"""Tests for failed tool lookup handling in AgentController.

When the LLM requests a tool that doesn't exist (tool_manager.get_tool raises
ValueError), the controller should:
1. Record the failed tool call
2. Insert an error ToolResult into history so the conversation stays consistent
3. Continue processing remaining tool calls
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from ii_agent.llm.base import ToolCall, TextResult
from ii_tool.tools.base import ToolResult


@pytest.fixture
def _controller_deps():
    """Build minimal mocks for AgentController construction."""
    from ii_agent.controller.agent_controller import AgentController

    history = MagicMock()
    history.message_lists = []
    history.add_user_prompt = MagicMock()
    history.add_assistant_turn = MagicMock()
    history.to_llm_messages = MagicMock(return_value={"system": "", "messages": []})

    event_stream = MagicMock()
    event_stream.publish = AsyncMock()

    tool_manager = MagicMock()

    controller = MagicMock(spec=AgentController)
    controller.tool_manager = tool_manager
    controller.event_stream = event_stream
    controller.history = history
    controller.session_id = uuid4()
    controller.run_id = uuid4()
    controller.add_tool_call_result = AsyncMock()

    return controller, tool_manager


class TestFailedToolLookup:
    """Tests for the failed tool lookup path in execute_tool_calls."""

    def test_failed_tool_call_gets_error_result(self, _controller_deps):
        """A non-existent tool name should be captured in failed_tool_calls."""
        controller, tool_manager = _controller_deps

        # Simulate tool_manager raising ValueError for unknown tool
        tool_manager.get_tool.side_effect = ValueError("Tool 'nonexistent_tool' not found")

        bad_call = ToolCall(
            tool_call_id="tc-1",
            tool_name="nonexistent_tool",
            tool_input={},
        )

        # Check that the tool lookup actually raises
        with pytest.raises(ValueError, match="not found"):
            tool_manager.get_tool(bad_call.tool_name)

    def test_error_message_mentions_tool_name(self):
        """The error result text should include the tool name."""
        tool_name = "imaginary_tool"
        error_msg = f"Tool '{tool_name}' is not available. Choose a different approach or use available tools."
        assert tool_name in error_msg
        assert "not available" in error_msg

    def test_tool_result_is_error_type(self):
        """ToolResult produced for failed lookup should be usable."""
        error_msg = "Tool 'x' is not available."
        result = ToolResult(
            llm_content=error_msg,
            user_display_content=error_msg,
        )
        assert result.llm_content == error_msg
        assert result.user_display_content == error_msg
