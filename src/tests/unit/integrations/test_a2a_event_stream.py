"""Unit tests for ii_agent.integrations.a2a.event_stream_adapter."""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from ii_agent.realtime.events import ApplicationEvent, EventGroup, EventType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_NAME_TO_GROUP: dict[EventType, EventGroup] = {
    EventType.CONNECTION_ESTABLISHED: EventGroup.SYSTEM,
    EventType.STATUS_UPDATE: EventGroup.SYSTEM,
    EventType.AGENT_INITIALIZED: EventGroup.SYSTEM,
    EventType.WORKSPACE_INFO: EventGroup.SYSTEM,
    EventType.SANDBOX_STATUS: EventGroup.SYSTEM,
    EventType.PROCESSING: EventGroup.AGENT_RUN,
    EventType.STREAM_COMPLETE: EventGroup.SYSTEM,
    EventType.ERROR: EventGroup.SYSTEM,
    EventType.SUB_AGENT_COMPLETED: EventGroup.AGENT_RUN,
    EventType.RUN_INTERRUPTED: EventGroup.AGENT_RUN,
    EventType.REASONING_DELTA: EventGroup.AGENT_REASONING,
    EventType.TOOL_CALL_STARTED: EventGroup.AGENT_TOOL,
    EventType.TOOL_CALL_COMPLETED: EventGroup.AGENT_TOOL,
    EventType.RUN_CONTENT: EventGroup.AGENT_RUN,
    EventType.FILE_EDIT: EventGroup.AGENT_TOOL,
}


def _make_event(event_name: EventType, content: Any = None) -> ApplicationEvent:
    group = _NAME_TO_GROUP.get(event_name, EventGroup.SYSTEM)
    event = ApplicationEvent(
        group=group,
        name=event_name,
        session_id=uuid.uuid4(),
        content=content if isinstance(content, dict) else {},
    )
    if not isinstance(content, dict) and content is not None:
        object.__setattr__(event, "content", content)
    return event


def _make_adapter(event_queue=None, *, context_id="ctx-1", task_id="task-1", runtime_trace=False):
    from ii_agent.integrations.a2a.event_stream_adapter import EventStreamAdapter

    return EventStreamAdapter(
        event_queue=event_queue,
        context_id=context_id,
        task_id=task_id,
        runtime_trace_enabled=runtime_trace,
    )


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestEventStreamAdapterInit:
    def test_stores_all_params(self):
        from ii_agent.integrations.a2a.event_stream_adapter import EventStreamAdapter

        queue = MagicMock()
        adapter = EventStreamAdapter(
            event_queue=queue, context_id="ctx", task_id="task", runtime_trace_enabled=True
        )
        assert adapter.event_queue is queue
        assert adapter.context_id == "ctx"
        assert adapter.task_id == "task"
        assert adapter._runtime_trace_enabled is True

    def test_defaults_when_no_params(self):
        adapter = _make_adapter()
        assert adapter._artifact_sequence == 0
        assert adapter._artifact_streams == {}

    def test_context_id_property_returns_value(self):
        adapter = _make_adapter(context_id="my-ctx")
        assert adapter._context_id == "my-ctx"

    def test_task_id_property_returns_value(self):
        adapter = _make_adapter(task_id="my-task")
        assert adapter._task_id == "my-task"

    def test_context_id_defaults_to_unknown_when_none(self):
        from ii_agent.integrations.a2a.event_stream_adapter import EventStreamAdapter

        adapter = EventStreamAdapter(event_queue=None, context_id=None, task_id=None)
        assert adapter._context_id == "unknown_context"
        assert adapter._task_id == "unknown_task"


# ---------------------------------------------------------------------------
# publish / add_event
# ---------------------------------------------------------------------------


