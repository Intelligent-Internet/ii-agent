"""Tool for indicating task completion."""

from typing import Any, Optional
from ii_agent.llm.message_history import MessageHistory
from ii_agent.tools.base import LLMTool, ToolImplOutput


class CompleteTool(LLMTool):
    name = "complete"
    """The model should call this tool when it is done with the task."""

    description = "Call this tool when you are done with the task, and supply your answer or summary."
    input_schema = {
        "type": "object",
        "properties": {
            "answer": {
                "type": "string",
                "description": "The answer to the question, or final summary of actions taken to accomplish the task.",
            },
        },
        "required": ["answer"],
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
        # Add safety checks for tool_input
        if tool_input is None:
            self.answer = "Tool called with None input"
            return ToolImplOutput("Task completed with error", "Task completed with error")
        
        if not isinstance(tool_input, dict):
            self.answer = f"Tool called with non-dict input: {type(tool_input)}"
            return ToolImplOutput("Task completed with error", "Task completed with error")
        
        if "answer" not in tool_input:
            self.answer = "Tool called without 'answer' key"
            return ToolImplOutput("Task completed with error", "Task completed with error")
        
        answer = tool_input["answer"]
        if not answer:
            self.answer = "Model returned empty answer"
            return ToolImplOutput("Task completed with empty answer", "Task completed with empty answer")
        
        self.answer = answer
        return ToolImplOutput("Task completed", "Task completed")

    def get_tool_start_message(self, tool_input: dict[str, Any]) -> str:
        return ""


class ReturnControlToUserTool(LLMTool):
    name = "return_control_to_user"
    
    description = """\
Return control back to the user. Use this tool when you are done with the task or after asking questions to user and waiting for their response. Use this tool when:
* You have completed your task or delivered the requested output
* You have asked a question or provided options and need the user to choose
* You are waiting for the user's response, input, or confirmation
* You want to pause to allow the user to review, reflect, or take the next action
This tool signals a handoff point, indicating that further action is expected from the user."""

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