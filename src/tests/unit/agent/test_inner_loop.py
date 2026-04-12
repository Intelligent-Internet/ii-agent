from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, AsyncIterator, List, cast

import pytest

from ii_agent.agents.inner_loop import A2AInnerLoop, NativeInnerLoop
from ii_agent.agents.models.metrics import Metrics
from ii_agent.agents.models.base import Model
from ii_agent.agents.models.message import Message
from ii_agent.agents.models.response import ModelResponse
from ii_agent.agents.runs import RunOutput
from ii_agent.core.config.agent import AgentSettings
from ii_agent.integrations.a2a.as_client import A2AStreamEvent, IIAgentA2AClient
from ii_agent.realtime.events.app_events import DelegationFallbackEvent


@dataclass
class _FakeModel:
    id: str = "fake-model"
    name: str = "fake"
    streamed_events: List[Any] = field(default_factory=list)

    async def aresponse_stream(self, **_: Any) -> AsyncIterator[Any]:
        for event in self.streamed_events:
            yield event


class _FakeA2AClient:
    def __init__(self, events: List[A2AStreamEvent] | None = None, fail: bool = False) -> None:
        self._events = events or []
        self._fail = fail

    async def astream(self, **_: Any) -> AsyncIterator[A2AStreamEvent]:
        if self._fail:
            raise RuntimeError("adapter unavailable")
        for event in self._events:
            yield event


@pytest.mark.asyncio
async def test_native_inner_loop_delegates_to_model_stream() -> None:
    strategy = NativeInnerLoop()
    model = _FakeModel(streamed_events=[ModelResponse(content="hello", is_delta=True)])

    events = []
    async for event in strategy.aresponse_stream(model=cast(Model, model), messages=[]):
        events.append(event)

    assert len(events) == 1
    assert isinstance(events[0], ModelResponse)
    assert events[0].content == "hello"


@pytest.mark.asyncio
async def test_a2a_inner_loop_maps_stream_events() -> None:
    strategy = A2AInnerLoop(
        client=cast(
            IIAgentA2AClient,
            _FakeA2AClient(
                events=[
                    A2AStreamEvent(event_type="text_delta", data={"text": "hi "}),
                    A2AStreamEvent(event_type="text_delta", data={"text": "there"}),
                    A2AStreamEvent(
                        event_type="usage",
                        data={"input_tokens": 5, "output_tokens": 7, "total_tokens": 12},
                    ),
                    A2AStreamEvent(event_type="message_complete", data={"text": "hi there"}),
                ]
            ),
        ),
    )

    events = []
    async for event in strategy.aresponse_stream(
        model=cast(Model, _FakeModel()),
        messages=[],
        run_response=cast(
            RunOutput,
            SimpleNamespace(
                session_id="00000000-0000-0000-0000-000000000099",
                run_id="00000000-0000-0000-0000-000000000098",
            ),
        ),
    ):
        events.append(event)

    model_events = [e for e in events if isinstance(e, ModelResponse) and e.delta_status]
    assert [e.delta_status for e in model_events] == [
        "content_started",
        "content_started",
        "content_done",
    ]
    # Streaming deltas must be is_delta=True; content_done must be is_delta=False
    # to prevent the full content from being appended as a delta (text duplication).
    assert model_events[0].is_delta is True
    assert model_events[1].is_delta is True
    assert model_events[2].is_delta is False
    usage = [e for e in events if isinstance(e, ModelResponse) and e.response_usage is not None][0]
    assert isinstance(usage.response_usage, Metrics)
    assert usage.response_usage.total_tokens == 12


@pytest.mark.asyncio
async def test_a2a_inner_loop_falls_back_to_native_on_error() -> None:
    fallback = NativeInnerLoop()
    strategy = A2AInnerLoop(
        client=cast(IIAgentA2AClient, _FakeA2AClient(fail=True)),
        fallback_strategy=fallback,
        fallback_to_native=True,
    )
    model = _FakeModel(streamed_events=[ModelResponse(content="fallback-ok", is_delta=True)])

    events = []
    async for event in strategy.aresponse_stream(model=cast(Model, model), messages=[]):
        events.append(event)

    # The new circuit breaker emits a DelegationFallbackEvent before native fallback events.
    fallback_events = [e for e in events if isinstance(e, DelegationFallbackEvent)]
    model_events = [e for e in events if isinstance(e, ModelResponse)]
    assert len(fallback_events) == 1, "expected one DelegationFallbackEvent"
    assert len(model_events) == 1, "expected one native ModelResponse"
    assert model_events[0].content == "fallback-ok"


