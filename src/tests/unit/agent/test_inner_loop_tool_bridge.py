"""Tests for A2AInnerLoop tool bridging functionality.

Tests cover:
  * Tool schema serialization and metadata transport
  * Heartbeat event filtering
  * Tool execution request handling
  * _execute_bridged_tool — Function matching, async/sync execution, errors
  * post_tool_result delivery via client
  * tool_call_started / tool_call_completed event emission
  * FunctionCall.aexecute() integration (pre_hook, entrypoint arg injection, post_hook)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, List, cast
from unittest.mock import AsyncMock

import pytest

from ii_agent.agents.inner_loop import A2AInnerLoop
from ii_agent.agents.models.base import Model
from ii_agent.agents.models.response import ModelResponse, ModelResponseEvent
from ii_agent.integrations.a2a.as_client import A2AStreamEvent, IIAgentA2AClient
from ii_agent.agents.tools.function import Function


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class _FakeModel:
    id: str = "fake-model"
    name: str = "fake"
    streamed_events: List[Any] = field(default_factory=list)

    async def aresponse_stream(self, **_: Any) -> AsyncIterator[Any]:
        for event in self.streamed_events:
            yield event


class _FakeA2AClient:
    """Fake A2A client that yields configurable events."""

    def __init__(
        self,
        events: List[A2AStreamEvent] | None = None,
        fail: bool = False,
    ) -> None:
        self._events = events or []
        self._fail = fail
        self.posted_results: list[dict[str, Any]] = []

    async def astream(self, **kwargs: Any) -> AsyncIterator[A2AStreamEvent]:
        self._last_metadata = kwargs.get("metadata", {})
        if self._fail:
            raise RuntimeError("adapter unavailable")
        for event in self._events:
            yield event

    async def post_tool_result(self, *, tool_call_id: str, result: str) -> bool:
        self.posted_results.append({"tool_call_id": tool_call_id, "result": result})
        return True


def _make_function(
    name: str,
    entrypoint: Any = None,
    description: str = "",
    parameters: dict | None = None,
) -> Function:
    """Build a minimal Function with the fields needed by _execute_bridged_tool."""
    fn = Function(
        name=name,
        description=description,
        parameters=parameters or {"type": "object", "properties": {}},
    )
    fn.entrypoint = entrypoint
    return fn


# ---------------------------------------------------------------------------
# Tool schema metadata transport
# ---------------------------------------------------------------------------


class TestToolSchemaMetadataTransport:
    """Verify that tool schemas are serialized into A2A metadata."""

    @pytest.mark.asyncio
    async def test_tools_serialized_into_metadata(self) -> None:
        """When tools are provided, native_tool_schemas appears in metadata."""
        captured_metadata: list[dict] = []

        class _CapturingClient:
            async def astream(self, **kwargs: Any) -> AsyncIterator[A2AStreamEvent]:
                captured_metadata.append(kwargs.get("metadata", {}))
                yield A2AStreamEvent(event_type="text_delta", data={"text": "ok"})

            async def post_tool_result(self, **kw: Any) -> bool:
                return True

        strategy = A2AInnerLoop(client=cast(IIAgentA2AClient, _CapturingClient()))

        tools = [
            _make_function("WebSearch", description="Search"),
            _make_function("Bash"),  # CLI-native — should be excluded
        ]

        async for _ in strategy.aresponse_stream(
            model=cast(Model, _FakeModel()),
            messages=[],
            tools=tools,
        ):
            pass

        assert len(captured_metadata) == 1
        schemas = captured_metadata[0].get("native_tool_schemas", [])
        names = [s["name"] for s in schemas]
        assert "WebSearch" in names
        # Bash is CLI-native and should be excluded by serialize_tool_schemas
        assert "Bash" not in names

    @pytest.mark.asyncio
    async def test_no_tools_sends_empty_schemas(self) -> None:
        captured_metadata: list[dict] = []

        class _CapturingClient:
            async def astream(self, **kwargs: Any) -> AsyncIterator[A2AStreamEvent]:
                captured_metadata.append(kwargs.get("metadata", {}))
                yield A2AStreamEvent(event_type="text_delta", data={"text": "ok"})

            async def post_tool_result(self, **kw: Any) -> bool:
                return True

        strategy = A2AInnerLoop(client=cast(IIAgentA2AClient, _CapturingClient()))

        async for _ in strategy.aresponse_stream(
            model=cast(Model, _FakeModel()),
            messages=[],
            tools=None,
        ):
            pass

        schemas = captured_metadata[0].get("native_tool_schemas", [])
        assert schemas == []


# ---------------------------------------------------------------------------
# Heartbeat filtering
# ---------------------------------------------------------------------------


class TestHeartbeatFiltering:
    """Verify that heartbeat events are silently discarded."""

    @pytest.mark.asyncio
    async def test_heartbeat_events_discarded(self) -> None:
        events_from_adapter = [
            A2AStreamEvent(event_type="text_delta", data={"text": "start "}),
            A2AStreamEvent(event_type="heartbeat", data={"status": "waiting"}),
            A2AStreamEvent(event_type="heartbeat", data={"status": "waiting"}),
            A2AStreamEvent(event_type="text_delta", data={"text": "end"}),
        ]

        strategy = A2AInnerLoop(
            client=cast(IIAgentA2AClient, _FakeA2AClient(events=events_from_adapter)),
        )

        events = []
        async for event in strategy.aresponse_stream(
            model=cast(Model, _FakeModel()),
            messages=[],
        ):
            events.append(event)

        # Only text_delta events should appear (heartbeats filtered out)
        # The synthetic finalization also yields a content_done event.
        model_events = [e for e in events if isinstance(e, ModelResponse)]
        assert len(model_events) == 3
        assert model_events[0].content == "start "
        assert model_events[1].content == "end"
        assert model_events[2].delta_status == "content_done"
        assert model_events[2].is_delta is False


# ---------------------------------------------------------------------------
# Tool execution request handling
# ---------------------------------------------------------------------------


class TestToolExecutionRequestHandling:
    """Test _handle_tool_execution_request and the event stream interception."""

    @pytest.mark.asyncio
    async def test_tool_execution_request_dispatches_and_posts_result(self) -> None:
        """When tool.execution_request arrives, the tool is executed and result posted."""

        async def _fake_search(query: str) -> str:
            return f"results for {query}"

        tools = [_make_function("WebSearch", entrypoint=_fake_search)]
        client = _FakeA2AClient(
            events=[
                A2AStreamEvent(
                    event_type="tool.execution_request",
                    data={
                        "tool_call_id": "call-001",
                        "tool_name": "WebSearch",
                        "arguments": {"query": "python docs"},
                    },
                ),
                A2AStreamEvent(event_type="text_delta", data={"text": "done"}),
            ],
        )

        strategy = A2AInnerLoop(client=cast(IIAgentA2AClient, client))

        events = []
        async for event in strategy.aresponse_stream(
            model=cast(Model, _FakeModel()),
            messages=[],
            tools=tools,
        ):
            events.append(event)

        # Should get tool_call_started + tool_call_completed + text delta + content_done
        model_events = [e for e in events if isinstance(e, ModelResponse)]
        assert len(model_events) == 4

        # First event: tool_call_started
        assert model_events[0].event == ModelResponseEvent.tool_call_started.value
        assert model_events[0].tool_executions[0].tool_name == "WebSearch"

        # Second event: tool_call_completed
        assert model_events[1].event == ModelResponseEvent.tool_call_completed.value
        assert model_events[1].tool_executions[0].tool_name == "WebSearch"
        assert model_events[1].tool_executions[0].result == "results for python docs"

        # Third event: text delta
        assert model_events[2].content == "done"

        # Result should have been posted back
        assert len(client.posted_results) == 1
        assert client.posted_results[0]["tool_call_id"] == "call-001"
        assert client.posted_results[0]["result"] == "results for python docs"

    @pytest.mark.asyncio
    async def test_tool_not_found_posts_error(self) -> None:
        """When tool is not found, an error message is posted as result."""
        client = _FakeA2AClient(
            events=[
                A2AStreamEvent(
                    event_type="tool.execution_request",
                    data={
                        "tool_call_id": "call-002",
                        "tool_name": "NonExistentTool",
                        "arguments": {},
                    },
                ),
                A2AStreamEvent(event_type="text_delta", data={"text": "ok"}),
            ],
        )

        strategy = A2AInnerLoop(client=cast(IIAgentA2AClient, client))

        events = []
        async for event in strategy.aresponse_stream(
            model=cast(Model, _FakeModel()),
            messages=[],
            tools=[_make_function("WebSearch")],
        ):
            events.append(event)

        assert len(client.posted_results) == 1
        assert "not found" in client.posted_results[0]["result"]

        # No tool events emitted for missing tool (only text delta + content_done)
        model_events = [e for e in events if isinstance(e, ModelResponse)]
        text_events = [
            e for e in model_events if e.event == ModelResponseEvent.assistant_response.value
        ]
        assert len(text_events) == 2


# ---------------------------------------------------------------------------
# _execute_bridged_tool
# ---------------------------------------------------------------------------


class TestExecuteBridgedTool:
    """Test the _execute_bridged_tool instance method."""

    def _make_strategy(self) -> A2AInnerLoop:
        return A2AInnerLoop(client=cast(IIAgentA2AClient, _FakeA2AClient()))

    @pytest.mark.asyncio
    async def test_executes_async_entrypoint(self) -> None:
        async def _async_tool(query: str) -> str:
            return f"async result: {query}"

        tools = [_make_function("AsyncTool", entrypoint=_async_tool)]
        strategy = self._make_strategy()
        result, events = await strategy._execute_bridged_tool(
            "AsyncTool", {"query": "hello"}, tools, "call-async"
        )
        assert result == "async result: hello"
        # Should have started + completed events
        assert len(events) == 2
        assert events[0].event == ModelResponseEvent.tool_call_started.value
        assert events[1].event == ModelResponseEvent.tool_call_completed.value

    @pytest.mark.asyncio
    async def test_executes_sync_entrypoint(self) -> None:
        """Sync entrypoints are wrapped via asyncio.to_thread by the model layer.

        However _execute_bridged_tool always uses FunctionCall.aexecute(), so
        we test with a coroutine-function entrypoint (the common case for
        ii-agent tools).  Pure sync functions hit aexecute()'s await-fallback
        which may require the model's arun_function_call wrapper.
        """

        async def _sync_tool(x: int) -> int:
            return x * 2

        tools = [_make_function("SyncTool", entrypoint=_sync_tool)]
        strategy = self._make_strategy()
        result, events = await strategy._execute_bridged_tool(
            "SyncTool", {"x": 5}, tools, "call-sync"
        )
        assert result == "10"
        assert len(events) == 2

    @pytest.mark.asyncio
    async def test_returns_error_for_missing_tool(self) -> None:
        tools = [_make_function("OtherTool")]
        strategy = self._make_strategy()
        result, events = await strategy._execute_bridged_tool("MissingTool", {}, tools, "call-miss")
        assert "not found" in result
        assert events == []

    @pytest.mark.asyncio
    async def test_returns_error_for_no_entrypoint(self) -> None:
        tools = [_make_function("NoEntry", entrypoint=None)]
        strategy = self._make_strategy()
        result, events = await strategy._execute_bridged_tool("NoEntry", {}, tools, "call-noentry")
        assert "no executable entrypoint" in result
        assert events == []

    @pytest.mark.asyncio
    async def test_returns_error_on_exception(self) -> None:
        async def _failing_tool() -> str:
            raise ValueError("boom")

        tools = [_make_function("FailTool", entrypoint=_failing_tool)]
        strategy = self._make_strategy()
        result, events = await strategy._execute_bridged_tool("FailTool", {}, tools, "call-fail")
        assert "boom" in result
        # Should still have started + completed (error) events
        assert len(events) == 2
        assert events[0].event == ModelResponseEvent.tool_call_started.value
        assert events[1].event == ModelResponseEvent.tool_call_completed.value
        assert events[1].tool_executions[0].tool_call_error is True

    @pytest.mark.asyncio
    async def test_none_result_becomes_empty_string(self) -> None:
        async def _none_tool() -> None:
            return None

        tools = [_make_function("NoneTool", entrypoint=_none_tool)]
        strategy = self._make_strategy()
        result, events = await strategy._execute_bridged_tool("NoneTool", {}, tools, "call-none")
        assert result == ""
        assert len(events) == 2

    @pytest.mark.asyncio
    async def test_skips_dict_tools(self) -> None:
        """Dict tools are skipped — only Function objects are matched."""
        tools: list = [{"name": "DictTool", "description": "a dict"}]
        strategy = self._make_strategy()
        result, events = await strategy._execute_bridged_tool("DictTool", {}, tools, "call-dict")
        assert "not found" in result
        assert events == []

    @pytest.mark.asyncio
    async def test_empty_tools_list(self) -> None:
        strategy = self._make_strategy()
        result, events = await strategy._execute_bridged_tool("AnyTool", {}, [], "call-empty")
        assert "not found" in result
        assert events == []


# ---------------------------------------------------------------------------
# post_tool_result delivery failure handling
# ---------------------------------------------------------------------------


class TestPostToolResultFailure:
    """Test handling when post_tool_result fails."""

    @pytest.mark.asyncio
    async def test_failed_delivery_logged_but_not_raised(self) -> None:
        """When post_tool_result returns False, execution continues."""

        async def _tool() -> str:
            return "result"

        class _FailingClient:
            async def astream(self, **kwargs: Any) -> AsyncIterator[A2AStreamEvent]:
                yield A2AStreamEvent(
                    event_type="tool.execution_request",
                    data={
                        "tool_call_id": "call-fail",
                        "tool_name": "T",
                        "arguments": {},
                    },
                )
                yield A2AStreamEvent(event_type="text_delta", data={"text": "done"})

            async def post_tool_result(self, **kw: Any) -> bool:
                return False  # Delivery failed

        tools = [_make_function("T", entrypoint=_tool)]
        strategy = A2AInnerLoop(client=cast(IIAgentA2AClient, _FailingClient()))

        events = []
        async for event in strategy.aresponse_stream(
            model=cast(Model, _FakeModel()),
            messages=[],
            tools=tools,
        ):
            events.append(event)

        # Should get tool_call_started + tool_call_completed + text + content_done - no exception raised
        model_events = [e for e in events if isinstance(e, ModelResponse)]
        assert len(model_events) == 4
        assert model_events[0].event == ModelResponseEvent.tool_call_started.value
        assert model_events[1].event == ModelResponseEvent.tool_call_completed.value
        assert model_events[2].content == "done"
        assert model_events[3].delta_status == "content_done"


# ---------------------------------------------------------------------------
# Pre-hook / Post-hook integration via FunctionCall.aexecute()
# ---------------------------------------------------------------------------


class TestPrePostHookIntegration:
    """Verify that pre_hook and post_hook run through the bridge."""

    def _make_strategy(self) -> A2AInnerLoop:
        return A2AInnerLoop(client=cast(IIAgentA2AClient, _FakeA2AClient()))

    @pytest.mark.asyncio
    async def test_pre_hook_runs_before_entrypoint(self) -> None:
        call_order: list[str] = []

        async def _pre_hook() -> None:
            call_order.append("pre_hook")

        async def _entrypoint(x: int) -> str:
            call_order.append("entrypoint")
            return str(x)

        fn = Function(
            name="HookedTool",
            description="Tool with hooks",
            parameters={"type": "object", "properties": {}},
        )
        fn.entrypoint = _entrypoint
        fn.pre_hook = _pre_hook

        strategy = self._make_strategy()
        result, events = await strategy._execute_bridged_tool(
            "HookedTool", {"x": 42}, [fn], "call-hook-pre"
        )

        assert result == "42"
        assert call_order == ["pre_hook", "entrypoint"]
        assert len(events) == 2

    @pytest.mark.asyncio
    async def test_post_hook_runs_after_entrypoint(self) -> None:
        call_order: list[str] = []

        async def _post_hook() -> None:
            call_order.append("post_hook")

        async def _entrypoint() -> str:
            call_order.append("entrypoint")
            return "done"

        fn = Function(
            name="PostHookTool",
            description="",
            parameters={"type": "object", "properties": {}},
        )
        fn.entrypoint = _entrypoint
        fn.post_hook = _post_hook

        strategy = self._make_strategy()
        result, events = await strategy._execute_bridged_tool(
            "PostHookTool", {}, [fn], "call-hook-post"
        )

        assert result == "done"
        assert call_order == ["entrypoint", "post_hook"]

    @pytest.mark.asyncio
    async def test_agent_injection_via_signature(self) -> None:
        """If the entrypoint accepts 'agent', it gets Function._agent injected."""
        captured_agent = []

        async def _tool_with_agent(agent: Any) -> str:
            captured_agent.append(agent)
            return "ok"

        fn = Function(
            name="AgentTool",
            description="",
            parameters={"type": "object", "properties": {}},
        )
        fn.entrypoint = _tool_with_agent
        # Simulate what agent.py does before passing tools to aresponse_stream
        fn._agent = "fake-agent-object"

        strategy = self._make_strategy()
        result, events = await strategy._execute_bridged_tool("AgentTool", {}, [fn], "call-agent")

        assert result == "ok"
        assert captured_agent == ["fake-agent-object"]

    @pytest.mark.asyncio
    async def test_run_context_injection_via_signature(self) -> None:
        """If the entrypoint accepts 'run_context', it gets Function._run_context."""
        captured = []

        async def _tool_with_ctx(run_context: Any) -> str:
            captured.append(run_context)
            return "ctx-ok"

        @dataclass
        class _FakeRunContext:
            session_state: Any = None

        fn = Function(
            name="CtxTool",
            description="",
            parameters={"type": "object", "properties": {}},
        )
        fn.entrypoint = _tool_with_ctx
        fn._run_context = _FakeRunContext()

        strategy = self._make_strategy()
        result, _ = await strategy._execute_bridged_tool("CtxTool", {}, [fn], "call-ctx")

        assert result == "ctx-ok"
        assert len(captured) == 1
        assert isinstance(captured[0], _FakeRunContext)

    @pytest.mark.asyncio
    async def test_fc_injection_via_signature(self) -> None:
        """If the entrypoint accepts 'fc', it gets the FunctionCall object."""
        captured_fc = []

        async def _tool_with_fc(fc: Any) -> str:
            captured_fc.append(fc)
            return "fc-ok"

        fn = Function(
            name="FcTool",
            description="",
            parameters={"type": "object", "properties": {}},
        )
        fn.entrypoint = _tool_with_fc

        strategy = self._make_strategy()
        result, _ = await strategy._execute_bridged_tool("FcTool", {}, [fn], "call-fc")

        assert result == "fc-ok"
        assert len(captured_fc) == 1
        # The fc should be a FunctionCall instance
        from ii_agent.agents.tools.function import FunctionCall as FC

        assert isinstance(captured_fc[0], FC)


# ---------------------------------------------------------------------------
# Client post_tool_result HTTP method
# ---------------------------------------------------------------------------


class TestClientPostToolResult:
    """Test IIAgentA2AClient.post_tool_result."""

    @pytest.mark.asyncio
    async def test_posts_to_correct_url(self) -> None:
        import httpx

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = lambda: None

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post = AsyncMock(return_value=mock_response)

        client = IIAgentA2AClient(
            agent_url="http://localhost:18100",
            httpx_client=mock_client,
        )

        result = await client.post_tool_result(
            tool_call_id="call-abc",
            result="search results",
        )

        assert result is True
        mock_client.post.assert_awaited_once_with(
            "http://localhost:18100/tools/call-abc/result",
            json={"result": "search results"},
        )

    @pytest.mark.asyncio
    async def test_returns_false_on_error(self) -> None:
        import httpx

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post = AsyncMock(
            side_effect=httpx.HTTPStatusError("err", request=None, response=None)
        )

        client = IIAgentA2AClient(
            agent_url="http://localhost:18100",
            httpx_client=mock_client,
        )

        result = await client.post_tool_result(
            tool_call_id="call-xyz",
            result="data",
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_connection_error(self) -> None:
        import httpx

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))

        client = IIAgentA2AClient(
            agent_url="http://localhost:18100",
            httpx_client=mock_client,
        )

        result = await client.post_tool_result(
            tool_call_id="call-conn",
            result="data",
        )

        assert result is False


# ---------------------------------------------------------------------------
# HITL pause: _execute_bridged_tool respects HITL flags
# ---------------------------------------------------------------------------


class TestHITLPauseInBridgedTools:
    """Test that _execute_bridged_tool emits ToolCallPaused for HITL-flagged tools."""

    def _make_strategy(self) -> A2AInnerLoop:
        return A2AInnerLoop(client=cast(IIAgentA2AClient, _FakeA2AClient()))

    def _make_hitl_function(
        self,
        name: str = "ConfirmTool",
        *,
        requires_confirmation: bool = False,
        requires_user_input: bool = False,
        external_execution: bool = False,
    ) -> Function:
        fn = Function(
            name=name,
            description="HITL tool",
            parameters={"type": "object", "properties": {}},
        )
        fn.entrypoint = lambda: "should not run"
        fn.requires_confirmation = requires_confirmation or None
        fn.requires_user_input = requires_user_input or None
        fn.external_execution = external_execution or None
        return fn

    @pytest.mark.asyncio
    async def test_requires_confirmation_emits_paused(self) -> None:
        fn = self._make_hitl_function(requires_confirmation=True)
        strategy = self._make_strategy()
        result, events = await strategy._execute_bridged_tool(
            "ConfirmTool", {"x": 1}, [fn], "call-hitl-confirm"
        )
        assert "requires human approval" in result
        assert len(events) == 1
        assert events[0].event == ModelResponseEvent.tool_call_paused.value
        te = events[0].tool_executions[0]
        assert te.requires_confirmation is True
        assert te.tool_name == "ConfirmTool"

    @pytest.mark.asyncio
    async def test_requires_user_input_emits_paused(self) -> None:
        fn = self._make_hitl_function(requires_user_input=True)
        strategy = self._make_strategy()
        result, events = await strategy._execute_bridged_tool(
            "ConfirmTool", {}, [fn], "call-hitl-input"
        )
        assert "requires human approval" in result
        assert len(events) == 1
        te = events[0].tool_executions[0]
        assert te.requires_user_input is True

    @pytest.mark.asyncio
    async def test_external_execution_emits_paused(self) -> None:
        fn = self._make_hitl_function(external_execution=True)
        strategy = self._make_strategy()
        result, events = await strategy._execute_bridged_tool(
            "ConfirmTool", {}, [fn], "call-hitl-ext"
        )
        assert "requires human approval" in result
        te = events[0].tool_executions[0]
        assert te.external_execution_required is True

    @pytest.mark.asyncio
    async def test_no_hitl_flags_executes_normally(self) -> None:
        """When no HITL flags are set, the tool executes as before."""

        async def _tool(x: int) -> str:
            return f"result: {x}"

        fn = _make_function("NormalTool", entrypoint=_tool)
        strategy = self._make_strategy()
        result, events = await strategy._execute_bridged_tool(
            "NormalTool", {"x": 5}, [fn], "call-normal"
        )
        assert result == "result: 5"
        assert len(events) == 2  # started + completed

    @pytest.mark.asyncio
    async def test_hitl_tool_not_executed(self) -> None:
        """Entrypoint must NOT be called for HITL-flagged tools."""
        call_count = 0

        async def _side_effect_tool() -> str:
            nonlocal call_count
            call_count += 1
            return "executed!"

        fn = self._make_hitl_function(requires_confirmation=True)
        fn.entrypoint = _side_effect_tool
        strategy = self._make_strategy()
        await strategy._execute_bridged_tool("ConfirmTool", {}, [fn], "call-hitl-noexec")
        assert call_count == 0, "HITL tool entrypoint should not have been called"

    @pytest.mark.asyncio
    async def test_hitl_pause_posts_refusal_to_adapter(self) -> None:
        """When HITL pauses, the refusal string is posted to the adapter."""
        fn = self._make_hitl_function(requires_confirmation=True)
        client = _FakeA2AClient(
            events=[
                A2AStreamEvent(
                    event_type="tool.execution_request",
                    data={
                        "tool_call_id": "call-hitl-post",
                        "tool_name": "ConfirmTool",
                        "arguments": {},
                    },
                ),
                A2AStreamEvent(event_type="text_delta", data={"text": "done"}),
            ],
        )
        strategy = A2AInnerLoop(client=cast(IIAgentA2AClient, client))

        events = []
        async for event in strategy.aresponse_stream(
            model=cast(Model, _FakeModel()),
            messages=[],
            tools=[fn],
        ):
            events.append(event)

        # Should have ToolCallPaused + text delta
        model_events = [e for e in events if isinstance(e, ModelResponse)]
        paused = [e for e in model_events if e.event == ModelResponseEvent.tool_call_paused.value]
        assert len(paused) == 1, "expected one ToolCallPaused event"

        # Result should have been posted to adapter
        assert len(client.posted_results) == 1
        assert "requires human approval" in client.posted_results[0]["result"]


# ---------------------------------------------------------------------------
# Client cancel_task HTTP method
# ---------------------------------------------------------------------------


class TestClientCancelTask:
    """Test IIAgentA2AClient.cancel_task."""

    @pytest.mark.asyncio
    async def test_posts_cancel_to_correct_url(self) -> None:
        import httpx

        mock_response = AsyncMock()
        mock_response.status_code = 200

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post = AsyncMock(return_value=mock_response)

        client = IIAgentA2AClient(
            agent_url="http://localhost:18100",
            httpx_client=mock_client,
        )

        result = await client.cancel_task("task-123")
        assert result is True
        mock_client.post.assert_awaited_once_with(
            "http://localhost:18100/tasks/task-123:cancel",
        )

    @pytest.mark.asyncio
    async def test_returns_false_on_error(self) -> None:
        import httpx

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))

        client = IIAgentA2AClient(
            agent_url="http://localhost:18100",
            httpx_client=mock_client,
        )

        result = await client.cancel_task("task-456")
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_409_conflict(self) -> None:
        import httpx

        mock_response = AsyncMock()
        mock_response.status_code = 409

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post = AsyncMock(return_value=mock_response)

        client = IIAgentA2AClient(
            agent_url="http://localhost:18100",
            httpx_client=mock_client,
        )

        result = await client.cancel_task("task-789")
        assert result is False
