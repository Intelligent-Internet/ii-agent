"""Pre- and post-hook callables that wire SAGE into the agent turn cycle.

The pre-hook performs a semantic recall against the SAGE node and injects a
synthetic context message before the model runs. The post-hook stores the
turn observation. The post-hook is decorated with
``@hook(run_in_background=True)`` so AgentOS schedules it as a FastAPI
background task — the agent response is returned to the caller without
waiting for consensus.

Both hooks are defensive: any failure, timeout, or missing dependency is
logged at debug level and swallowed. The agent turn is never blocked by
SAGE being slow, down, or misconfigured.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ii_agent.agents.hooks.decorator import hook
from ii_agent.core.logger import logger
from ii_agent.integrations.sage.client import SageClient

if TYPE_CHECKING:  # pragma: no cover — type-checking only
    from ii_agent.agents.runs import RunInput, RunOutput


# Marker stored on the RunInput so the post-hook can correlate what was
# injected into the prompt with what gets stored. Keeps the public API
# on RunInput untouched — we use attribute-setattr rather than a subclass.
_SAGE_CONTEXT_ATTR = "_sage_recalled_context"


def _format_recall_block(memories: list[dict[str, Any]]) -> str:
    """Format a recall result set into a human-readable context block."""
    if not memories:
        return ""
    lines = ["[SAGE persistent memory — recalled context]"]
    for m in memories:
        confidence = float(m.get("confidence", 0.0) or 0.0)
        content = str(m.get("content", "")).strip().replace("\n", " ")
        if not content:
            continue
        lines.append(f"- [{confidence:.0%}] {content[:400]}")
    if len(lines) == 1:  # only the header survived
        return ""
    return "\n".join(lines)


def _extract_user_text(run_input: "RunInput | None") -> str:
    """Extract a plain-text representation of the user's turn input."""
    if run_input is None:
        return ""
    try:
        return run_input.input_content_string() or ""
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"SAGE: failed to stringify run input: {exc}")
        return ""


def _extract_response_text(run_output: "RunOutput | None") -> str:
    """Extract a plain-text representation of the assistant's response."""
    if run_output is None or run_output.content is None:
        return ""
    content = run_output.content
    if isinstance(content, str):
        return content
    try:
        return str(content)
    except Exception:  # noqa: BLE001
        return ""


def make_sage_hooks(
    client: SageClient,
) -> tuple[Any, Any]:
    """Build the pre- and post-hook closures bound to ``client``.

    Returning a pair of closures (rather than module-level hooks) lets a
    single process host multiple agents with different SAGE
    configurations — each registration gets its own client.
    """

    @hook
    async def sage_pre_hook(run_input: "RunInput", **_kwargs: Any) -> None:
        """Recall SAGE memories and inject them into the run input.

        Uses a strict timeout (``SAGE_PRE_HOOK_TIMEOUT_S``, default 2s) so
        a slow SAGE node never blocks the agent turn. Falls back to empty
        recall on timeout or any exception.
        """
        if not client.config.enabled:
            return

        user_text = _extract_user_text(run_input)
        if not user_text:
            return

        try:
            memories = await asyncio.wait_for(
                client.recall(user_text),
                timeout=client.config.pre_hook_timeout_s,
            )
        except asyncio.TimeoutError:
            logger.debug(
                "SAGE pre-hook recall timed out after "
                f"{client.config.pre_hook_timeout_s}s — proceeding without context"
            )
            memories = []
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"SAGE pre-hook recall errored: {exc}")
            memories = []

        block = _format_recall_block(memories)
        if not block:
            return

        # Stash the recalled memories on the RunInput so the post-hook can
        # reference them when storing the turn observation.
        try:
            setattr(run_input, _SAGE_CONTEXT_ATTR, memories)
        except Exception:  # noqa: BLE001 — dataclass with slots would block this
            pass

        # Attach the context block to the turn input. We prepend it to the
        # existing string rather than replacing it so the model still sees
        # the user's original content verbatim.
        # Inject the recalled context. The fast path handles plain strings
        # (the dominant case for chat agents). For Message-shaped inputs
        # we detect by duck-typing on `content` so we don't have to import
        # the heavy framework module at hook-execution time.
        try:
            if isinstance(run_input.input_content, str):
                run_input.input_content = f"{block}\n\n{run_input.input_content}"
            elif hasattr(run_input.input_content, "content") and isinstance(
                getattr(run_input.input_content, "content", None), (str, type(None))
            ):
                existing = run_input.input_content.content or ""
                run_input.input_content.content = f"{block}\n\n{existing}"
            # For other shapes (list/dict/BaseModel), skip injection —
            # they may not round-trip cleanly with a prepended block.
            # TODO(follow-up): support list/dict input_content injection.
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"SAGE pre-hook failed to inject context: {exc}")

        logger.debug(f"SAGE pre-hook injected {len(memories)} recalled memories")

    @hook(run_in_background=True)
    async def sage_post_hook(
        run_output: "RunOutput",
        **_kwargs: Any,
    ) -> None:
        """Store a concise observation of the turn in SAGE.

        Runs in background via AgentOS so the agent response is returned
        without waiting on consensus. Silently drops failures.
        """
        if not client.config.enabled:
            return

        user_text = _extract_user_text(run_output.input)
        assistant_text = _extract_response_text(run_output)
        if not user_text and not assistant_text:
            return

        # Truncate aggressively — SAGE is for durable institutional memory,
        # not transcripts. Keep the observation small and semantic.
        observation = (
            f"ii-agent turn (agent={run_output.agent_name or 'unknown'}): "
            f"user asked: {user_text[:400]}. "
            f"assistant responded: {assistant_text[:400]}."
        )

        try:
            await client.propose(
                observation,
                memory_type="observation",
                confidence=0.80,
            )
        except Exception as exc:  # noqa: BLE001 — background task must not throw
            logger.debug(f"SAGE post-hook propose failed: {exc}")

    return sage_pre_hook, sage_post_hook