def test_agent_settings_a2a_defaults() -> None:
    settings = AgentSettings()
    assert settings.inner_loop_mode == "native"
    assert settings.a2a_agent_url is None
    assert settings.a2a_timeout_seconds == 30.0
    assert settings.a2a_fallback_to_native is True
    assert settings.a2a_context_reuse is True


def test_a2a_client_parse_stream_line_handles_sse_payload() -> None:
    event = IIAgentA2AClient._parse_stream_line('data: {"type":"text_delta","data":{"text":"hi"}}')
    assert event is not None
    assert event.event_type == "text_delta"
    assert event.data["text"] == "hi"


def test_a2a_client_parse_stream_line_ignores_invalid_lines() -> None:
    assert IIAgentA2AClient._parse_stream_line("") is None
    assert IIAgentA2AClient._parse_stream_line("data: [DONE]") is None
    assert IIAgentA2AClient._parse_stream_line("not-json") is None


@pytest.mark.asyncio
async def test_a2a_inner_loop_error_event_raises_provider_error() -> None:
    strategy = A2AInnerLoop(
        client=cast(
            IIAgentA2AClient,
            _FakeA2AClient(events=[A2AStreamEvent(event_type="error", data={"message": "boom"})]),
        ),
        fallback_to_native=False,
    )

    with pytest.raises(Exception, match="boom"):
        async for _ in strategy.aresponse_stream(model=cast(Model, _FakeModel()), messages=[]):
            pass


@pytest.mark.asyncio
async def test_a2a_inner_loop_no_fallback_raises_on_client_failure() -> None:
    strategy = A2AInnerLoop(
        client=cast(IIAgentA2AClient, _FakeA2AClient(fail=True)),
        fallback_to_native=False,
    )

    with pytest.raises(Exception, match="failed without fallback"):
        async for _ in strategy.aresponse_stream(model=cast(Model, _FakeModel()), messages=[]):
            pass


@pytest.mark.asyncio
async def test_a2a_inner_loop_maps_reasoning_and_usage_shapes() -> None:
    strategy = A2AInnerLoop(
        client=cast(
            IIAgentA2AClient,
            _FakeA2AClient(
                events=[
                    A2AStreamEvent(event_type="reasoning_delta", data={"delta": "thinking..."}),
                    A2AStreamEvent(event_type="reasoning_done", data={"content": "done"}),
                    A2AStreamEvent(
                        event_type="assistant.usage", data={"cost": 0.02, "duration": 1.5}
                    ),
                    # content_done with empty content is now skipped (no content to persist).
                    A2AStreamEvent(
                        event_type="content_done", data={"tool_calls": {"bad": "shape"}}
                    ),
                ]
            ),
        ),
    )

    events = []
    async for event in strategy.aresponse_stream(model=cast(Model, _FakeModel()), messages=[]):
        events.append(event)

    reasoning_delta = events[0]
    assert isinstance(reasoning_delta, ModelResponse)
    assert reasoning_delta.delta_status == "reasoning_started"
    assert reasoning_delta.reasoning_content == "thinking..."

    reasoning_done = events[1]
    assert isinstance(reasoning_done, ModelResponse)
    assert reasoning_done.delta_status == "reasoning_done"
    assert reasoning_done.reasoning_content == "done"
    assert reasoning_done.is_delta is False  # must NOT be a delta to avoid duplication

    usage = events[2]
    assert isinstance(usage, ModelResponse)
    assert usage.response_usage is not None
    assert usage.response_usage.cost == 0.02
    assert usage.response_usage.duration == 1.5

    # Empty content_done is skipped — no 4th event.  Tool calls from
    # ASSISTANT_MESSAGE are SDK-internal metadata; the tool bridge handles
    # native tool execution via tool.execution_request events.
    assert len(events) == 3