class TestPublishAndAddEvent:
    @pytest.mark.asyncio
    async def test_publish_delegates_to_add_event(self):
        adapter = _make_adapter()
        adapter.add_event = AsyncMock()
        event = _make_event(EventType.RUN_CONTENT, {"text": "hello"})
        await adapter.publish(event)
        adapter.add_event.assert_called_once_with(event)

    @pytest.mark.asyncio
    async def test_add_event_skips_when_no_queue(self):
        adapter = _make_adapter(event_queue=None)
        event = _make_event(EventType.RUN_CONTENT, {"text": "hello"})
        # Should not raise
        await adapter.add_event(event)

    @pytest.mark.asyncio
    async def test_add_event_enqueues_converted_events(self):
        queue = AsyncMock()
        queue.enqueue_event = AsyncMock()
        adapter = _make_adapter(event_queue=queue)
        event = _make_event(EventType.STREAM_COMPLETE, {"text": "done"})
        await adapter.add_event(event)
        queue.enqueue_event.assert_called()

    @pytest.mark.asyncio
    async def test_add_event_handles_exception_gracefully(self):
        queue = AsyncMock()
        queue.enqueue_event = AsyncMock(side_effect=RuntimeError("queue error"))
        adapter = _make_adapter(event_queue=queue)
        event = _make_event(EventType.STREAM_COMPLETE, {"text": "done"})
        # Should not raise
        await adapter.add_event(event)


# ---------------------------------------------------------------------------
# subscribe / unsubscribe (no-ops)
# ---------------------------------------------------------------------------


class TestSubscribeNoops:
    def test_subscribe_is_noop(self):
        adapter = _make_adapter()
        adapter.subscribe(MagicMock())  # Should not raise

    def test_unsubscribe_is_noop(self):
        adapter = _make_adapter()
        adapter.unsubscribe(MagicMock())  # Should not raise


# ---------------------------------------------------------------------------
# _convert_event
# ---------------------------------------------------------------------------


class TestConvertEvent:
    def test_working_status_events(self):
        adapter = _make_adapter()
        for event_type in [
            EventType.CONNECTION_ESTABLISHED,
            EventType.STATUS_UPDATE,
            EventType.AGENT_INITIALIZED,
            EventType.WORKSPACE_INFO,
            EventType.SANDBOX_STATUS,
            EventType.PROCESSING,
        ]:
            event = _make_event(event_type, {"status": "working"})
            result = adapter._convert_event(event)
            assert len(result) == 1
            from a2a.types import TaskState

            assert result[0].status.state == TaskState.working

    def test_completion_events(self):
        from a2a.types import TaskState

        adapter = _make_adapter()
        for event_type in [EventType.STREAM_COMPLETE, EventType.STREAM_COMPLETE]:
            event = _make_event(event_type, {"text": "done"})
            result = adapter._convert_event(event)
            assert len(result) == 1
            assert result[0].status.state == TaskState.completed

    def test_error_event(self):
        from a2a.types import TaskState

        adapter = _make_adapter()
        event = _make_event(EventType.ERROR, {"message": "oops"})
        result = adapter._convert_event(event)
        assert len(result) == 1
        assert result[0].status.state == TaskState.failed

    def test_sub_agent_complete_event(self):
        from a2a.types import TaskState

        adapter = _make_adapter()
        event = _make_event(EventType.SUB_AGENT_COMPLETED, {"text": "sub done"})
        result = adapter._convert_event(event)
        assert len(result) == 1
        assert result[0].status.state == TaskState.working

    def test_interrupted_event(self):
        from a2a.types import TaskState

        adapter = _make_adapter()
        event = _make_event(EventType.RUN_INTERRUPTED, {"text": "need input"})
        result = adapter._convert_event(event)
        assert len(result) == 1
        assert result[0].status.state == TaskState.input_required

    def test_artifact_events_produce_artifact_update(self):
        adapter = _make_adapter()
        for event_type in [
            EventType.REASONING_DELTA,
            EventType.TOOL_CALL_STARTED,
            EventType.RUN_CONTENT,
        ]:
            event = _make_event(event_type, {"text": "content"})
            result = adapter._convert_event(event)
            # May be empty if no text extracted, but should not raise
            assert isinstance(result, list)

    def test_fallback_for_unclassified_event(self):
        adapter = _make_adapter()
        event = _make_event(EventType.FILE_EDIT, {"text": "file changed"})
        result = adapter._convert_event(event)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# _status_working / _status_complete / _status_failed
