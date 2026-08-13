"""Unit tests for realtime/events/converter.py — convert_agent_event_to_realtime."""

from __future__ import annotations

import uuid


from ii_agent.agents.models.response import ToolExecution
from ii_agent.agents.runs.agent import (
    AgentSummaryCompletedEvent,
    AgentSummaryStartedEvent,
    ReasoningCompletedEvent,
    ReasoningDeltaEvent,
    ReasoningStartedEvent,
    RunCancelledEvent,
    RunCompletedEvent,
    RunContentDeltaEvent,
    RunContentEvent,
    RunErrorEvent,
    RunOutput,
    RunStartedEvent,
    SandboxInitializedEvent,
    ToolCallCompletedEvent,
    ToolCallStartedEvent,
)
from ii_agent.realtime.events.app_events import (
    AgentCompleteEvent,
    AgentModelCompactEvent,
    AgentProcessingEvent,
    AgentReasoningDeltaEvent,
    AgentReasoningEvent,
    AgentReasoningStartEvent,
    AgentResponseDeltaEvent,
    AgentResponseEvent,
    AgentResponseInterruptedEvent,
    AgentToolCallEvent,
    AgentToolResultEvent,
    SandboxStatusChangedEvent,
    SubAgentCompleteEvent,
    SystemErrorEvent,
)
from ii_agent.realtime.events.converter import (
    _get_sub_agent_info,
    convert_agent_event_to_realtime,
)
from ii_agent.tasks.types import RunStatus


RUN_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
SESSION_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")

# Minimal required fields for RunOutput
_RUN_OUTPUT_DEFAULTS = dict(
    run_id="run-1",
    session_id="sess-1",
    user_id="user-1",
    model="claude-3",
    agent_name="agent",
)


class TestGetSubAgentInfo:
    def test_only_agent_name_for_plain_event(self):
        # agent_name is always included when set; no sub-agent fields
        event = RunStartedEvent(agent_name="a", model="m")
        info = _get_sub_agent_info(event)
        assert "delegated_from" not in info
        assert "is_sub_agent_event" not in info
        assert "parent_run_id" not in info
        assert info.get("agent_name") == "a"

    def test_delegated_from_included(self):
        event = RunStartedEvent(agent_name="a", model="m", delegated_from="parent")
        info = _get_sub_agent_info(event)
        assert info["delegated_from"] == "parent"

    def test_is_sub_agent_event_included(self):
        event = RunStartedEvent(agent_name="a", model="m", is_sub_agent_event=True)
        info = _get_sub_agent_info(event)
        assert info["is_sub_agent_event"] is True

    def test_parent_run_id_included(self):
        event = RunStartedEvent(agent_name="a", model="m", parent_run_id="parent-run")
        info = _get_sub_agent_info(event)
        assert info["parent_run_id"] == "parent-run"

    def test_run_output_is_sub_agent_response(self):
        run_out = RunOutput(**_RUN_OUTPUT_DEFAULTS, delegated_from="parent-agent")
        info = _get_sub_agent_info(run_out)
        assert info["is_sub_agent_response"] is True

    def test_run_output_not_sub_agent_when_no_delegation(self):
        run_out = RunOutput(**_RUN_OUTPUT_DEFAULTS)
        info = _get_sub_agent_info(run_out)
        assert "is_sub_agent_response" not in info

    def test_agent_name_included(self):
        event = RunStartedEvent(agent_name="my-agent", model="m")
        info = _get_sub_agent_info(event)
        assert info["agent_name"] == "my-agent"


class TestConvertRunOutput:
    def _run_out(self, **kwargs):
        return RunOutput(**{**_RUN_OUTPUT_DEFAULTS, **kwargs})

    def test_completed_run_returns_agent_complete(self):
        run_out = self._run_out(status=RunStatus.COMPLETED, content="Done")
        result = convert_agent_event_to_realtime(run_out, RUN_ID, SESSION_ID)
        assert isinstance(result, AgentCompleteEvent)
        assert result.content["text"] == "Done"

    def test_cancelled_run_returns_interrupted(self):
        run_out = self._run_out(status=RunStatus.CANCELLED)
        result = convert_agent_event_to_realtime(run_out, RUN_ID, SESSION_ID)
        assert isinstance(result, AgentResponseInterruptedEvent)
        assert result.content["run_status"] == RunStatus.CANCELLED

    def test_sub_agent_run_returns_sub_agent_complete(self):
        run_out = self._run_out(delegated_from="parent", status=RunStatus.COMPLETED)
        result = convert_agent_event_to_realtime(run_out, RUN_ID, SESSION_ID)
        assert isinstance(result, SubAgentCompleteEvent)

    def test_run_id_in_content(self):
        run_out = self._run_out(status=RunStatus.COMPLETED)
        result = convert_agent_event_to_realtime(run_out, RUN_ID, SESSION_ID)
        assert result.content["run_id"] == str(RUN_ID)