@pytest.mark.asyncio
async def test_a2a_content_done_is_not_delta() -> None:
    """Regression: content_done events must use is_delta=False.

    When the A2A adapter emits an ``assistant.message`` event with the
    complete response text, it must NOT be treated as a streaming delta.
    Setting is_delta=True caused the agent to append the full content on
    top of the already-accumulated deltas, producing duplicated text in
    the UI.
    """
    strategy = A2AInnerLoop(
        client=cast(
            IIAgentA2AClient,
            _FakeA2AClient(
                events=[
                    A2AStreamEvent(
                        event_type="assistant.message_delta",
                        data={"delta": "Hello "},
                    ),
                    A2AStreamEvent(
                        event_type="assistant.message_delta",
                        data={"delta": "world"},
                    ),
                    A2AStreamEvent(
                        event_type="assistant.message",
                        data={"content": "Hello world"},
                    ),
                ]
            ),
        ),
    )

    events: list[ModelResponse] = []
    async for event in strategy.aresponse_stream(
        model=cast(Model, _FakeModel()),
        messages=[],
    ):
        if isinstance(event, ModelResponse):
            events.append(event)

    # Two deltas + one content_done
    assert len(events) == 3
    assert events[0].is_delta is True
    assert events[0].content == "Hello "
    assert events[1].is_delta is True
    assert events[1].content == "world"
    assert events[2].is_delta is False
    assert events[2].content == "Hello world"


@pytest.mark.asyncio
async def test_a2a_reasoning_done_is_not_delta() -> None:
    """Regression: reasoning_done events must use is_delta=False.

    When the A2A adapter emits an ``assistant.reasoning`` event with the
    complete reasoning text, it must NOT be treated as a streaming delta.
    Setting is_delta=True caused the agent to append the full reasoning on
    top of the already-accumulated deltas, producing doubled reasoning text,
    and — because the resulting event remained transient — the reasoning was
    not persisted to the application_events table for session replay.
    """
    strategy = A2AInnerLoop(
        client=cast(
            IIAgentA2AClient,
            _FakeA2AClient(
                events=[
                    A2AStreamEvent(
                        event_type="reasoning_delta",
                        data={"delta": "Let me "},
                    ),
                    A2AStreamEvent(
                        event_type="reasoning_delta",
                        data={"delta": "think"},
                    ),
                    A2AStreamEvent(
                        event_type="reasoning_done",
                        data={"content": "Let me think"},
                    ),
                ]
            ),
        ),
    )

    events: list[ModelResponse] = []
    async for event in strategy.aresponse_stream(
        model=cast(Model, _FakeModel()),
        messages=[],
    ):
        if isinstance(event, ModelResponse):
            events.append(event)

    # Two reasoning deltas + one reasoning_done
    assert len(events) == 3
    assert events[0].is_delta is True
    assert events[0].reasoning_content == "Let me "
    assert events[1].is_delta is True
    assert events[1].reasoning_content == "think"
    assert events[2].is_delta is False
    assert events[2].reasoning_content == "Let me think"
    assert events[2].delta_status == "reasoning_done"


def test_a2a_inner_loop_resolve_context_id_fallback_order() -> None:
    assert A2AInnerLoop._resolve_context_id(None) == "default"
    assert (
        A2AInnerLoop._resolve_context_id(cast(RunOutput, SimpleNamespace(session_id="sess-1")))
        == "sess-1"
    )
    assert (
        A2AInnerLoop._resolve_context_id(cast(RunOutput, SimpleNamespace(run_id="run-1")))
        == "run-1"
    )
    assert A2AInnerLoop._resolve_context_id(cast(RunOutput, SimpleNamespace())) == "default"


def test_a2a_inner_loop_ignores_unknown_event_types() -> None:
    assert A2AInnerLoop._map_event(A2AStreamEvent(event_type="unknown", data={})) is None


def test_a2a_client_requires_url_or_factory() -> None:
    with pytest.raises(ValueError, match="Either agent_url or url_factory"):
        IIAgentA2AClient()


