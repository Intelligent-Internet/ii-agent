"""A2A-backed turn loop for chat mode.

Replaces ``LLMTurnLoopService`` when ``AGENT_CHAT_INNER_LOOP_MODE=a2a``.
Routes chat turns through the A2A adapter (same transport layer used by
agent mode) while preserving the identical ``AsyncIterator[Dict]`` SSE
interface expected by ``ChatService``.

Architecture:
    ChatService → A2AChatTurnLoop.run() → IIAgentA2AClient.astream()
                                        → ChatA2AEventTranslator.translate()
                                        → tool bridging via ChatToolService
                                        → billing via pubsub

Fallback: On A2A failure (circuit breaker open, stream error) when
``fallback_to_native`` is enabled, transparently falls back to the
``LLMTurnLoopService`` for the same turn.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, AsyncIterator, Dict, List, TYPE_CHECKING

from ii_agent.chat.application.a2a_event_translator import ChatA2AEventTranslator
from ii_agent.chat.application.context_service import ContextWindowManager
from ii_agent.chat.messages.service import MessageService
from ii_agent.chat.types import (
    BinaryContent,
    ImageURLContent,
    MessageRole,
    TextContent,
    ToolResult,
)
from ii_agent.core.db import get_db_session_local
from ii_agent.core.redis import cancel
from ii_agent.integrations.a2a.as_client import IIAgentA2AClient
from ii_agent.integrations.a2a.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
)
from ii_agent.realtime.events.app_events import ModelUsageEvent, ToolUsageEvent
from ii_agent.settings.llm.schemas import ModelConfig

if TYPE_CHECKING:
    from ii_agent.chat.api.schemas import ChatMessageRequest
    from ii_agent.chat.application.tool_service import ChatToolService
    from ii_agent.chat.application.turn_loop_service import LLMTurnLoopService
    from ii_agent.chat.tools.base import BaseTool
    from ii_agent.chat.types import Message
    from ii_agent.realtime.pubsub.asyncio_pubsub import AsyncIOPubSub

logger = logging.getLogger(__name__)


class A2AChatTurnLoop:
    """A2A-backed replacement for ``LLMTurnLoopService``.

    Shares the same ``run()`` signature and yields identical SSE dicts so
    ``ChatService`` can swap between direct and A2A paths transparently.
    """

    def __init__(
        self,
        *,
        client: IIAgentA2AClient,
        circuit_breaker: CircuitBreaker,
        fallback_loop: LLMTurnLoopService,
        fallback_to_native: bool = True,
        context_reuse: bool = True,
        a2a_backend: str = "copilot",
        message_service: MessageService,
        pubsub: AsyncIOPubSub | None = None,
    ) -> None:
        self._client = client
        self._circuit_breaker = circuit_breaker
        self._fallback_loop = fallback_loop
        self._fallback_to_native = fallback_to_native
        self._context_reuse = context_reuse
        self._a2a_backend = a2a_backend
        self._message_service = message_service
        self._pubsub = pubsub

    # ------------------------------------------------------------------
    # Public interface (same signature as LLMTurnLoopService.run)
    # ------------------------------------------------------------------

    async def run(
        self,
        *,
        messages: List,
        provider,
        tool_registry: Dict[str, BaseTool],
        tools_to_pass: List[Dict[str, Any]],
        is_code_interpreter_enabled: bool,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        model_id: str,
        user_message: Message,
        run_id: str,
        model_config: ModelConfig,
        chat_request: ChatMessageRequest,
        tool_service: ChatToolService,
    ) -> AsyncIterator[Dict]:
        """Run the A2A turn loop, falling back to direct if needed."""
        try:
            await self._circuit_breaker.check()
        except CircuitBreakerOpenError:
            if self._fallback_to_native:
                self._circuit_breaker.record_fallback()
                logger.warning(
                    "A2A circuit breaker open; falling back to direct LLM for chat (session=%s)",
                    session_id,
                )
                async for event in self._fallback_loop.run(
                    messages=messages,
                    provider=provider,
                    tool_registry=tool_registry,
                    tools_to_pass=tools_to_pass,
                    is_code_interpreter_enabled=is_code_interpreter_enabled,
                    session_id=session_id,
                    user_id=user_id,
                    model_id=model_id,
                    user_message=user_message,
                    run_id=run_id,
                    model_config=model_config,
                    chat_request=chat_request,
                    tool_service=tool_service,
                ):
                    yield event
                return
            raise

        try:
            async for event in self._a2a_turn_loop(
                messages=messages,
                tool_registry=tool_registry,
                tools_to_pass=tools_to_pass,
                session_id=session_id,
                user_id=user_id,
                model_id=model_id,
                user_message=user_message,
                run_id=run_id,
                model_config=model_config,
                chat_request=chat_request,
                tool_service=tool_service,
            ):
                yield event
            await self._circuit_breaker.record_success()

        except Exception as exc:
            await self._circuit_breaker.record_failure(exc)
            if self._fallback_to_native:
                self._circuit_breaker.record_fallback()
                logger.warning(
                    "A2A stream failed; falling back to direct LLM for chat (session=%s, error=%s)",
                    session_id,
                    exc,
                )
                async for event in self._fallback_loop.run(
                    messages=messages,
                    provider=provider,
                    tool_registry=tool_registry,
                    tools_to_pass=tools_to_pass,
                    is_code_interpreter_enabled=is_code_interpreter_enabled,
                    session_id=session_id,
                    user_id=user_id,
                    model_id=model_id,
                    user_message=user_message,
                    run_id=run_id,
                    model_config=model_config,
                    chat_request=chat_request,
                    tool_service=tool_service,
                ):
                    yield event
            else:
                raise

    # ------------------------------------------------------------------
    # Internal: A2A streaming loop
    # ------------------------------------------------------------------

    async def _a2a_turn_loop(
        self,
        *,
        messages: List,
        tool_registry: Dict[str, BaseTool],
        tools_to_pass: List[Dict[str, Any]],
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        model_id: str,
        user_message: Message,
        run_id: str,
        model_config: ModelConfig,
        chat_request: ChatMessageRequest,
        tool_service: ChatToolService,
    ) -> AsyncIterator[Dict]:
        """Stream from the A2A adapter, bridging tools and translating events."""
        run_uuid = uuid.UUID(run_id) if isinstance(run_id, str) else run_id
        context_id = self._build_context_id(session_id)
        translator = ChatA2AEventTranslator()

        # Context compression — same as native turn loop
        async with get_db_session_local() as db:
            messages = await ContextWindowManager.compress_context_if_needed(
                db_session=db,
                messages=messages,
                session_id=session_id,
                llm_config=model_config,
                user_id=user_id,
            )

        # Build A2A metadata
        a2a_messages = self._build_a2a_messages(messages)
        native_tool_schemas = self._serialize_chat_tools(tools_to_pass)

        metadata: Dict[str, Any] = {
            "model": model_config.model_id,
            "native_tool_schemas": native_tool_schemas,
            "source": "chat",
        }
        logger.info(
            "[a2a:stream] model_id=%r context_id=%s source=chat",
            model_config.model_id,
            context_id,
        )

        # Forward extended thinking config if set
        thinking_tokens = getattr(model_config, "thinking_tokens", None)
        if isinstance(thinking_tokens, int) and thinking_tokens >= 1024:
            metadata["thinking_tokens"] = thinking_tokens

        # Extract system prompt from chat messages
        system_prompt = self._extract_system_prompt(messages)
        if system_prompt:
            metadata["system_message"] = system_prompt

        usage_data: Dict[str, Any] | None = None
        file_parts: list = []

        await cancel.raise_if_cancelled(run_id)

        from ii_agent.agents.models.message import Message as A2AMessage

        a2a_msg_objects = [
            A2AMessage(
                role=m["role"],
                content=m["content"],
                images=m.get("images") or None,
            )
            for m in a2a_messages
        ]

        async for event in self._client.astream(
            messages=a2a_msg_objects,
            context_id=context_id,
            metadata=metadata,
        ):
            await cancel.raise_if_cancelled(run_id)

            if event.event_type in {"session.error", "error"}:
                message = str(event.data.get("message") or "Unknown A2A stream error")
                logger.warning(
                    "A2A chat stream returned session error; using native fallback "
                    "(session=%s, context_id=%s, error=%s)",
                    session_id,
                    context_id,
                    message,
                )
                raise RuntimeError(message)

            # Handle tool bridging requests
            if event.event_type == "tool.execution_request":
                tool_result_events = await self._bridge_tool_execution(
                    event_data=event.data,
                    tool_registry=tool_registry,
                    tool_service=tool_service,
                    session_id=session_id,
                    user_id=user_id,
                    run_uuid=run_uuid,
                )
                for tr_event in tool_result_events:
                    yield tr_event
                continue

            # Track usage
            if event.event_type in {"assistant.usage", "usage"}:
                usage_data = event.data

            # Translate to chat SSE events
            for sse_event in translator.translate(event):
                yield sse_event

        # Emit any pending stop events
        for sse_event in translator.finalize():
            yield sse_event

        # Build usage and publish billing
        if usage_data:
            token_usage = translator.build_usage_token_usage(usage_data)
            yield {
                "type": "usage",
                "usage": {
                    "input_tokens": token_usage.input_tokens,
                    "output_tokens": token_usage.output_tokens,
                    "cache_read_tokens": token_usage.cache_read_tokens,
                    "cache_write_tokens": token_usage.cache_write_tokens,
                },
            }

            await self._publish_a2a_llm_usage(
                usage_data=usage_data,
                token_usage=token_usage,
                session_id=session_id,
                user_id=user_id,
                run_id=run_uuid,
                model_config=model_config,
            )

        await cancel.raise_if_cancelled(run_id)

        # Determine finish reason from stream state
        finish_reason = translator.finish_reason or "end_turn"

        # Save assistant message
        content_text = translator.accumulated_content

        parts: list = []
        if content_text:
            parts.append(TextContent(text=content_text))

        async with get_db_session_local() as db:
            assistant_message = await self._message_service.create_message(
                db,
                session_id=session_id,
                role=MessageRole.ASSISTANT,
                parts=parts,
                model_id=model_id,
                parent_message_id=user_message.id,
                usage=translator.build_usage_token_usage(usage_data) if usage_data else None,
                file_ids=[f["id"] for f in file_parts],
                finish_reason=finish_reason,
            )
            await db.commit()

        # Post-response summarization — same as native turn loop
        async with get_db_session_local() as db:
            await ContextWindowManager.check_and_summarize_after_response(
                db_session=db,
                session_id=session_id,
                llm_config=model_config,
                user_id=user_id,
            )
            await db.commit()

        yield {
            "type": "complete",
            "message_id": assistant_message.id,
            "finish_reason": finish_reason,
            "files": file_parts,
        }

    # ------------------------------------------------------------------
    # Tool bridging
    # ------------------------------------------------------------------

    async def _bridge_tool_execution(
        self,
        *,
        event_data: Dict[str, Any],
        tool_registry: Dict[str, BaseTool],
        tool_service: ChatToolService,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        run_uuid: uuid.UUID,
    ) -> list[Dict[str, Any]]:
        """Execute a bridged tool and post result back to adapter."""
        tool_call_id = str(event_data.get("tool_call_id", ""))
        # The adapter SSE payload uses ``tool_name`` and ``arguments`` (see
        # ``copilot_backend._inject_tool_request`` and the design doc
        # docs/design-docs/a2a-tool-bridge-gap-analysis.md).  Fall back to
        # ``name``/``input`` for forward-compat with older adapter payloads.
        tool_name = str(event_data.get("tool_name") or event_data.get("name", ""))
        tool_input = event_data.get("arguments")
        if tool_input is None:
            tool_input = event_data.get("input", {})

        if isinstance(tool_input, str):
            try:
                tool_input = json.loads(tool_input)
            except json.JSONDecodeError:
                tool_input = {"input": tool_input}

        # ChatToolService.execute_tool builds a ToolCallInput whose ``input``
        # field is typed as ``str`` (a JSON-encoded parameters blob — chat
        # tools call ``json.loads(tool_call.input)`` in their ``run``
        # method).  The native chat path passes the LLM-emitted JSON string
        # straight through, but the A2A adapter delivers ``arguments`` as a
        # dict.  Re-serialise so the downstream contract holds.
        tool_input_str = json.dumps(
            tool_input if isinstance(tool_input, dict) else {"input": tool_input}
        )

        events: list[Dict[str, Any]] = []

        tool_result = await tool_service.execute_tool(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            tool_input=tool_input_str,
            tool_registry=tool_registry,
        )

        events.append(
            {
                "type": "tool_result",
                "tool_call_id": tool_result.tool_call_id,
                "name": tool_result.name,
                "output": tool_result.output.model_dump(),
            }
        )

        # Post result back to adapter so the A2A backend can continue
        result_str = json.dumps(tool_result.output.model_dump(), default=str)
        await self._client.post_tool_result(
            tool_call_id=tool_call_id,
            result=result_str,
        )

        # Publish tool billing
        await self._publish_tool_usage(
            tool_result=tool_result,
            session_id=session_id,
            user_id=user_id,
            run_id=run_uuid,
        )

        return events

    # ------------------------------------------------------------------
    # Message conversion
    # ------------------------------------------------------------------

    @staticmethod
    def _build_a2a_messages(chat_messages: List) -> List[Dict[str, Any]]:
        """Convert chat Message objects to dicts for A2A transport.

        Returns dicts with ``role``, ``content`` (text), and optionally
        ``images`` (list of ``Image`` objects from ``BinaryContent`` /
        ``ImageURLContent`` parts).
        """
        result: List[Dict[str, Any]] = []
        for msg in chat_messages:
            role = getattr(msg, "role", "user")
            if hasattr(role, "value"):
                role = role.value

            # Skip tool result messages — the adapter manages its own tool flow
            if str(role) == "tool":
                continue

            # Extract text content and images from parts
            content = ""
            parts = getattr(msg, "parts", None)
            images: list = []
            if parts:
                text_parts = []
                for part in parts:
                    if isinstance(part, TextContent):
                        text_parts.append(part.text)
                    elif isinstance(part, BinaryContent):
                        # Convert to A2A Image for base64 transport
                        from ii_agent.files.media.media import Image as A2AImage

                        images.append(
                            A2AImage(
                                content=part.data,
                                mime_type=part.mime_type,
                            )
                        )
                    elif isinstance(part, ImageURLContent):
                        from ii_agent.files.media.media import Image as A2AImage

                        images.append(A2AImage(url=part.url))
                    elif isinstance(part, str):
                        text_parts.append(part)
                    elif hasattr(part, "text"):
                        text_parts.append(str(part.text))
                content = "\n".join(text_parts)
            elif isinstance(msg, dict):
                content = str(msg.get("content", ""))

            entry: Dict[str, Any] = {"role": str(role), "content": content}
            if images:
                entry["images"] = images
            result.append(entry)
        return result

    @staticmethod
    def _extract_system_prompt(chat_messages: List) -> str | None:
        """Extract system prompt from chat message history."""
        for msg in chat_messages:
            role = getattr(msg, "role", "")
            if hasattr(role, "value"):
                role = role.value
            if str(role) in ("system", "developer"):
                parts = getattr(msg, "parts", None)
                if parts:
                    for part in parts:
                        if isinstance(part, TextContent):
                            return part.text
                        if hasattr(part, "text"):
                            return str(part.text)
        return None

    @staticmethod
    def _serialize_chat_tools(tools_to_pass: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Serialize chat tool definitions for A2A metadata.

        Chat tools are already in OpenAI-compat dict format
        ``{"type": "function", "function": {"name": ..., "parameters": ...}}``.
        Extract and normalize to the flat schema the adapter expects.
        """
        schemas: List[Dict[str, Any]] = []
        for tool_def in tools_to_pass:
            if isinstance(tool_def, dict):
                func = tool_def.get("function", tool_def)
                name = func.get("name", "")
                if not name:
                    continue
                schemas.append(
                    {
                        "name": name,
                        "description": func.get("description", ""),
                        "parameters": func.get("parameters", {"type": "object", "properties": {}}),
                    }
                )
        return schemas

    # ------------------------------------------------------------------
    # Context ID
    # ------------------------------------------------------------------

    def _build_context_id(self, session_id: uuid.UUID) -> str:
        """Build a context ID for the A2A adapter."""
        if self._context_reuse:
            return f"chat-{session_id}"
        return f"chat-{session_id}-{uuid.uuid4()}"

    # ------------------------------------------------------------------
    # Billing
    # ------------------------------------------------------------------

    async def _publish_a2a_llm_usage(
        self,
        *,
        usage_data: Dict[str, Any],
        token_usage,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        run_id: uuid.UUID,
        model_config: ModelConfig,
    ) -> None:
        """Publish ModelUsageEvent with A2A billing backend."""
        if not self._pubsub:
            return

        try:
            await self._pubsub.publish(
                ModelUsageEvent(
                    session_id=session_id,
                    user_id=user_id,
                    run_id=run_id,
                    setting_id=model_config.id,
                    model_id=model_config.model_id,
                    provider=model_config.provider,
                    pricing=model_config.pricing,
                    input_tokens=token_usage.input_tokens,
                    output_tokens=token_usage.output_tokens,
                    cache_read_tokens=token_usage.cache_read_tokens,
                    cache_write_tokens=token_usage.cache_write_tokens,
                    reasoning_tokens=token_usage.reasoning_tokens,
                    is_user_key=model_config.is_user_model(),
                    billing_backend=f"a2a:{self._a2a_backend}",
                    provider_reported_cost=float(usage_data.get("cost", 0.0)),
                    premium_requests=int(usage_data.get("premium_requests", 0)),
                )
            )
        except Exception:
            logger.exception(
                "Failed to publish A2A LLM usage event (session=%s, model=%s)",
                session_id,
                model_config.model_id,
            )

    async def _publish_tool_usage(
        self,
        *,
        tool_result: ToolResult,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        run_id: uuid.UUID,
    ) -> None:
        """Publish ToolUsageEvent for credit deduction."""
        if not self._pubsub:
            return
        if not tool_result.cost_usd or tool_result.cost_usd <= 0:
            return

        try:
            await self._pubsub.publish(
                ToolUsageEvent(
                    session_id=session_id,
                    user_id=user_id,
                    run_id=run_id,
                    tool_name=tool_result.name,
                    cost_usd=tool_result.cost_usd,
                )
            )
        except Exception:
            logger.exception(
                "Failed to publish tool usage event (session=%s, tool=%s)",
                session_id,
                tool_result.name,
            )
