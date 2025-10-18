"""Lightweight LLM invocation helpers for the Salon runtime."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Sequence

from scribe_core.provider_router import ProviderRouter

from .salon_personas import SalonParticipant, SalonPersona

logger = logging.getLogger(__name__)


@dataclass
class InvokeResult:
    """Normalized result produced by an LLM invocation."""

    model: str
    provider: str
    content: str
    artifacts: list[Any] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)


class LLMInvoker:
    """Thin async wrapper around the synchronous provider router."""

    def __init__(
        self,
        router: Optional[ProviderRouter] = None,
        *,
        max_concurrent: int = 5,
        timeout_seconds: float = 30.0,
        retry_attempts: int = 2,
    ) -> None:
        self._router = router or ProviderRouter.lazy_default()
        # Retain the legacy knobs so existing callers do not break.
        self.max_concurrent = max_concurrent
        self.timeout_seconds = timeout_seconds
        self.retry_attempts = retry_attempts

    async def invoke(
        self,
        *,
        provider: str,
        model: str,
        messages: Sequence[Mapping[str, str]],
        system_prompt: Optional[str] = None,
        context: Optional[Mapping[str, Any]] = None,
        mentions: Optional[Sequence[str]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> InvokeResult:
        """Invoke a model through the configured provider router."""

        payload: Dict[str, Any] = {
            "messages": [dict(message) for message in messages],
            "system": system_prompt,
            "context": dict(context or {}),
            "mentions": list(mentions or []),
            "options": {},
        }

        if temperature is not None:
            payload["options"]["temperature"] = temperature
        if max_tokens is not None:
            payload["options"]["max_tokens"] = max_tokens

        try:
            raw_response = await asyncio.to_thread(
                self._router.send_message,
                provider,
                model,
                payload,
            )
        except Exception as exc:  # pragma: no cover - defensive guardrail
            logger.exception("LLM invocation failed (provider=%s model=%s)", provider, model)
            meta: Dict[str, Any] = {"error": str(exc)}
            if mentions:
                meta["mentions"] = list(mentions)
            return InvokeResult(
                model=model,
                provider=provider,
                content="",
                artifacts=[],
                meta=meta,
            )

        meta = dict(raw_response.get("meta") or {})
        if mentions:
            meta.setdefault("mentions", list(mentions))
        context_payload = payload.get("context") or {}
        if context_payload and "context" not in meta:
            meta["context"] = context_payload

        return InvokeResult(
            model=model,
            provider=provider,
            content=str(raw_response.get("content", "")),
            artifacts=list(raw_response.get("artifacts") or []),
            meta=meta,
        )

    async def invoke_participant(
        self,
        *,
        participant: SalonParticipant,
        persona: SalonPersona,
        topic: str,
        conversation_history: Optional[str] = None,
    ) -> InvokeResult:
        """Format a salon participant request then invoke the configured provider."""

        history = (conversation_history or "").strip()
        safe_history = history or "No previous conversation context is available."

        try:
            system_prompt = persona.system_prompt_template.format(
                topic=topic,
                history=safe_history,
            )
        except KeyError as exc:
            logger.error("Failed to format persona prompt for %s: %s", participant.id, exc)
            meta = {
                "error": f"prompt_format_error: {exc}",
                "participant_id": participant.id,
                "persona_id": persona.id,
            }
            return InvokeResult(
                model=participant.llm_config.get("model", ""),
                provider=participant.llm_config.get("provider", "anthropic"),
                content="",
                artifacts=[],
                meta=meta,
            )

        provider = participant.llm_config.get("provider", "anthropic")
        model = participant.llm_config.get("model", "claude-3-haiku")
        temperature = participant.llm_config.get("temperature")
        max_tokens = participant.llm_config.get("max_tokens")
        mentions = participant.metadata.get("mentions") if isinstance(participant.metadata, dict) else None

        user_prompt = (
            f"Salon topic: {topic}\n\n"
            f"Conversation so far:\n{safe_history}\n\n"
            f"Respond as persona '{persona.name}' ({persona.id})."
        )

        result = await self.invoke(
            provider=provider,
            model=model,
            messages=[{"role": "user", "content": user_prompt}],
            system_prompt=system_prompt,
            context={
                "participant_id": participant.id,
                "persona_id": persona.id,
                "topic": topic,
                "history_present": bool(history),
            },
            mentions=mentions,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        result.meta.setdefault("participant_id", participant.id)
        result.meta.setdefault("persona_id", persona.id)
        return result