@pytest.mark.asyncio
async def test_a2a_client_lazy_url_factory_resolves_on_first_call() -> None:
    resolved: list[str] = []

    async def _factory() -> str:
        resolved.append("called")
        return "http://sandbox-host:12345"

    client = IIAgentA2AClient(url_factory=_factory)
    # Property returns None before resolution
    assert client.agent_url is None

    url = await client._resolve_url()
    assert url == "http://sandbox-host:12345"
    # Cached — factory not called again
    url2 = await client._resolve_url()
    assert url2 == url
    assert len(resolved) == 1
    # Property reflects resolved URL
    assert client.agent_url == "http://sandbox-host:12345"


def test_agent_settings_tool_allowlist_helpers() -> None:
    settings = AgentSettings(auto_approve_tools=False)

    assert settings.is_tool_allowed("shell") is False
    settings.add_allowed_tool("shell")
    assert settings.is_tool_allowed("shell") is True

    settings.remove_allowed_tool("shell")
    assert settings.is_tool_allowed("shell") is False

    settings.add_allowed_tool("a")
    settings.add_allowed_tool("b")
    settings.clear_allowed_tools()
    assert settings.allow_tools == set()


# ---------------------------------------------------------------------------
# A2AInnerLoop — compaction authority event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a2a_inner_loop_emits_compaction_authority_event() -> None:
    """When a session_id is present, a CompactionAuthorityEvent should be yielded."""
    from ii_agent.realtime.events.app_events import CompactionAuthorityEvent
    from ii_agent.chat.application.compaction_lock import _locks

    # Clear lock registry before test
    _locks.clear()

    session_id = "00000000-0000-0000-0000-000000000001"
    strategy = A2AInnerLoop(
        client=cast(
            IIAgentA2AClient,
            _FakeA2AClient(events=[A2AStreamEvent(event_type="text_delta", data={"text": "hi"})]),
        ),
    )

    events = []
    async for event in strategy.aresponse_stream(
        model=cast(Model, _FakeModel()),
        messages=[],
        run_response=cast(
            RunOutput,
            SimpleNamespace(session_id=session_id, run_id="00000000-0000-0000-0000-000000000010"),
        ),
    ):
        events.append(event)

    authority_events = [e for e in events if isinstance(e, CompactionAuthorityEvent)]
    assert len(authority_events) == 1
    assert authority_events[0].authority == "a2a"
    assert authority_events[0].compaction_locked is True

    _locks.clear()


@pytest.mark.asyncio
async def test_a2a_inner_loop_releases_compaction_lock_after_stream() -> None:
    """The compaction lock should be released after the stream completes."""
    from ii_agent.chat.application.compaction_lock import _locks, is_compaction_locked
    import uuid

    _locks.clear()

    session_uuid = uuid.UUID("00000000-0000-0000-0000-000000000002")
    strategy = A2AInnerLoop(
        client=cast(
            IIAgentA2AClient,
            _FakeA2AClient(events=[A2AStreamEvent(event_type="text_delta", data={"text": "ok"})]),
        ),
    )

    async for _ in strategy.aresponse_stream(
        model=cast(Model, _FakeModel()),
        messages=[],
        run_response=cast(
            RunOutput,
            SimpleNamespace(
                session_id=str(session_uuid), run_id="00000000-0000-0000-0000-000000000020"
            ),
        ),
    ):
        pass

    # Lock should be released after stream ends.
    assert not is_compaction_locked(session_uuid)

    _locks.clear()


@pytest.mark.asyncio
async def test_a2a_inner_loop_no_lock_when_no_session_id() -> None:
    """No compaction event should be emitted when session_id is absent."""
    from ii_agent.realtime.events.app_events import CompactionAuthorityEvent

    strategy = A2AInnerLoop(
        client=cast(
            IIAgentA2AClient,
            _FakeA2AClient(events=[A2AStreamEvent(event_type="text_delta", data={"text": "hi"})]),
        ),
    )

    events = []
    async for event in strategy.aresponse_stream(
        model=cast(Model, _FakeModel()),
        messages=[],
        run_response=None,
    ):
        events.append(event)

    authority_events = [e for e in events if isinstance(e, CompactionAuthorityEvent)]
    assert len(authority_events) == 0


