"""Council service - parallel LLM execution engine for Model Council feature."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple, TYPE_CHECKING

from ii_agent.chat.types import (
    Message,
    TextContent,
    MessageRole,
    CouncilPreferences,
)
from ii_agent.chat.llm import get_client
from ii_agent.settings.llm.schemas import ModelConfig
from ii_agent.core.config.settings import get_settings
from ii_agent.core.redis import cancel

if TYPE_CHECKING:
    from ii_agent.billing.schemas import TokenUsage
    from ii_agent.integrations.a2a.as_client import IIAgentA2AClient

logger = logging.getLogger(__name__)

COUNCIL_MODEL_TIMEOUT = 180  # seconds per model
MIN_COUNCIL_MODELS = 2
MAX_COUNCIL_MODELS = 10

SYNTHESIS_PROMPT_TEMPLATE = """You are a synthesis assistant. The user asked the following question:

<user_question>
{user_question}
</user_question>

Multiple AI models have provided their responses. Please synthesize these into a single, comprehensive, well-structured answer that combines the best insights from all responses.

{model_outputs}

Instructions:
- Combine the key insights from all model responses into a unified answer
- Resolve any contradictions by using your best judgment
- Maintain accuracy and completeness
- Use clear, well-organized formatting
- Do NOT mention the individual models or say "Model X said..."
- Write the response as if you are directly answering the user's question"""


def _extract_text(content) -> str:
    """Extract plain text from a list of content parts or a raw string."""
    if isinstance(content, str):
        return content
    return "".join(p.text for p in content if isinstance(p, TextContent))


def _should_fallback_to_direct(exc: Exception) -> bool:
    """Return True when an A2A failure should degrade gracefully to direct inference."""
    details = f"{type(exc).__name__}: {exc}".lower()
    return any(
        marker in details
        for marker in (
            "connect",
            "connection",
            "timeout",
            "rate limit",
            "429",
            "temporar",
            "unavailable",
            "overloaded",
        )
    )


async def _call_via_a2a(
    *,
    a2a_client: IIAgentA2AClient,
    messages: List[Message],
    context_id: str,
    metadata: Dict[str, Any] | None = None,
) -> Tuple[str, Optional[TokenUsage], float, int]:
    """Execute a council member call via A2A, collecting content + usage.

    Returns ``(content, usage, provider_reported_cost, premium_requests)``.
    """
    from ii_agent.agents.models.message import Message as AgentMessage
    from ii_agent.billing.schemas import TokenUsage

    # Convert chat messages to A2A agent messages (text only, no tool bridging)
    a2a_messages: List[AgentMessage] = []
    for msg in messages:
        role = msg.role.value if hasattr(msg.role, "value") else str(msg.role)
        if role == "tool":
            continue
        text = _extract_text(msg.parts if hasattr(msg, "parts") else "")
        a2a_messages.append(AgentMessage(role=role, content=text))

    content_parts: List[str] = []
    full_content: str | None = None
    usage_data: Dict[str, Any] = {}

    async for event in a2a_client.astream(
        messages=a2a_messages,
        context_id=context_id,
        metadata=metadata,
    ):
        et = event.event_type
        if et in ("assistant.message", "message_complete", "content_done"):
            c = event.data.get("content", "")
            if c:
                full_content = str(c)
        elif et in ("assistant.message_delta", "text_delta", "message_delta"):
            delta = event.data.get("delta", "")
            if delta:
                content_parts.append(str(delta))
        elif et in ("assistant.usage", "usage"):
            usage_data = event.data
        elif et in ("session.error", "error"):
            raise RuntimeError(event.data.get("message", "A2A agent returned an error"))

    # Prefer the full message if available; fall back to joined deltas
    content = full_content if full_content is not None else "".join(content_parts)

    usage: TokenUsage | None = None
    if usage_data:
        usage = TokenUsage(
            input_tokens=int(usage_data.get("input_tokens") or 0),
            output_tokens=int(usage_data.get("output_tokens") or 0),
            cache_read_tokens=int(usage_data.get("cache_read_tokens") or 0),
            cache_write_tokens=int(usage_data.get("cache_write_tokens") or 0),
            reasoning_tokens=int(usage_data.get("reasoning_tokens") or 0),
            cost_usd=float(usage_data.get("cost") or 0.0),
        )

    return (
        content,
        usage,
        float(usage_data.get("cost") or 0.0),
        int(usage_data.get("premium_requests") or 0),
    )


