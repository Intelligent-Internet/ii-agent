"""Minimal provider router used by the revived Scribe stack."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional


class ProviderRouter:
    """Route LLM invocations to a configured provider.

    The current implementation is intentionally lightweight. It normalises the
    payload and returns an echo-style response so the higher-level salon code
    can be exercised end-to-end without relying on the legacy stack.
    """

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path

    def send_message(self, provider: str, model: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Return a normalised response for the supplied payload."""

        messages = payload.get("messages") or []
        last_message_content = ""
        if isinstance(messages, list):
            for message in reversed(messages):
                if isinstance(message, dict):
                    last_message_content = str(message.get("content", "")).strip()
                if last_message_content:
                    break

        system_prompt = str(payload.get("system") or "").strip()
        body_parts = [part for part in (system_prompt, last_message_content) if part]
        combined = "\n\n".join(body_parts) if body_parts else ""

        response_text = (
            f"[provider={provider} model={model}] {combined}".strip()
            if combined
            else f"[provider={provider} model={model}]"
        )

        meta: Dict[str, Any] = {}
        mentions = payload.get("mentions")
        if mentions:
            meta["mentions"] = list(mentions)
        context = payload.get("context")
        if context:
            meta["context"] = dict(context)
        options = payload.get("options")
        if options:
            meta["options"] = dict(options)

        return {
            "content": response_text,
            "artifacts": [],
            "meta": meta,
        }

    @classmethod
    def lazy_default(cls) -> "ProviderRouter":
        """Construct a router using default configuration discovery."""

        default_config = Path("config/models.yml")
        if not default_config.exists():
            default_config = None
        return cls(config_path=default_config)