# ---------------------------------------------------------------------------
# A2AInnerLoop — cancellation during stream
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a2a_inner_loop_cancel_propagates_exception() -> None:
    """RunCancelledException should propagate through the A2A stream."""
    from unittest.mock import patch
    from ii_agent.core.redis.cancel import RunCancelledException

    call_count = 0

    async def _raise_cancelled(run_id: str) -> None:
        nonlocal call_count
        call_count += 1
        # Cancel on the second event
        if call_count >= 2:
            raise RunCancelledException(f"Run {run_id} was cancelled")

    strategy = A2AInnerLoop(
        client=cast(
            IIAgentA2AClient,
            _FakeA2AClient(
                events=[
                    A2AStreamEvent(event_type="text_delta", data={"text": "first "}),
                    A2AStreamEvent(event_type="text_delta", data={"text": "second"}),
                    A2AStreamEvent(event_type="text_delta", data={"text": "third"}),
                ]
            ),
        ),
        fallback_to_native=True,  # Must NOT fall back on cancel
    )

    with patch("ii_agent.agents.inner_loop.raise_if_cancelled", side_effect=_raise_cancelled):
        with pytest.raises(RunCancelledException):
            async for _ in strategy.aresponse_stream(
                model=cast(Model, _FakeModel()),
                messages=[],
                run_response=cast(
                    RunOutput,
                    SimpleNamespace(
                        session_id="00000000-0000-0000-0000-000000000099",
                        run_id="00000000-0000-0000-0000-0000000c0001",
                    ),
                ),
            ):
                pass


@pytest.mark.asyncio
async def test_a2a_inner_loop_cancel_does_not_trigger_fallback() -> None:
    """Cancellation must NOT fall back to native — it must re-raise."""
    from unittest.mock import patch
    from ii_agent.core.redis.cancel import RunCancelledException

    async def _always_cancel(run_id: str) -> None:
        raise RunCancelledException(f"Run {run_id} was cancelled")

    fallback = NativeInnerLoop()
    strategy = A2AInnerLoop(
        client=cast(
            IIAgentA2AClient,
            _FakeA2AClient(events=[A2AStreamEvent(event_type="text_delta", data={"text": "hi"})]),
        ),
        fallback_strategy=fallback,
        fallback_to_native=True,
    )

    with patch("ii_agent.agents.inner_loop.raise_if_cancelled", side_effect=_always_cancel):
        events = []
        with pytest.raises(RunCancelledException):
            async for event in strategy.aresponse_stream(
                model=cast(Model, _FakeModel(streamed_events=[ModelResponse(content="native")])),
                messages=[],
                run_response=cast(
                    RunOutput,
                    SimpleNamespace(
                        session_id="00000000-0000-0000-0000-0000000c0002",
                        run_id="00000000-0000-0000-0000-0000000c0003",
                    ),
                ),
            ):
                events.append(event)

    # No DelegationFallbackEvent — native fallback must NOT have triggered
    fallback_events = [e for e in events if isinstance(e, DelegationFallbackEvent)]
    assert len(fallback_events) == 0, "cancellation must not trigger native fallback"


@pytest.mark.asyncio
async def test_a2a_inner_loop_cancel_calls_adapter_cancel() -> None:
    """When cancelled, the inner loop should call cancel_task on the adapter."""
    from unittest.mock import patch
    from ii_agent.core.redis.cancel import RunCancelledException

    cancel_called = []

    class _TrackingClient:
        async def astream(self, **_: Any) -> AsyncIterator[A2AStreamEvent]:
            yield A2AStreamEvent(event_type="session.task_id", data={"task_id": "adapter-task-42"})
            yield A2AStreamEvent(event_type="text_delta", data={"text": "hi"})

        async def post_tool_result(self, **kw: Any) -> bool:
            return True

        async def cancel_task(self, task_id: str) -> bool:
            cancel_called.append(task_id)
            return True

    async def _always_cancel(run_id: str) -> None:
        raise RunCancelledException(f"Run {run_id} was cancelled")

    strategy = A2AInnerLoop(
        client=cast(IIAgentA2AClient, _TrackingClient()),
        fallback_to_native=False,
    )

    # The first event (session.task_id) won't trigger cancel since it comes
    # before the text_delta. But raise_if_cancelled fires on text_delta.
    call_count = 0

    async def _cancel_on_second(run_id: str) -> None:
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            raise RunCancelledException(f"Run {run_id} was cancelled")

    with patch("ii_agent.agents.inner_loop.raise_if_cancelled", side_effect=_cancel_on_second):
        with pytest.raises(RunCancelledException):
            async for _ in strategy.aresponse_stream(
                model=cast(Model, _FakeModel()),
                messages=[],
                run_response=cast(
                    RunOutput,
                    SimpleNamespace(
                        session_id="00000000-0000-0000-0000-0000000c0004",
                        run_id="00000000-0000-0000-0000-0000000c0005",
                    ),
                ),
            ):
                pass

    assert cancel_called == ["adapter-task-42"], "adapter cancel_task should have been called"


