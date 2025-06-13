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

    async def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        assert tool_input["answer"], "Model returned empty answer"
        self.answer = tool_input["answer"]
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

    async def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        self.answer = "Task completed"
        return ToolImplOutput("Task completed", "Task completed")

    def get_tool_start_message(self, tool_input: dict[str, Any]) -> str:
        return ""
    
    

class CompleteToolReviewer(LLMTool):
    name = "complete_reviewer"
    """The model should call this tool when it is done with the task."""

    description = "Call this tool when you are done with the task, and supply your answer or summary. This tool is used by the reviewer agent to indicate that the task is complete."
    input_schema = {
        "type": "object",
        "properties": {
            "answer": {
                "type": "string",
                "description": "The answer to the question, or final summary of actions taken to accomplish the task. This is the feedback from the reviewer agent to the general agent.",
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

    async def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        assert tool_input["answer"], "Model returned empty answer"
        self.answer = tool_input["answer"]
        return ToolImplOutput(self.answer, "Reviewer completed")

    def get_tool_start_message(self, tool_input: dict[str, Any]) -> str:
        return ""


class ReturnControlToGeneralAgentTool(LLMTool):
    name = "return_control_to_general_agent"
    
    description = """\
Return control back to the general agent. Use this tool when you are done with the review and want to handover the control back to the general agent.
Before using this tool, you should have provided the general agent with details feedback that you have reviewed the general agent's output.
This tool signals a handoff point, indicating that further action is expected from the general agent."""

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

    async def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        return ToolImplOutput("Reviewer completed - handover control to general agent", "Reviewer completed - handover control to general agent")

    def get_tool_start_message(self, tool_input: dict[str, Any]) -> str:
        return ""