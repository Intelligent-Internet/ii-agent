"""Translate A2A SSE events to chat SSE dict format.

Maps adapter stream events (assistant.message_delta, assistant.reasoning_delta,
assistant.usage, etc.) to the chat SSE dict format expected by the REST streaming
endpoint and LLMTurnLoopService consumers.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from ii_agent.billing.schemas import TokenUsage
from ii_agent.integrations.a2a.as_client import A2AStreamEvent

logger = logging.getLogger(__name__)


class ChatA2AEventTranslator:
    """Stateful translator from A2A SSE events to chat SSE dicts.

    Tracks accumulated content and reasoning for synthetic finalization
    events (content_stop, thinking_stop) that have no direct A2A equivalent.
    """

    def __init__(self) -> None:
        self._content_started = False
        self._thinking_started = False
        self._accumulated_content = ""
        self._accumulated_thinking = ""
        self._finish_reason: str | None = None

    def translate(self, event: A2AStreamEvent) -> list[Dict[str, Any]]:
        """Translate a single A2A event into zero or more chat SSE dicts.

        Returns a list because some A2A events produce multiple chat events
        (e.g., first content delta produces both content_start and content_delta).
        """
        event_type = event.event_type
        data = event.data
        results: list[Dict[str, Any]] = []

        if event_type in {"assistant.message_delta", "text_delta", "message_delta"}:
            delta = str(data.get("delta") or data.get("text") or "")
            if not delta:
                return results
            if not self._content_started:
                results.append({"type": "content_start"})
                self._content_started = True
            results.append({"type": "content_delta", "content": delta})
            self._accumulated_content += delta

        elif event_type in {"assistant.reasoning_delta", "reasoning_delta"}:
            delta = str(data.get("delta") or data.get("text") or "")
            if not delta:
                return results
            if not self._thinking_started:
                results.append({"type": "thinking_start"})
                self._thinking_started = True
            results.append({"type": "thinking_delta", "thinking": delta})
            self._accumulated_thinking += delta

        elif event_type in {"assistant.reasoning", "reasoning_done"}:
            if self._thinking_started:
                results.append({"type": "thinking_stop"})
                self._thinking_started = False

        elif event_type in {"assistant.message", "message_complete", "content_done"}:
            content = str(data.get("content") or data.get("text") or "")
            if content:
                self._accumulated_content = content
            # Extract finish_reason if the backend reports one
            finish_reason = data.get("finish_reason") or data.get("stop_reason")
            if finish_reason:
                self._finish_reason = str(finish_reason)
            if self._content_started:
                results.append({"type": "content_stop"})
                self._content_started = False

        elif event_type in {"assistant.usage", "usage"}:
            results.append(self._translate_usage(data))

        elif event_type in {"session.error", "error"}:
            message = str(data.get("message") or "Unknown A2A stream error")
            results.append({"type": "error", "message": message})
            self._finish_reason = "error"

        elif event_type == "heartbeat":
            pass  # Ignore heartbeats

        elif event_type == "session.task_id":
            pass  # Internal — consumed by turn loop

        elif event_type == "tool.execution_request":
            pass  # Handled directly by turn loop, not translated

        return results

    def build_usage_token_usage(self, data: Dict[str, Any]) -> TokenUsage:
        """Build a TokenUsage from an A2A usage event's data dict."""
        return TokenUsage(
            input_tokens=int(data.get("input_tokens") or 0),
            output_tokens=int(data.get("output_tokens") or 0),
            cache_read_tokens=int(data.get("cache_read_tokens") or 0),
            cache_write_tokens=int(data.get("cache_write_tokens") or 0),
            reasoning_tokens=int(data.get("reasoning_tokens") or 0),
            cost_usd=float(data.get("cost") or 0.0),
        )

    @property
    def accumulated_content(self) -> str:
        return self._accumulated_content

    @property
    def accumulated_thinking(self) -> str:
        return self._accumulated_thinking

    @property
    def finish_reason(self) -> str | None:
        """Finish reason extracted from stream events, or None if not reported."""
        return self._finish_reason

    def finalize(self) -> list[Dict[str, Any]]:
        """Emit any pending stop events at end of stream."""
        results: list[Dict[str, Any]] = []
        if self._thinking_started:
            results.append({"type": "thinking_stop"})
            self._thinking_started = False
        if self._content_started:
            results.append({"type": "content_stop"})
            self._content_started = False
        return results

    @staticmethod
    def _translate_usage(data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "type": "usage",
            "usage": {
                "input_tokens": int(data.get("input_tokens") or 0),
                "output_tokens": int(data.get("output_tokens") or 0),
                "cache_read_tokens": int(data.get("cache_read_tokens") or 0),
                "cache_write_tokens": int(data.get("cache_write_tokens") or 0),
            },
        }