# ---------------------------------------------------------------------------
# A2AInnerLoop — session.task_id event handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a2a_inner_loop_captures_task_id_but_does_not_yield() -> None:
    """session.task_id events should be consumed (not yielded) by the inner loop."""
    strategy = A2AInnerLoop(
        client=cast(
            IIAgentA2AClient,
            _FakeA2AClient(
                events=[
                    A2AStreamEvent(event_type="session.task_id", data={"task_id": "task-abc"}),
                    A2AStreamEvent(event_type="text_delta", data={"text": "hello"}),
                ]
            ),
        ),
    )

    events = []
    async for event in strategy.aresponse_stream(
        model=cast(Model, _FakeModel()),
        messages=[],
    ):
        events.append(event)

    # The text_delta is yielded, then a synthetic finalization event because
    # there was no content_done with the final text.
    model_events = [e for e in events if isinstance(e, ModelResponse)]
    assert len(model_events) == 2
    assert model_events[0].content == "hello"
    assert model_events[0].is_delta is True
    # Synthetic finalization
    assert model_events[1].content == "hello"
    assert model_events[1].is_delta is False


@pytest.mark.asyncio
async def test_a2a_inner_loop_no_cancel_when_no_run_id() -> None:
    """When run_response is None, raise_if_cancelled should not be called."""
    from unittest.mock import patch

    cancel_calls = []

    async def _track_cancel(run_id: str) -> None:
        cancel_calls.append(run_id)

    strategy = A2AInnerLoop(
        client=cast(
            IIAgentA2AClient,
            _FakeA2AClient(events=[A2AStreamEvent(event_type="text_delta", data={"text": "hi"})]),
        ),
    )

    with patch("ii_agent.agents.inner_loop.raise_if_cancelled", side_effect=_track_cancel):
        async for _ in strategy.aresponse_stream(
            model=cast(Model, _FakeModel()),
            messages=[],
            run_response=None,
        ):
            pass

    assert cancel_calls == [], "raise_if_cancelled should not be called without run_id"


# ---------------------------------------------------------------------------
# A2AInnerLoop — system message forwarding
# ---------------------------------------------------------------------------


class _CapturingA2AClient:
    """Fake A2A client that captures the metadata passed to astream()."""

    def __init__(self, events: List[A2AStreamEvent] | None = None) -> None:
        self._events = events or []
        self.last_metadata: dict[str, Any] | None = None

    async def astream(self, **kwargs: Any) -> AsyncIterator[A2AStreamEvent]:
        self.last_metadata = kwargs.get("metadata")
        for event in self._events:
            yield event


@pytest.mark.asyncio
async def test_a2a_inner_loop_forwards_system_message_in_metadata() -> None:
    """The system message from the messages list must be forwarded via metadata."""
    client = _CapturingA2AClient(
        events=[A2AStreamEvent(event_type="text_delta", data={"text": "ok"})]
    )
    strategy = A2AInnerLoop(client=cast(IIAgentA2AClient, client))

    messages = [
        Message(role="system", content="You are a helpful agent with BROWSER_RULES..."),
        Message(role="user", content="Go to walmart.ca"),
    ]

    async for _ in strategy.aresponse_stream(
        model=cast(Model, _FakeModel()),
        messages=messages,
    ):
        pass

    assert client.last_metadata is not None
    assert client.last_metadata["system_message"] == "You are a helpful agent with BROWSER_RULES..."