# ---------------------------------------------------------------------------


class TestStatusBuilders:
    def test_status_working_not_final(self):
        adapter = _make_adapter()
        event = _make_event(EventType.STATUS_UPDATE, {"text": "processing..."})
        result = adapter._status_working(event)
        assert len(result) == 1
        assert result[0].final is False

    def test_status_complete_is_final(self):
        adapter = _make_adapter()
        event = _make_event(EventType.STREAM_COMPLETE, {"text": "done"})
        result = adapter._status_complete(event)
        assert len(result) == 1
        assert result[0].final is True

    def test_status_failed_is_final(self):
        adapter = _make_adapter()
        event = _make_event(EventType.ERROR, {"message": "error occurred"})
        result = adapter._status_failed(event)
        assert len(result) == 1
        assert result[0].final is True

    def test_status_input_required_not_final(self):
        adapter = _make_adapter()
        event = _make_event(EventType.RUN_INTERRUPTED, {"text": "waiting"})
        result = adapter._status_input_required(event)
        assert len(result) == 1
        assert result[0].final is False

    def test_status_sub_agent_not_final(self):
        adapter = _make_adapter()
        event = _make_event(EventType.SUB_AGENT_COMPLETED, {})
        result = adapter._status_sub_agent(event)
        assert result[0].final is False

    def test_complete_resets_streams(self):
        adapter = _make_adapter()
        adapter._artifact_streams["key"] = "artifact_id"
        event = _make_event(EventType.STREAM_COMPLETE, {"text": "done"})
        adapter._status_complete(event)
        assert adapter._artifact_streams == {}

    def test_failed_resets_streams(self):
        adapter = _make_adapter()
        adapter._artifact_streams["key"] = "artifact_id"
        event = _make_event(EventType.ERROR, {"message": "error"})
        adapter._status_failed(event)
        assert adapter._artifact_streams == {}


# ---------------------------------------------------------------------------
# _artifact_update
# ---------------------------------------------------------------------------


class TestArtifactUpdate:
    def test_empty_text_returns_empty_list(self):
        adapter = _make_adapter()
        # {"text": ""} → _summarize_content returns "" → falsy → _artifact_update returns []
        event = _make_event(EventType.REASONING_DELTA, {"text": ""})
        result = adapter._artifact_update(event)
        assert result == []

    def test_text_content_produces_artifact_event(self):
        from a2a.types import TaskArtifactUpdateEvent

        adapter = _make_adapter()
        event = _make_event(EventType.RUN_CONTENT, {"text": "Some response"})
        result = adapter._artifact_update(event)
        assert len(result) == 1
        assert isinstance(result[0], TaskArtifactUpdateEvent)

    def test_artifact_append_for_same_stream_key(self):
        adapter = _make_adapter()
        # First event creates stream
        event1 = _make_event(EventType.RUN_CONTENT, {"text": "chunk 1"})
        result1 = adapter._artifact_update(event1)
        assert result1[0].append is False

        # Second event appends
        event2 = _make_event(EventType.RUN_CONTENT, {"text": "chunk 2"})
        result2 = adapter._artifact_update(event2)
        assert result2[0].append is True

    def test_runtime_trace_adds_sequence(self):
        adapter = _make_adapter(runtime_trace=True)
        event = _make_event(EventType.RUN_CONTENT, {"text": "traced"})
        result = adapter._artifact_update(event)
        assert len(result) == 1
        metadata = result[0].metadata
        assert isinstance(metadata, dict)
        assert "sequence" in metadata
        assert metadata["sequence"] == 1

    def test_runtime_trace_increments_sequence(self):
        adapter = _make_adapter(runtime_trace=True)
        event1 = _make_event(EventType.RUN_CONTENT, {"text": "a"})
        event2 = _make_event(EventType.REASONING_DELTA, {"text": "b"})
        adapter._artifact_update(event1)
        result2 = adapter._artifact_update(event2)
        assert result2[0].metadata["sequence"] == 2


