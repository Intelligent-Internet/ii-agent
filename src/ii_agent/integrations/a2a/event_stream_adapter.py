"""A2A EventStreamAdapter — maps II-Agent realtime events to A2A SSE events.

The adapter takes a queue of :class:`~ii_agent.realtime.events.BaseEvent`
objects (produced by the agent runtime) and translates them into A2A-compatible
:class:`~a2a.types.TaskStatusUpdateEvent` and
:class:`~a2a.types.TaskArtifactUpdateEvent` objects suitable for SSE streaming.

Usage::

    adapter = EventStreamAdapter(
        event_queue=queue,
        context_id="ctx-123",
        task_id="task-456",
    )
    async for a2a_event in adapter.stream():
        yield a2a_event
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Optional

from a2a.types import (
    Artifact,
    Message,
    Part,
    Role,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)

from ii_agent.integrations.a2a.multimodal import content_to_parts
from ii_agent.realtime.events.app_events import EventType

# ---------------------------------------------------------------------------
# Artifact / stream key helpers
# ---------------------------------------------------------------------------

# EventType values that produce artifact (content) update events.
_ARTIFACT_EVENT_TYPES = {
    EventType.RUN_CONTENT,
    EventType.TOOL_CALL_STARTED,
    EventType.TOOL_CALL_COMPLETED,
    EventType.REASONING_DELTA,
    EventType.FILE_EDIT,
}

# Friendly display names for artifact events.
_ARTIFACT_NAMES: dict[str, str] = {
    EventType.RUN_CONTENT: "Agent Response",
    EventType.TOOL_CALL_STARTED: "Tool Call",
    EventType.TOOL_CALL_COMPLETED: "Tool Result",
    EventType.REASONING_DELTA: "Reasoning",
    EventType.FILE_EDIT: "File Edit",
}

# Tool names that produce user-visible message text.
_MESSAGE_TOOL_NAMES = {"message", "message_user", "send_message"}

logger = logging.getLogger(__name__)


class EventStreamAdapter:
    """Translates II-Agent :class:`BaseEvent` objects into A2A streaming events.

    Parameters
    ----------
    event_queue:
        Source of :class:`BaseEvent` objects.  May be ``None`` for testing.
    context_id:
        A2A context identifier (maps to a session).
    task_id:
        A2A task identifier for the current run.
    runtime_trace_enabled:
        When ``True``, every artifact event carries a ``sequence`` counter in
        its ``metadata`` for debugging.  Defaults to ``False``.
    """

    def __init__(
        self,
        event_queue: Any,
        *,
        context_id: Optional[str],
        task_id: Optional[str],
        runtime_trace_enabled: bool = False,
    ) -> None:
        self.event_queue = event_queue
        self._context_id: str = context_id or "unknown_context"
        self._task_id: str = task_id or "unknown_task"
        self._runtime_trace_enabled = runtime_trace_enabled

        # Map stream_key → artifact_id for append logic.
        self._artifact_streams: dict[str, str] = {}
        self._artifact_sequence: int = 0

    @property
    def context_id(self) -> str:
        return self._context_id

    @property
    def task_id(self) -> str:
        return self._task_id

    # ------------------------------------------------------------------
    # Public API (required by PubSubCallbackBase / A2A server)
    # ------------------------------------------------------------------

    def subscribe(self, callback: Any) -> None:
        """No-op: adapter streams events via add_event / publish."""

    def unsubscribe(self, callback: Any) -> None:
        """No-op."""

    async def publish(self, event: Any) -> None:
        """Delegate to add_event (for pubsub compatibility)."""
        await self.add_event(event)

    async def add_event(self, event: Any) -> None:
        """Convert event and enqueue its A2A representation."""
        if self.event_queue is None:
            return
        try:
            converted = self._convert_event(event)
            for a2a_event in converted:
                await self.event_queue.enqueue_event(a2a_event)
        except Exception:
            event_name = getattr(event, "name", type(event).__name__)
            logger.warning(
                "Failed to convert/enqueue event (type=%s): %s",
                event_name,
                event,
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # Event dispatch
    # ------------------------------------------------------------------

    # EventType sets that determine dispatch targets.
    _WORKING_STATUS_TYPES: frozenset[str] = frozenset(
        {
            EventType.CONNECTION_ESTABLISHED,
            EventType.STATUS_UPDATE,
            EventType.AGENT_INITIALIZED,
            EventType.WORKSPACE_INFO,
            EventType.SANDBOX_STATUS,
            EventType.PROCESSING,
        }
    )

    def _convert_event(self, event: Any) -> list:
        """Dispatch an event to the correct translator method."""
        name = getattr(event, "name", "")
        if name in self._WORKING_STATUS_TYPES:
            return self._status_working(event)
        if name == EventType.STREAM_COMPLETE:
            return self._status_complete(event)
        if name == EventType.ERROR:
            return self._status_failed(event)
        if name == EventType.SUB_AGENT_COMPLETED:
            return self._status_sub_agent(event)
        if name == EventType.RUN_INTERRUPTED:
            return self._status_input_required(event)
        # Artifact / content events
        return self._artifact_update(event)

    # ------------------------------------------------------------------
    # Status events
    # ------------------------------------------------------------------

    def _status_working(self, event: Any) -> list[TaskStatusUpdateEvent]:
        text = self._summarize_content(getattr(event, "content", None))
        return [self._build_status_event(TaskState.working, text=text, final=False)]

    def _status_input_required(self, event: Any) -> list[TaskStatusUpdateEvent]:
        text = self._summarize_content(event.content)
        return [self._build_status_event(TaskState.input_required, text=text, final=False)]

    def _status_sub_agent(self, event: Any) -> list[TaskStatusUpdateEvent]:
        text = self._summarize_content(event.content)
        return [self._build_status_event(TaskState.working, text=text, final=False)]

    def _status_complete(self, event: Any) -> list[TaskStatusUpdateEvent]:
        text = self._summarize_content(event.content)
        self._reset_streams()
        return [self._build_status_event(TaskState.completed, text=text, final=True)]

    def _status_failed(self, event: Any) -> list[TaskStatusUpdateEvent]:
        content = event.content if hasattr(event, "content") else {}
        text = self._summarize_content(content) if isinstance(content, dict) else None
        self._reset_streams()
        return [self._build_status_event(TaskState.failed, text=text, final=True)]

    # ------------------------------------------------------------------
    # Artifact events
    # ------------------------------------------------------------------

    def _artifact_update(self, event: Any) -> list[TaskArtifactUpdateEvent]:
        # Try multimodal parts first for events with rich content.
        content = getattr(event, "content", {}) or {}
        parts = self._extract_parts(event, content)

        if not parts:
            return []

        stream_key = self._resolve_stream_key(event) or "default"
        artifact_id, is_first = self._get_or_create_artifact(stream_key)

        metadata: Optional[dict[str, Any]] = None
        if self._runtime_trace_enabled:
            metadata = {"sequence": self._next_sequence()}

        artifact = Artifact(
            artifactId=artifact_id,
            name=self._artifact_name(event),
            parts=parts,
        )
        ev = TaskArtifactUpdateEvent(
            taskId=self._task_id,
            contextId=self._context_id,
            artifact=artifact,
            append=not is_first,
            lastChunk=False,
            metadata=metadata,
        )
        return [ev]

    def _extract_parts(self, event: Any, content: Any) -> list[Part]:
        """Extract A2A Parts from an event, supporting multimodal content.

        Falls back to a single ``TextPart`` when the content is plain text.
        Uses :func:`content_to_parts` for richer content dicts that may
        contain image/file references.
        """
        # For structured content dicts, try multimodal extraction first.
        if isinstance(content, dict):
            # Check for multimodal fields before falling back to text-only.
            has_media = any(
                k in content
                for k in ("image", "image_output", "image_url", "file", "file_output", "file_url")
            )
            if has_media:
                parts = content_to_parts(content)
                if parts:
                    return parts

        # Standard text extraction path.
        text = self._artifact_text(event)
        if not text:
            return []
        return [Part(root=TextPart(text=text))]

    def _get_or_create_artifact(self, stream_key: str) -> tuple[str, bool]:
        """Return ``(artifact_id, is_first_chunk)`` for the given stream key."""
        if stream_key in self._artifact_streams:
            return self._artifact_streams[stream_key], False
        artifact_id = str(uuid.uuid4())
        self._artifact_streams[stream_key] = artifact_id
        return artifact_id, True

    # ------------------------------------------------------------------
    # Text extraction helpers
    # ------------------------------------------------------------------

    def _artifact_text(self, event: Any) -> Optional[str]:
        content = getattr(event, "content", {}) or {}
        name = getattr(event, "name", "")

        if name == EventType.TOOL_CALL_STARTED:
            return self._extract_tool_call_text(content)

        if name == EventType.TOOL_CALL_COMPLETED:
            result = self._extract_tool_result_text(content)
            if result is not None:
                return result
            return self._summarize_content(content)

        if name == EventType.RUN_CONTENT:
            if isinstance(content, dict):
                return content.get("text") or self._summarize_content(content)
            return self._summarize_content(content)

        # REASONING_DELTA, FILE_EDIT, and others
        return self._summarize_content(content)

    def _extract_tool_call_text(self, content: Any) -> Optional[str]:
        if not isinstance(content, dict):
            return None
        display_name = str(content.get("tool_display_name") or content.get("tool_name") or "tool")
        tool_input = content.get("tool_input") or {}
        input_type = ""
        if isinstance(tool_input, dict):
            input_type = tool_input.get("type") or tool_input.get("language") or ""
        suffix = f" ({input_type})" if input_type else ""
        return f"Calling {display_name}{suffix}"

    def _extract_tool_result_text(self, content: Any) -> Optional[str]:
        if not isinstance(content, dict):
            return None
        tool_name = str(content.get("tool_name") or "")
        if tool_name not in _MESSAGE_TOOL_NAMES:
            return None
        result = content.get("result")
        text = self._extract_text_payload(result)
        if text is None:
            tool_input = content.get("tool_input") or {}
            if isinstance(tool_input, dict):
                text = _as_str_or_none(tool_input.get("message"))
        return text

    def _extract_text_payload(self, value: Any) -> Optional[str]:
        """Extract a text string from a result value."""
        if isinstance(value, str):
            return value or None
        if isinstance(value, dict):
            for key in ("text", "message", "action"):
                v = value.get(key)
                if isinstance(v, str) and v:
                    return v
        return None

    def _summarize_content(self, content: Any) -> Optional[str]:
        if content is None:
            return None
        if isinstance(content, str):
            return content
        if isinstance(content, dict):
            for key in ("text", "message", "detail", "status"):
                v = content.get(key)
                if v is not None:
                    return str(v)
            return json.dumps(content)
        return str(content)

    # ------------------------------------------------------------------
    # Artifact/stream metadata helpers
    # ------------------------------------------------------------------

    def _artifact_name(self, event: Any) -> str:
        name = getattr(event, "name", "")
        return _ARTIFACT_NAMES.get(name, str(name).replace("_", " ").title())

    def _resolve_stream_key(self, event: Any) -> Optional[str]:
        name = getattr(event, "name", "")
        if name not in _ARTIFACT_EVENT_TYPES:
            return None
        content = getattr(event, "content", {}) or {}
        if isinstance(content, dict):
            if "stream_key" in content:
                return str(content["stream_key"])
            if "tool_name" in content:
                return f"{name}:{content['tool_name']}"
        return str(name)

    def _metadata(self, content: Any) -> Optional[dict[str, Any]]:
        if not isinstance(content, dict):
            return None
        return {k: v for k, v in content.items() if v is not None} or None

    def _merge_metadata(
        self,
        base: dict[str, Any],
        extra: Optional[dict[str, Any]],
    ) -> Optional[dict[str, Any]]:
        if not base and not extra:
            return None
        result = dict(base)
        if extra:
            result.update(extra)
        return result or None

    # ------------------------------------------------------------------
    # A2A message / status builders
    # ------------------------------------------------------------------

    def _build_message(self, text: str) -> Message:
        return Message(
            messageId=str(uuid.uuid4()),
            role=Role.agent,
            parts=[Part(root=TextPart(text=text))],
        )

    def _build_status_event(
        self,
        state: TaskState,
        *,
        text: Optional[str],
        final: bool,
        metadata: Optional[dict[str, Any]] = None,
    ) -> TaskStatusUpdateEvent:
        message = self._build_message(text) if text else None
        status = TaskStatus(state=state, message=message)
        return TaskStatusUpdateEvent(
            taskId=self._task_id,
            contextId=self._context_id,
            status=status,
            final=final,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Sequence counter
    # ------------------------------------------------------------------

    def _next_sequence(self) -> int:
        self._artifact_sequence += 1
        return self._artifact_sequence

    def _reset_streams(self) -> None:
        self._artifact_streams.clear()


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _as_str_or_none(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value)
    return s if s else None