class TestConvertRunStartedEvent:
    def test_returns_processing_event(self):
        event = RunStartedEvent(agent_name="agent", model="claude-3", model_provider="anthropic")
        result = convert_agent_event_to_realtime(event, RUN_ID, SESSION_ID)
        assert isinstance(result, AgentProcessingEvent)
        assert result.content["model"] == "claude-3"
        assert result.content["run_status"] == RunStatus.RUNNING


class TestConvertRunContentEvent:
    def test_returns_agent_response_event(self):
        event = RunContentEvent(agent_name="a", model="m", content="hello")
        result = convert_agent_event_to_realtime(event, RUN_ID, SESSION_ID)
        assert isinstance(result, AgentResponseEvent)
        assert result.content["text"] == "hello"


class TestConvertRunContentDeltaEvent:
    def test_returns_agent_response_delta(self):
        event = RunContentDeltaEvent(agent_name="a", model="m", content="chunk")
        result = convert_agent_event_to_realtime(event, RUN_ID, SESSION_ID)
        assert isinstance(result, AgentResponseDeltaEvent)
        assert result.content["text"] == "chunk"

    def test_none_content_becomes_empty_string(self):
        event = RunContentDeltaEvent(agent_name="a", model="m", content=None)
        result = convert_agent_event_to_realtime(event, RUN_ID, SESSION_ID)
        assert result.content["text"] == ""


class TestConvertRunCompletedEvent:
    def test_normal_run_completed_returns_agent_complete(self):
        event = RunCompletedEvent(agent_name="a", model="m")
        result = convert_agent_event_to_realtime(event, RUN_ID, SESSION_ID)
        assert isinstance(result, AgentCompleteEvent)
        assert result.content["run_status"] == RunStatus.COMPLETED

    def test_sub_agent_run_completed_returns_sub_agent_complete(self):
        event = RunCompletedEvent(agent_name="a", model="m", delegated_from="parent")
        result = convert_agent_event_to_realtime(event, RUN_ID, SESSION_ID)
        assert isinstance(result, SubAgentCompleteEvent)


class TestConvertRunErrorEvent:
    def test_returns_system_error(self):
        event = RunErrorEvent(agent_name="a", model="m", content="boom", error_type=None)
        result = convert_agent_event_to_realtime(event, RUN_ID, SESSION_ID)
        assert isinstance(result, SystemErrorEvent)
        assert result.content["message"] == "boom"
        assert result.content["run_status"] == RunStatus.FAILED

    def test_unknown_error_type_defaults(self):
        event = RunErrorEvent(agent_name="a", model="m", error_type="unknown_code")
        result = convert_agent_event_to_realtime(event, RUN_ID, SESSION_ID)
        assert isinstance(result, SystemErrorEvent)

    def test_no_content_uses_default_message(self):
        event = RunErrorEvent(agent_name="a", model="m")
        result = convert_agent_event_to_realtime(event, RUN_ID, SESSION_ID)
        assert result.content["message"] == "An error occurred"


class TestConvertRunCancelledEvent:
    def test_returns_interrupted_event(self):
        event = RunCancelledEvent(agent_name="a", model="m", reason="timeout")
        result = convert_agent_event_to_realtime(event, RUN_ID, SESSION_ID)
        assert isinstance(result, AgentResponseInterruptedEvent)
        assert result.content["message"] == "timeout"
        assert result.content["run_status"] == RunStatus.CANCELLED

    def test_no_reason_uses_default(self):
        event = RunCancelledEvent(agent_name="a", model="m")
        result = convert_agent_event_to_realtime(event, RUN_ID, SESSION_ID)
        assert "cancelled" in result.content["message"].lower()