@pytest.mark.asyncio
async def test_a2a_inner_loop_forwards_none_when_no_system_message() -> None:
    """When there is no system message, metadata.system_message should be None."""
    client = _CapturingA2AClient(
        events=[A2AStreamEvent(event_type="text_delta", data={"text": "ok"})]
    )
    strategy = A2AInnerLoop(client=cast(IIAgentA2AClient, client))

    messages = [Message(role="user", content="hello")]

    async for _ in strategy.aresponse_stream(
        model=cast(Model, _FakeModel()),
        messages=messages,
    ):
        pass

    assert client.last_metadata is not None
    assert client.last_metadata["system_message"] is None


# ---------------------------------------------------------------------------
# Empty content_done and synthetic finalization tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a2a_empty_content_done_skipped() -> None:
    """When ASSISTANT_MESSAGE has empty content, _map_event returns None.

    The Copilot SDK sometimes sends ASSISTANT_MESSAGE with content=""
    after streaming all text via ASSISTANT_MESSAGE_DELTA.  This must not
    replace the accumulated delta text with an empty string.
    """
    strategy = A2AInnerLoop(
        client=cast(
            IIAgentA2AClient,
            _FakeA2AClient(
                events=[
                    A2AStreamEvent(
                        event_type="assistant.message_delta",
                        data={"delta": "Hello "},
                    ),
                    A2AStreamEvent(
                        event_type="assistant.message_delta",
                        data={"delta": "world"},
                    ),
                    # ASSISTANT_MESSAGE with empty content (end-of-turn signal only)
                    A2AStreamEvent(
                        event_type="assistant.message",
                        data={"content": "", "tool_calls": []},
                    ),
                ]
            ),
        ),
    )

    events: list[ModelResponse] = []
    async for event in strategy.aresponse_stream(
        model=cast(Model, _FakeModel()),
        messages=[],
    ):
        if isinstance(event, ModelResponse):
            events.append(event)

    # Two deltas + one synthetic finalization (NOT the empty content_done)
    assert len(events) == 3
    assert events[0].is_delta is True
    assert events[0].content == "Hello "
    assert events[1].is_delta is True
    assert events[1].content == "world"
    # Synthetic finalization carries the accumulated text
    assert events[2].is_delta is False
    assert events[2].content == "Hello world"
    assert events[2].delta_status == "content_done"


@pytest.mark.asyncio
async def test_a2a_synthetic_finalization_when_no_content_done() -> None:
    """When no non-delta content event arrives, synthetic finalization is emitted.

    This ensures the accumulated delta text is persisted to the database
    even when the Copilot SDK's ASSISTANT_MESSAGE event has empty content.
    """
    strategy = A2AInnerLoop(
        client=cast(
            IIAgentA2AClient,
            _FakeA2AClient(
                events=[
                    A2AStreamEvent(
                        event_type="assistant.message_delta",
                        data={"delta": "abc"},
                    ),
                    A2AStreamEvent(
                        event_type="assistant.message_delta",
                        data={"delta": "def"},
                    ),
                    # No assistant.message event at all
                ]
            ),
        ),
    )

    events: list[ModelResponse] = []
    async for event in strategy.aresponse_stream(
        model=cast(Model, _FakeModel()),
        messages=[],
    ):
        if isinstance(event, ModelResponse):
            events.append(event)

    # Two deltas + synthetic finalization
    assert len(events) == 3
    finalization = events[2]
    assert finalization.is_delta is False
    assert finalization.content == "abcdef"
    assert finalization.delta_status == "content_done"


@pytest.mark.asyncio
async def test_a2a_no_synthetic_finalization_when_content_done_present() -> None:
    """When a non-empty content_done arrives, no synthetic finalization is needed."""
    strategy = A2AInnerLoop(
        client=cast(
            IIAgentA2AClient,
            _FakeA2AClient(
                events=[
                    A2AStreamEvent(
                        event_type="assistant.message_delta",
                        data={"delta": "hi"},
                    ),
                    A2AStreamEvent(
                        event_type="assistant.message",
                        data={"content": "hi"},
                    ),
                ]
            ),
        ),
    )

    events: list[ModelResponse] = []
    async for event in strategy.aresponse_stream(
        model=cast(Model, _FakeModel()),
        messages=[],
    ):
        if isinstance(event, ModelResponse):
            events.append(event)

    # One delta + one real content_done (no synthetic)
    assert len(events) == 2
    assert events[0].is_delta is True
    assert events[1].is_delta is False
    assert events[1].content == "hi"