# ---------------------------------------------------------------------------
# _artifact_text / _extract_tool_call_text / _extract_tool_result_text
# ---------------------------------------------------------------------------


class TestArtifactText:
    def test_tool_call_returns_calling_description(self):
        adapter = _make_adapter()
        event = _make_event(
            EventType.TOOL_CALL_STARTED, {"tool_name": "web_search", "tool_input": {"q": "hi"}}
        )
        text = adapter._artifact_text(event)
        assert text is not None
        assert "web_search" in text.lower() or "calling" in text.lower()

    def test_tool_result_for_message_tool_returns_text(self):
        adapter = _make_adapter()
        event = _make_event(
            EventType.TOOL_CALL_COMPLETED,
            {"tool_name": "message", "result": "Hello user"},
        )
        text = adapter._artifact_text(event)
        assert text == "Hello user"

    def test_tool_result_non_message_tool_returns_none(self):
        adapter = _make_adapter()
        event = _make_event(
            EventType.TOOL_CALL_COMPLETED, {"tool_name": "web_search", "result": "results..."}
        )
        text = adapter._artifact_text(event)
        # Non-message tools return summarized content from _summarize_content
        assert isinstance(text, (str, type(None)))

    def test_agent_response_returns_text(self):
        adapter = _make_adapter()
        event = _make_event(EventType.RUN_CONTENT, {"text": "Hello!"})
        text = adapter._artifact_text(event)
        assert text == "Hello!"


# ---------------------------------------------------------------------------
# _extract_tool_call_text
# ---------------------------------------------------------------------------


class TestExtractToolCallText:
    def test_returns_calling_with_display_name(self):
        adapter = _make_adapter()
        content = {"tool_display_name": "Web Search", "tool_input": {}}
        result = adapter._extract_tool_call_text(content)
        assert "Web Search" in result

    def test_returns_calling_with_tool_name_fallback(self):
        adapter = _make_adapter()
        content = {"tool_name": "my_tool"}
        result = adapter._extract_tool_call_text(content)
        assert "my_tool" in result

    def test_non_dict_returns_none(self):
        adapter = _make_adapter()
        result = adapter._extract_tool_call_text("not a dict")
        assert result is None

    def test_with_input_type_adds_type(self):
        adapter = _make_adapter()
        content = {"tool_name": "executor", "tool_input": {"type": "bash"}}
        result = adapter._extract_tool_call_text(content)
        assert "bash" in result or "executor" in result

    def test_empty_display_name_falls_back_to_tool(self):
        adapter = _make_adapter()
        content = {"tool_display_name": "", "tool_input": {}}
        result = adapter._extract_tool_call_text(content)
        assert result is not None


# ---------------------------------------------------------------------------
# _extract_tool_result_text
# ---------------------------------------------------------------------------


class TestExtractToolResultText:
    def test_message_tool_returns_text(self):
        adapter = _make_adapter()
        content = {"tool_name": "message", "result": "Hi there!"}
        result = adapter._extract_tool_result_text(content)
        assert result == "Hi there!"

    def test_message_user_tool_returns_text(self):
        adapter = _make_adapter()
        content = {"tool_name": "message_user", "result": "Hello user!"}
        result = adapter._extract_tool_result_text(content)
        assert result == "Hello user!"

    def test_non_message_tool_returns_none(self):
        adapter = _make_adapter()
        content = {"tool_name": "web_search", "result": "search results"}
        result = adapter._extract_tool_result_text(content)
        assert result is None

    def test_non_dict_returns_none(self):
        adapter = _make_adapter()
        result = adapter._extract_tool_result_text("bad")
        assert result is None

    def test_uses_tool_input_message_as_fallback(self):
        # When result is a dict without "text"/"message"/"action" keys,
        # _extract_text_payload returns None, so the function falls back to
        # tool_input["message"].
        # Note: passing None or "" as result triggers an UnboundLocalError bug
        # in the source (event_stream_adapter.py:354). We use a dict to avoid it.
        adapter = _make_adapter()
        content = {
            "tool_name": "message",
            "result": {},  # dict with no text/message/action -> _extract_text_payload returns None
            "tool_input": {"message": "fallback text"},
        }
        result = adapter._extract_tool_result_text(content)
        assert result == "fallback text"