class TestConvertReasoningEvents:
    def test_reasoning_started(self):
        event = ReasoningStartedEvent(agent_name="a", model="m")
        result = convert_agent_event_to_realtime(event, RUN_ID, SESSION_ID)
        assert isinstance(result, AgentReasoningStartEvent)

    def test_reasoning_delta_normal(self):
        event = ReasoningDeltaEvent(
            agent_name="a", model="m", reasoning_content="thinking...", is_redacted=False
        )
        result = convert_agent_event_to_realtime(event, RUN_ID, SESSION_ID)
        assert isinstance(result, AgentReasoningDeltaEvent)
        assert result.content["text"] == "thinking..."
        assert result.content["is_redacted"] is False

    def test_reasoning_delta_redacted(self):
        event = ReasoningDeltaEvent(
            agent_name="a",
            model="m",
            redacted_reasoning_content="<encrypted>",
            is_redacted=True,
        )
        result = convert_agent_event_to_realtime(event, RUN_ID, SESSION_ID)
        assert isinstance(result, AgentReasoningDeltaEvent)
        assert result.content["text"] == "<encrypted>"
        assert result.content["is_redacted"] is True

    def test_reasoning_completed(self):
        event = ReasoningCompletedEvent(agent_name="a", model="m", content="final reasoning")
        result = convert_agent_event_to_realtime(event, RUN_ID, SESSION_ID)
        assert isinstance(result, AgentReasoningEvent)
        assert result.content["text"] == "final reasoning"


class TestConvertAgentSummaryEvents:
    def test_summary_started_returns_none(self):
        event = AgentSummaryStartedEvent(agent_name="a", model="m")
        result = convert_agent_event_to_realtime(event, RUN_ID, SESSION_ID)
        assert result is None

    def test_summary_completed_returns_compact(self):
        event = AgentSummaryCompletedEvent(agent_name="a", model="m")
        result = convert_agent_event_to_realtime(event, RUN_ID, SESSION_ID)
        assert isinstance(result, AgentModelCompactEvent)


class TestConvertSandboxInitializedEvent:
    def test_returns_sandbox_status_changed_with_no_sandbox_info(self):
        event = SandboxInitializedEvent(agent_name="a", model="m", sandbox_info=None)
        result = convert_agent_event_to_realtime(event, RUN_ID, SESSION_ID)
        assert isinstance(result, SandboxStatusChangedEvent)
        # Normalized status for None info
        assert result.status == "starting"


class TestConvertToolCallEvents:
    def test_tool_call_started_no_tool(self):
        event = ToolCallStartedEvent(agent_name="a", model="m", tool=None)
        result = convert_agent_event_to_realtime(event, RUN_ID, SESSION_ID)
        assert isinstance(result, AgentToolCallEvent)
        assert result.tool_name == ""

    def test_tool_call_started_with_tool(self):
        tool = ToolExecution(tool_name="web_search", tool_call_id="tc-1")
        event = ToolCallStartedEvent(agent_name="a", model="m", tool=tool)
        result = convert_agent_event_to_realtime(event, RUN_ID, SESSION_ID)
        assert isinstance(result, AgentToolCallEvent)
        assert result.tool_name == "web_search"
        assert result.tool_call_id == "tc-1"

    def test_tool_call_completed_with_minimal_tool(self):
        # ToolCallCompletedEvent.tool must not be None (accesses tool.result)
        tool = ToolExecution(tool_name="search", tool_call_id="tc-99")
        tool.result = None  # result attribute expected by converter
        event = ToolCallCompletedEvent(agent_name="a", model="m", tool=tool)
        result = convert_agent_event_to_realtime(event, RUN_ID, SESSION_ID)
        assert isinstance(result, AgentToolResultEvent)
        assert result.tool_name == "search"

    def test_tool_call_completed_with_tool(self):
        tool = ToolExecution(tool_name="code_run", tool_call_id="tc-2")
        event = ToolCallCompletedEvent(agent_name="a", model="m", tool=tool)
        result = convert_agent_event_to_realtime(event, RUN_ID, SESSION_ID)
        assert isinstance(result, AgentToolResultEvent)
        assert result.tool_name == "code_run"


class TestConvertUnknownEvent:
    def test_unknown_event_returns_none(self):
        # Use an object that doesn't match any isinstance check
        from ii_agent.agents.runs.agent import PreHookStartedEvent

        event = PreHookStartedEvent(agent_name="a", model="m")
        result = convert_agent_event_to_realtime(event, RUN_ID, SESSION_ID)
        assert result is None