class CouncilService:
    """Parallel execution engine for Model Council feature.

    Runs multiple LLMs in parallel, collects their outputs,
    then produces a synthesized response from a designated synthesis model.
    """

    @classmethod
    def validate_preferences(cls, preferences: CouncilPreferences) -> None:
        """Validate council preferences. Raises ValueError on invalid config."""
        if not preferences.enabled:
            raise ValueError("Council mode is not enabled")

        num_models = len(preferences.council_models)
        if num_models < MIN_COUNCIL_MODELS:
            raise ValueError(
                f"Council requires at least {MIN_COUNCIL_MODELS} models, got {num_models}"
            )
        if num_models > MAX_COUNCIL_MODELS:
            raise ValueError(
                f"Council supports at most {MAX_COUNCIL_MODELS} models, got {num_models}"
            )

        if not preferences.synthesis_model_id:
            raise ValueError("Synthesis model ID is required")

    @classmethod
    async def stream_council_response(
        cls,
        *,
        user_id: uuid.UUID,
        messages: List[Message],
        user_question: str,
        council_preferences: CouncilPreferences,
        model_configs: Dict[str, ModelConfig],
        model_names: Dict[str, str],
        run_id: str,
        session_id: uuid.UUID,
        a2a_client: IIAgentA2AClient | None = None,
        a2a_backend: str = "copilot",
    ) -> AsyncIterator[Dict[str, Any]]:
        """Run council models in parallel, then synthesize.

        Yields dict events:
          - council_member_start / council_member_complete / council_member_error
          - council_synthesis_start / council_synthesis_complete
          - council_result with final metadata
        """
        cls.validate_preferences(council_preferences)

        queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        tasks: List[asyncio.Task] = []
        council_had_error = False
        member_outputs: Dict[str, str] = {}  # model_id -> collected content

        async def run_single_model(model_id: str, config: ModelConfig) -> None:
            nonlocal council_had_error
            display_name = model_names.get(model_id, model_id)

            try:
                await queue.put(
                    {
                        "type": "council_member_start",
                        "model_id": model_id,
                        "model_name": display_name,
                    }
                )

                # BYOK users go direct in cloud; in local mode all models
                # route through A2A (operator owns all keys).
                is_cloud_byok = config.is_user_model() and get_settings().environment != "local"
                use_a2a = a2a_client is not None and not is_cloud_byok

                if use_a2a:
                    # A2A path — billing via a2a:{backend}
                    context_id = f"council-{session_id}-{model_id}"
                    metadata = {"model": config.model_id, "source": "council"}
                    try:
                        content, usage, cost, prem_req = await asyncio.wait_for(
                            _call_via_a2a(
                                a2a_client=a2a_client,
                                messages=messages,
                                context_id=context_id,
                                metadata=metadata,
                            ),
                            timeout=COUNCIL_MODEL_TIMEOUT,
                        )
                    except (ConnectionError, OSError) as conn_err:
                        # A2A adapter unreachable — fall back to direct LLM
                        # so the council can still produce output.
                        logger.warning(
                            "Council model %s A2A unreachable (%s), falling back to direct",
                            model_id,
                            conn_err,
                        )
                        use_a2a = False  # noqa: F841 — fall through to direct path below
                    except Exception as a2a_exc:
                        if _should_fallback_to_direct(a2a_exc):
                            logger.warning(
                                "Council model %s A2A failed (%s), falling back to direct",
                                model_id,
                                a2a_exc,
                            )
                            use_a2a = False  # fall through to direct path below
                        else:
                            raise
                    else:
                        member_outputs[model_id] = content

                        await queue.put(
                            {
                                "type": "council_member_complete",
                                "model_id": model_id,
                                "model_name": display_name,
                                "content": content,
                                "usage": usage,
                                "model_config": config,
                                "billing_backend": f"a2a:{a2a_backend}",
                                "provider_reported_cost": cost,
                                "premium_requests": prem_req,
                            }
                        )

                if not use_a2a:
                    # Direct path — native billing
                    client = get_client(config)

                    async def _call():
                        response = await client.send(messages=messages)
                        return _extract_text(response.content), response.usage

                    content, usage = await asyncio.wait_for(_call(), timeout=COUNCIL_MODEL_TIMEOUT)
                    member_outputs[model_id] = content

                    await queue.put(
                        {
                            "type": "council_member_complete",
                            "model_id": model_id,
                            "model_name": display_name,
                            "content": content,
                            "usage": usage,
                            "model_config": config,
                            "billing_backend": "native",
                        }
                    )

            except asyncio.TimeoutError:
                council_had_error = True
                logger.warning(f"Council model {model_id} timed out after {COUNCIL_MODEL_TIMEOUT}s")
                await queue.put(
                    {
                        "type": "council_member_error",
                        "model_id": model_id,
                        "model_name": display_name,
                        "error": f"Model timed out after {COUNCIL_MODEL_TIMEOUT}s",
                    }
                )
            except Exception as e:
                council_had_error = True
                logger.error(f"Council model {model_id} failed: {e}", exc_info=True)
                await queue.put(
                    {
                        "type": "council_member_error",
                        "model_id": model_id,
                        "model_name": display_name,
                        "error": str(e),
                    }
                )

        try:
            # Phase 1: Launch all council models in parallel
            for model_config in council_preferences.council_models:
                mid = model_config.model_id
                config = model_configs.get(mid)
                if not config:
                    logger.warning(f"No LLM config for council model {mid}, skipping")
                    continue
                task = asyncio.create_task(run_single_model(mid, config))
                tasks.append(task)

            # Monitor task completion and drain queue
            pending_tasks = set(tasks)

            while pending_tasks:
                await cancel.raise_if_cancelled(run_id)

                _, pending_tasks = await asyncio.wait(
                    pending_tasks, timeout=0.1, return_when=asyncio.FIRST_COMPLETED
                )

                while not queue.empty():
                    yield queue.get_nowait()

            # Final drain after all tasks complete
            while not queue.empty():
                yield queue.get_nowait()

            await cancel.raise_if_cancelled(run_id)

            # Phase 2: Synthesis
            if not member_outputs:
                yield {
                    "type": "council_synthesis_error",
                    "error": "No council member produced output",
                }
                return

            synthesis_model_id = council_preferences.synthesis_model_id
            synthesis_config = model_configs.get(synthesis_model_id)
            if not synthesis_config:
                yield {
                    "type": "council_synthesis_error",
                    "error": f"No config for synthesis model: {synthesis_model_id}",
                }
                return

            model_output_sections = []
            for idx, (mid, content) in enumerate(member_outputs.items(), 1):
                name = model_names.get(mid, mid)
                model_output_sections.append(
                    f'<model_response_{idx} model="{name}">\n{content}\n</model_response_{idx}>'
                )

            synthesis_prompt = SYNTHESIS_PROMPT_TEMPLATE.format(
                user_question=user_question,
                model_outputs="\n\n".join(model_output_sections),
            )

            synthesis_message = Message(
                id=messages[-1].id,
                role=MessageRole.USER,
                parts=[TextContent(text=synthesis_prompt)],
                session_id=messages[-1].session_id,
                created_at=messages[-1].created_at,
                updated_at=messages[-1].updated_at,
            )

            yield {"type": "council_synthesis_start", "model_id": synthesis_model_id}

            is_cloud_byok_synth = (
                synthesis_config.is_user_model() and get_settings().environment != "local"
            )
            use_a2a_synthesis = a2a_client is not None and not is_cloud_byok_synth

            if use_a2a_synthesis:
                context_id = f"council-synthesis-{session_id}"
                metadata = {"model": synthesis_config.model_id, "source": "council-synthesis"}
                try:
                    synthesis_content, syn_usage, syn_cost, syn_prem = await _call_via_a2a(
                        a2a_client=a2a_client,
                        messages=[synthesis_message],
                        context_id=context_id,
                        metadata=metadata,
                    )
                except (ConnectionError, OSError) as conn_err:
                    logger.warning(
                        "Council synthesis A2A unreachable (%s), falling back to direct",
                        conn_err,
                    )
                    use_a2a_synthesis = False
                except Exception as a2a_exc:
                    if _should_fallback_to_direct(a2a_exc):
                        logger.warning(
                            "Council synthesis A2A failed (%s), falling back to direct",
                            a2a_exc,
                        )
                        use_a2a_synthesis = False
                    else:
                        raise
                else:
                    yield {
                        "type": "council_synthesis_complete",
                        "model_id": synthesis_model_id,
                        "content": synthesis_content,
                        "usage": syn_usage,
                        "model_config": synthesis_config,
                        "billing_backend": f"a2a:{a2a_backend}",
                        "provider_reported_cost": syn_cost,
                        "premium_requests": syn_prem,
                    }

            if not use_a2a_synthesis:
                synthesis_client = get_client(synthesis_config)
                synthesis_response = await synthesis_client.send(messages=[synthesis_message])
                synthesis_content = _extract_text(synthesis_response.content)

                yield {
                    "type": "council_synthesis_complete",
                    "model_id": synthesis_model_id,
                    "content": synthesis_content,
                    "usage": synthesis_response.usage,
                    "model_config": synthesis_config,
                    "billing_backend": "native",
                }

            yield {
                "type": "council_result",
                "member_outputs": member_outputs,
                "synthesis_content": synthesis_content,
                "synthesis_model_id": synthesis_model_id,
                "model_names": model_names,
                "had_error": council_had_error,
            }

        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except (asyncio.CancelledError, Exception):
                        pass