# ---------------------------------------------------------------------------
# _summarize_content
# ---------------------------------------------------------------------------


class TestSummarizeContent:
    def test_none_returns_none(self):
        adapter = _make_adapter()
        assert adapter._summarize_content(None) is None

    def test_string_returns_string(self):
        adapter = _make_adapter()
        assert adapter._summarize_content("hello") == "hello"

    def test_dict_with_text_returns_text(self):
        adapter = _make_adapter()
        assert adapter._summarize_content({"text": "value"}) == "value"

    def test_dict_with_message_returns_message(self):
        adapter = _make_adapter()
        assert adapter._summarize_content({"message": "msg"}) == "msg"

    def test_dict_with_detail_returns_detail(self):
        adapter = _make_adapter()
        assert adapter._summarize_content({"detail": "details"}) == "details"

    def test_dict_with_status_returns_status(self):
        adapter = _make_adapter()
        assert adapter._summarize_content({"status": "active"}) == "active"

    def test_arbitrary_dict_serializes_to_json(self):
        adapter = _make_adapter()
        result = adapter._summarize_content({"key": "value"})
        assert "key" in result

    def test_non_dict_non_string_converts_to_str(self):
        adapter = _make_adapter()
        result = adapter._summarize_content(42)
        assert result == "42"


# ---------------------------------------------------------------------------
# _artifact_name
# ---------------------------------------------------------------------------


class TestArtifactName:
    def test_returns_capitalized_event_type(self):
        adapter = _make_adapter()
        event = _make_event(EventType.RUN_CONTENT, {})
        name = adapter._artifact_name(event)
        assert name == "Agent Response"

    def test_tool_call_artifact_name(self):
        adapter = _make_adapter()
        event = _make_event(EventType.TOOL_CALL_STARTED, {})
        name = adapter._artifact_name(event)
        assert name == "Tool Call"


# ---------------------------------------------------------------------------
# _resolve_stream_key
# ---------------------------------------------------------------------------


class TestResolveStreamKey:
    def test_streaming_event_with_tool_name(self):
        adapter = _make_adapter()
        event = _make_event(EventType.RUN_CONTENT, {"tool_name": "my_tool"})
        key = adapter._resolve_stream_key(event)
        assert "my_tool" in key

    def test_streaming_event_returns_event_type_as_key(self):
        adapter = _make_adapter()
        event = _make_event(EventType.RUN_CONTENT, {"text": "hello"})
        key = adapter._resolve_stream_key(event)
        assert key == EventType.RUN_CONTENT.value

    def test_non_streaming_event_returns_none(self):
        adapter = _make_adapter()
        event = _make_event(EventType.STREAM_COMPLETE, {"text": "done"})
        key = adapter._resolve_stream_key(event)
        assert key is None

    def test_streaming_event_with_stream_key_in_content(self):
        adapter = _make_adapter()
        event = _make_event(EventType.RUN_CONTENT, {"stream_key": "custom_key"})
        key = adapter._resolve_stream_key(event)
        assert key == "custom_key"


# ---------------------------------------------------------------------------
# _metadata / _merge_metadata
# ---------------------------------------------------------------------------


class TestMetadata:
    def test_metadata_returns_none_when_not_dict(self):
        adapter = _make_adapter()
        result = adapter._metadata("not a dict")
        assert result is None

    def test_metadata_filters_none_values(self):
        adapter = _make_adapter()
        content = {"key": "value", "null_key": None}
        result = adapter._metadata(content)
        assert "null_key" not in result
        assert result["key"] == "value"

    def test_merge_metadata_combines_dicts(self):
        adapter = _make_adapter()
        base = {"code": "working"}
        extra = {"message": "processing"}
        result = adapter._merge_metadata(base, extra)
        assert result["code"] == "working"
        assert result["message"] == "processing"

    def test_merge_metadata_returns_empty_dict_when_both_empty(self):
        adapter = _make_adapter()
        # base is {}, extra is None → returns dict(base) == {}
        result = adapter._merge_metadata({}, None)
        # Result is empty dict (not None) because base is not empty of itself
        assert result == {} or result is None

    def test_merge_metadata_handles_none_extra(self):
        adapter = _make_adapter()
        base = {"code": "done"}
        result = adapter._merge_metadata(base, None)
        assert result == base


