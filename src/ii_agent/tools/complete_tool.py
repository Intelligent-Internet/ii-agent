"""Tool for indicating task completion."""

from typing import Any, Optional
from ii_agent.llm.message_history import MessageHistory
from ii_agent.tools.base import LLMTool, ToolImplOutput


class CompleteTool(LLMTool):
    name = "complete"
    """The model should call this tool when it is done with the task."""

    description = "Call this tool when you are done with the task"
    input_schema = {
        "type": "object",
        "properties": {
        },
        "required": [],
    }

    def __init__(self):
        super().__init__()
        self.answer: str = ""

    @property
    def should_stop(self):
        return self.answer != ""

    def reset(self):
        self.answer = ""

    def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        self.answer = "Task completed"
        return ToolImplOutput("Task completed", "Task completed")

    def get_tool_start_message(self, tool_input: dict[str, Any]) -> str:
        return ""
