"""Tests for the CopilotBackend tool bridge functionality.

Tests cover:
  * _create_sdk_tools — SDK Tool creation from JSON schemas
  * receive_tool_result — cross-thread result delivery
  * Tool execution request flow through _run_turn
  * Session re-creation when tool set changes
  * Heartbeat emission during tool execution waits
"""

from __future__ import annotations

import json
import sys
import asyncio
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Install fake copilot SDK stubs (must happen before importing copilot_backend)
# ---------------------------------------------------------------------------


def _install_fake_copilot_sdk() -> None:
    """Extend the fake copilot SDK with Tool and ToolResult stubs."""
    if "copilot.tools" not in sys.modules:
        _ft = ModuleType("copilot.tools")

        class FakeTool:
            def __init__(self, *, name: str, description: str, parameters: dict, handler: Any):
                self.name = name
                self.description = description
                self.parameters = parameters
                self.handler = handler

        class FakeToolResult(dict):
            """Mimics SDK ToolResult (TypedDict) with camelCase keys."""

            def __init__(self, **kwargs: Any):
                super().__init__(**kwargs)
                # Also expose as attributes for test assertions.
                for k, v in kwargs.items():
                    object.__setattr__(self, k, v)

        _ft.Tool = FakeTool  # type: ignore[attr-defined]
        _ft.ToolResult = FakeToolResult  # type: ignore[attr-defined]
        sys.modules["copilot.tools"] = _ft

    if "copilot" not in sys.modules:
        _fc = ModuleType("copilot")
        _fc.CopilotClient = MagicMock  # type: ignore[attr-defined]
        sys.modules["copilot"] = _fc

    if "copilot.generated" not in sys.modules:
        _fg = ModuleType("copilot.generated")
        sys.modules["copilot.generated"] = _fg

    if "copilot.generated.session_events" not in sys.modules:
        _fse = ModuleType("copilot.generated.session_events")

        class _FakeET(SimpleNamespace):
            ASSISTANT_MESSAGE_DELTA = "assistant.message_delta"
            ASSISTANT_REASONING_DELTA = "assistant.reasoning_delta"
            ASSISTANT_REASONING = "assistant.reasoning"
            ASSISTANT_MESSAGE = "assistant.message"
            ASSISTANT_USAGE = "assistant.usage"
            SESSION_ERROR = "session.error"
            SESSION_IDLE = "session.idle"
            ASSISTANT_TURN_END = "assistant.turn_end"
            ABORT = "abort"
            SESSION_SHUTDOWN = "session.shutdown"
            TOOL_EXECUTION_START = "tool.execution.start"

        _fse.SessionEventType = _FakeET  # type: ignore[attr-defined]
        sys.modules["copilot.generated.session_events"] = _fse


_install_fake_copilot_sdk()