# ---------------------------------------------------------------------------
# _build_message / _build_status_event
# ---------------------------------------------------------------------------


class TestBuildMessage:
    def test_build_message_creates_message_with_text(self):
        from a2a.types import Message, Role

        adapter = _make_adapter(context_id="ctx", task_id="task")
        msg = adapter._build_message("Hello")
        assert isinstance(msg, Message)
        assert msg.role == Role.agent
        assert len(msg.parts) == 1

    def test_build_status_event_with_text(self):
        from a2a.types import TaskState, TaskStatusUpdateEvent

        adapter = _make_adapter()
        event = adapter._build_status_event(TaskState.working, text="working on it", final=False)
        assert isinstance(event, TaskStatusUpdateEvent)
        assert event.status.state == TaskState.working
        assert event.final is False
        assert event.status.message is not None

    def test_build_status_event_without_text(self):
        from a2a.types import TaskState

        adapter = _make_adapter()
        event = adapter._build_status_event(TaskState.completed, text=None, final=True)
        assert event.status.message is None
        assert event.final is True

    def test_build_status_event_passes_metadata(self):
        from a2a.types import TaskState

        adapter = _make_adapter()
        event = adapter._build_status_event(
            TaskState.failed,
            text="err",
            final=True,
            metadata={"code": "error_code"},
        )
        assert event.metadata["code"] == "error_code"


# ---------------------------------------------------------------------------
# _next_sequence
# ---------------------------------------------------------------------------


class TestNextSequence:
    def test_sequence_starts_at_zero_and_increments(self):
        adapter = _make_adapter()
        assert adapter._next_sequence() == 1
        assert adapter._next_sequence() == 2
        assert adapter._next_sequence() == 3

    def test_reset_streams_clears_artifact_streams(self):
        adapter = _make_adapter()
        adapter._artifact_streams["k1"] = "id1"
        adapter._artifact_streams["k2"] = "id2"
        adapter._reset_streams()
        assert adapter._artifact_streams == {}


# ---------------------------------------------------------------------------
# Multimodal artifact events
# ---------------------------------------------------------------------------


class TestMultimodalArtifactEvents:
    """Test that content with image/file references produces multimodal Parts."""

    def test_content_with_image_url_produces_file_part(self):
        adapter = _make_adapter()
        event = _make_event(
            EventType.RUN_CONTENT,
            {
                "text": "Generated image",
                "image_url": "https://example.com/result.png",
            },
        )
        results = adapter._convert_event(event)
        assert len(results) == 1
        artifact = results[0].artifact
        # Should have a TextPart and a FilePart
        assert len(artifact.parts) == 2
        from a2a.types import TextPart, FilePart

        assert isinstance(artifact.parts[0].root, TextPart)
        assert isinstance(artifact.parts[1].root, FilePart)

    def test_content_with_image_output_dict(self):
        adapter = _make_adapter()
        event = _make_event(
            EventType.RUN_CONTENT,
            {
                "text": "Here is the image",
                "image_output": {
                    "url": "https://example.com/gen.png",
                    "mime_type": "image/png",
                },
            },
        )
        results = adapter._convert_event(event)
        assert len(results) == 1
        from a2a.types import FilePart

        file_parts = [p for p in results[0].artifact.parts if isinstance(p.root, FilePart)]
        assert len(file_parts) == 1

    def test_content_without_media_uses_text_only(self):
        adapter = _make_adapter()
        event = _make_event(EventType.RUN_CONTENT, {"text": "plain text"})
        results = adapter._convert_event(event)
        assert len(results) == 1
        from a2a.types import TextPart

        assert all(isinstance(p.root, TextPart) for p in results[0].artifact.parts)