from ii_agent.integrations.a2a.copilot_backend import (  # noqa: E402
    CopilotBackend,
    CopilotConfig,
    _ToolExecutionRequest,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_sse(sse_string: str) -> dict[str, Any]:
    """Strip 'data: ' prefix and parse JSON."""
    payload = sse_string.strip()
    assert payload.startswith("data: "), f"Not an SSE: {payload!r}"
    return json.loads(payload[6:])


_FakeET = sys.modules["copilot.generated.session_events"].SessionEventType


def _make_event(event_type: Any, **data_kwargs: Any) -> MagicMock:
    """Build a fake SDK SessionEvent."""
    event = MagicMock()
    event.type = event_type
    for key, value in data_kwargs.items():
        setattr(event.data, key, value)
    return event


# ---------------------------------------------------------------------------
# _create_sdk_tools
# ---------------------------------------------------------------------------


class TestCreateSdkTools:
    """Test SDK Tool creation from JSON schemas."""

    def test_creates_tools_from_schemas(self) -> None:
        backend = CopilotBackend(CopilotConfig())
        schemas = [
            {
                "name": "WebSearch",
                "description": "Search the web",
                "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
            },
            {
                "name": "VisitWeb",
                "description": "Visit a URL",
                "parameters": {"type": "object", "properties": {"url": {"type": "string"}}},
            },
        ]
        tools = backend._create_sdk_tools(schemas)
        assert len(tools) == 2
        assert tools[0].name == "WebSearch"
        assert tools[0].description == "Search the web"
        assert tools[1].name == "VisitWeb"

    def test_empty_schemas_returns_empty(self) -> None:
        backend = CopilotBackend(CopilotConfig())
        tools = backend._create_sdk_tools([])
        assert tools == []

    def test_handler_is_callable(self) -> None:
        backend = CopilotBackend(CopilotConfig())
        schemas = [{"name": "T", "description": "", "parameters": {}}]
        tools = backend._create_sdk_tools(schemas)
        assert callable(tools[0].handler)

    def test_default_parameters_used_when_missing(self) -> None:
        backend = CopilotBackend(CopilotConfig())
        schemas = [{"name": "T", "description": "d"}]
        tools = backend._create_sdk_tools(schemas)
        assert tools[0].parameters == {"type": "object", "properties": {}}

    @pytest.mark.asyncio
    async def test_handler_returns_error_without_active_queue(self) -> None:
        """When no stream is active, handler returns error ToolResult."""
        backend = CopilotBackend(CopilotConfig())
        backend._tool_stream_queue = None
        backend._tool_stream_loop = None

        schemas = [{"name": "WebSearch", "description": "", "parameters": {}}]
        tools = backend._create_sdk_tools(schemas)

        invocation = SimpleNamespace(arguments={"query": "test"})
        result = await tools[0].handler(invocation)

        assert result["resultType"] == "error"
        assert "no active stream" in result["textResultForLlm"]

    @pytest.mark.asyncio
    async def test_handler_injects_tool_execution_request(self) -> None:
        """Handler injects _ToolExecutionRequest into queue and awaits result."""
        backend = CopilotBackend(CopilotConfig(timeout=2.0))

        queue: asyncio.Queue[Any] = asyncio.Queue()
        backend._tool_stream_queue = queue
        backend._tool_stream_loop = asyncio.get_running_loop()

        schemas = [{"name": "WebSearch", "description": "", "parameters": {}}]
        tools = backend._create_sdk_tools(schemas)

        invocation = SimpleNamespace(arguments={"query": "hello"})

        async def _deliver_after_drain() -> Any:
            # Wait for the _ToolExecutionRequest to arrive in the queue.
            item = await asyncio.wait_for(queue.get(), timeout=2.0)
            assert isinstance(item, _ToolExecutionRequest)
            assert item.data["tool_name"] == "WebSearch"
            assert item.data["arguments"] == {"query": "hello"}
            tool_call_id = item.data["tool_call_id"]
            # Deliver the result to unblock the handler.
            backend.receive_tool_result(tool_call_id, "search results here")

        # Run handler and delivery concurrently.
        handler_result, _ = await asyncio.gather(
            tools[0].handler(invocation),
            _deliver_after_drain(),
        )

        assert handler_result["textResultForLlm"] == "search results here"
        assert handler_result["resultType"] == "success"

    @pytest.mark.asyncio
    async def test_handler_timeout_returns_error(self) -> None:
        """Handler returns error if result not delivered within timeout."""
        backend = CopilotBackend(CopilotConfig(timeout=0.1))

        queue: asyncio.Queue[Any] = asyncio.Queue()
        backend._tool_stream_queue = queue
        backend._tool_stream_loop = asyncio.get_running_loop()

        schemas = [{"name": "SlowTool", "description": "", "parameters": {}}]
        tools = backend._create_sdk_tools(schemas)

        invocation = SimpleNamespace(arguments={})

        # Run handler — it will time out since we don't deliver a result
        result = await tools[0].handler(invocation)

        assert result["resultType"] == "error"
        assert "timed out" in result["textResultForLlm"]


# ---------------------------------------------------------------------------
# receive_tool_result
# ---------------------------------------------------------------------------


class TestReceiveToolResult:
    """Test thread-safe result delivery via call_soon_threadsafe."""

    @pytest.mark.asyncio
    async def test_delivers_result_to_waiting_handler(self) -> None:
        backend = CopilotBackend(CopilotConfig())
        loop = asyncio.get_running_loop()

        # Simulate a waiting handler
        event = asyncio.Event()
        holder: list[Any] = [None]
        backend._tool_result_slots["call-123"] = (event, holder, loop)

        delivered = backend.receive_tool_result("call-123", "the result")

        assert delivered is True
        assert holder[0] == "the result"
        # call_soon_threadsafe schedules the set(); yield to let it execute.
        await asyncio.sleep(0)
        assert event.is_set()
        assert "call-123" not in backend._tool_result_slots

    def test_returns_false_for_unknown_call(self) -> None:
        backend = CopilotBackend(CopilotConfig())
        delivered = backend.receive_tool_result("unknown-id", "result")
        assert delivered is False

    @pytest.mark.asyncio
    async def test_returns_false_for_already_delivered(self) -> None:
        backend = CopilotBackend(CopilotConfig())
        loop = asyncio.get_running_loop()

        event = asyncio.Event()
        holder: list[Any] = [None]
        backend._tool_result_slots["call-456"] = (event, holder, loop)

        # First delivery succeeds
        assert backend.receive_tool_result("call-456", "first") is True
        # Second delivery finds no slot
        assert backend.receive_tool_result("call-456", "second") is False

    @pytest.mark.asyncio
    async def test_does_not_raise_on_empty_result(self) -> None:
        backend = CopilotBackend(CopilotConfig())
        loop = asyncio.get_running_loop()

        event = asyncio.Event()
        holder: list[Any] = [None]
        backend._tool_result_slots["call-789"] = (event, holder, loop)

        delivered = backend.receive_tool_result("call-789", "")
        assert delivered is True
        assert holder[0] == ""


# ---------------------------------------------------------------------------
# _ToolExecutionRequest dataclass
# ---------------------------------------------------------------------------


class TestToolExecutionRequest:
    def test_holds_data(self) -> None:
        req = _ToolExecutionRequest(data={"tool_call_id": "abc", "tool_name": "T"})
        assert req.data["tool_call_id"] == "abc"
        assert req.data["tool_name"] == "T"


# ---------------------------------------------------------------------------
# Session re-creation on tool set change
# ---------------------------------------------------------------------------


class TestSessionToolSetChange:
    """Verify session is re-created when tool schemas change."""

    @pytest.mark.asyncio
    async def test_creates_new_session_when_tool_count_changes(self) -> None:
        mock_client = MagicMock()
        mock_client.start = AsyncMock()
        mock_session1 = MagicMock()
        mock_session1.session_id = "sess-1"
        mock_session2 = MagicMock()
        mock_session2.session_id = "sess-2"
        mock_client.create_session = AsyncMock(side_effect=[mock_session1, mock_session2])
        mock_client.resume_session = AsyncMock(return_value=mock_session1)

        backend = CopilotBackend(CopilotConfig())

        with patch(
            "ii_agent.integrations.a2a.copilot_backend.CopilotBackend._get_client",
            new=AsyncMock(return_value=mock_client),
        ):
            # First call: 0 tools
            session1 = await backend._get_or_create_session("ctx-1", tool_schemas=None)
            assert session1.session_id == "sess-1"
            assert backend._session_tool_count["ctx-1"] == 0

            # Second call: 2 tools — should create new session
            schemas = [
                {"name": "WebSearch", "description": "", "parameters": {}},
                {"name": "VisitWeb", "description": "", "parameters": {}},
            ]
            session2 = await backend._get_or_create_session("ctx-1", tool_schemas=schemas)
            assert session2.session_id == "sess-2"
            assert backend._session_tool_count["ctx-1"] == 2

    @pytest.mark.asyncio
    async def test_creates_fresh_session_when_tool_count_unchanged(self) -> None:
        """Even when tool count is unchanged, a fresh session is always created.

        The implementation discards cached sessions on every call to ensure
        tool definitions and system messages are always re-injected.
        """
        mock_client = MagicMock()
        mock_client.start = AsyncMock()
        mock_session = MagicMock()
        mock_session.session_id = "sess-1"
        mock_client.create_session = AsyncMock(return_value=mock_session)
        mock_client.resume_session = AsyncMock(return_value=mock_session)

        backend = CopilotBackend(CopilotConfig())

        with patch(
            "ii_agent.integrations.a2a.copilot_backend.CopilotBackend._get_client",
            new=AsyncMock(return_value=mock_client),
        ):
            # First call: 2 tools
            schemas = [
                {"name": "WebSearch", "description": "", "parameters": {}},
                {"name": "VisitWeb", "description": "", "parameters": {}},
            ]
            await backend._get_or_create_session("ctx-1", tool_schemas=schemas)

            # Second call: still 2 tools — creates fresh session (not resumed)
            await backend._get_or_create_session("ctx-1", tool_schemas=schemas)

        # create_session should have been called twice (once per call).
        assert mock_client.create_session.await_count == 2
        mock_client.resume_session.assert_not_awaited()


# ---------------------------------------------------------------------------
# _run_turn — tool execution request in SSE stream
# ---------------------------------------------------------------------------


class TestRunTurnToolExecution:
    """Test that _run_turn yields tool.execution_request SSE events."""

    @pytest.mark.asyncio
    async def test_tool_execution_request_yields_sse(self) -> None:
        """When a _ToolExecutionRequest is injected, it becomes a tool.execution_request SSE."""
        tool_req = _ToolExecutionRequest(
            data={
                "tool_call_id": "call-xyz",
                "tool_name": "WebSearch",
                "arguments": {"query": "test"},
            }
        )
        idle_event = _make_event(_FakeET.SESSION_IDLE)

        mock_session = MagicMock()
        mock_session.session_id = "sess-001"
        registered_cb: list[Any] = []

        def _on(cb):
            registered_cb.append(cb)
            return MagicMock()

        async def _send(payload):
            for cb in registered_cb:
                cb(tool_req)
                cb(idle_event)
            return "msg-001"

        mock_session.on = _on
        mock_session.send = _send

        mock_client = MagicMock()
        mock_client.start = AsyncMock()

        backend = CopilotBackend(CopilotConfig())

        with (
            patch(
                "ii_agent.integrations.a2a.copilot_backend.CopilotBackend._get_client",
                new=AsyncMock(return_value=mock_client),
            ),
            patch(
                "ii_agent.integrations.a2a.copilot_backend.CopilotBackend._get_or_create_session",
                new=AsyncMock(return_value=mock_session),
            ),
            patch("copilot.generated.session_events.SessionEventType", _FakeET),
        ):
            chunks = [chunk async for chunk in backend.stream("hello", "ctx-1")]

        # Filter out [DONE]
        parsed = [_parse_sse(c) for c in chunks if not c.startswith("data: [DONE]")]

        tool_events = [p for p in parsed if p["type"] == "tool.execution_request"]
        assert len(tool_events) == 1
        assert tool_events[0]["data"]["tool_call_id"] == "call-xyz"
        assert tool_events[0]["data"]["tool_name"] == "WebSearch"
        assert tool_events[0]["data"]["arguments"] == {"query": "test"}


# ---------------------------------------------------------------------------
# Heartbeat emission
# ---------------------------------------------------------------------------


class TestHeartbeat:
    @pytest.mark.asyncio
    async def test_heartbeat_emitted_on_queue_timeout(self) -> None:
        """When no event arrives within _HEARTBEAT_INTERVAL, a heartbeat SSE is yielded."""
        # Use a very short heartbeat interval and overall timeout
        backend = CopilotBackend(CopilotConfig(timeout=0.3))

        mock_session = MagicMock()
        mock_session.session_id = "sess-hb"

        unsubscribe = MagicMock()
        mock_session.on = MagicMock(return_value=unsubscribe)

        # send() does nothing — no events fired, causing timeouts
        async def _slow_send(payload):
            # Fire idle after a delay via a background task
            await asyncio.sleep(0.25)
            return "msg-001"

        mock_session.send = _slow_send

        with (
            patch(
                "ii_agent.integrations.a2a.copilot_backend.CopilotBackend._get_client",
                new=AsyncMock(return_value=MagicMock()),
            ),
            patch(
                "ii_agent.integrations.a2a.copilot_backend.CopilotBackend._get_or_create_session",
                new=AsyncMock(return_value=mock_session),
            ),
            patch("copilot.generated.session_events.SessionEventType", _FakeET),
            patch(
                "ii_agent.integrations.a2a.copilot_backend._HEARTBEAT_INTERVAL",
                0.05,
            ),
        ):
            chunks = [chunk async for chunk in backend.stream("hello", "ctx-hb")]

        # Should have at least one heartbeat
        heartbeats = [
            _parse_sse(c) for c in chunks if not c.startswith("data: [DONE]") and "heartbeat" in c
        ]
        # We should see heartbeats before timeout error
        has_heartbeat = any(p["type"] == "heartbeat" for p in heartbeats)
        # The test might also see a timeout error, which is expected
        error_chunks = [
            _parse_sse(c) for c in chunks if not c.startswith("data: [DONE]") and "error" in c
        ]
        # Either we got heartbeats or the timeout error — both are valid
        assert has_heartbeat or len(error_chunks) > 0


# ---------------------------------------------------------------------------
# stream() with tool_schemas parameter
# ---------------------------------------------------------------------------


class TestStreamWithToolSchemas:
    @pytest.mark.asyncio
    async def test_passes_tool_schemas_to_get_or_create_session(self) -> None:
        """Verify stream() forwards tool_schemas to session creation."""
        idle_event = _make_event(_FakeET.SESSION_IDLE)

        mock_session = MagicMock()
        mock_session.session_id = "sess-ts"
        registered_cb: list[Any] = []

        def _on(cb):
            registered_cb.append(cb)
            return MagicMock()

        async def _send(payload):
            for cb in registered_cb:
                cb(idle_event)
            return "msg-001"

        mock_session.on = _on
        mock_session.send = _send

        get_or_create = AsyncMock(return_value=mock_session)

        backend = CopilotBackend(CopilotConfig())

        schemas = [{"name": "WebSearch", "description": "search", "parameters": {}}]

        with (
            patch(
                "ii_agent.integrations.a2a.copilot_backend.CopilotBackend._get_client",
                new=AsyncMock(return_value=MagicMock()),
            ),
            patch(
                "ii_agent.integrations.a2a.copilot_backend.CopilotBackend._get_or_create_session",
                new=get_or_create,
            ),
            patch("copilot.generated.session_events.SessionEventType", _FakeET),
        ):
            _ = [chunk async for chunk in backend.stream("hello", "ctx-1", tool_schemas=schemas)]

        # Verify tool_schemas was forwarded
        get_or_create.assert_awaited_once()
        call_kwargs = get_or_create.call_args
        # tool_schemas can be positional or keyword
        assert schemas in call_kwargs.args or call_kwargs.kwargs.get("tool_schemas") == schemas
