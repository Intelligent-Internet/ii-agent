from typing import Any, Optional
from ii_agent.llm.message_history import MessageHistory
from ii_agent.tools.base import LLMTool, ToolImplOutput


class MessageTool(LLMTool):
    name = "message_user"

    description = """\
Send a message to the user. Use this tool to communicate effectively in a variety of scenarios, including:
* Sharing your current thoughts or reasoning process
* Asking clarifying or follow-up questions
* Acknowledging receipt of messages
* Providing real-time progress updates
* Reporting completion of tasks or milestones
* Explaining changes in strategy, unexpected behavior, or encountered issues"""
    
    input_schema = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "The message to send to the user"},
        },
        "required": ["text"],
    }

    def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        # Add safety checks for tool_input
        if tool_input is None:
            msg = "Message tool called with None input"
            return ToolImplOutput(msg, msg, auxiliary_data={"success": False})
        
        if not isinstance(tool_input, dict):
            msg = f"Message tool called with non-dict input: {type(tool_input)}"
            return ToolImplOutput(msg, msg, auxiliary_data={"success": False})
        
        if "text" not in tool_input:
            msg = "Message tool called without 'text' key"
            return ToolImplOutput(msg, msg, auxiliary_data={"success": False})
        
        text = tool_input["text"]
        if not text:
            msg = "Model returned empty message"
            return ToolImplOutput(msg, msg, auxiliary_data={"success": False})
        
        msg = "Sent message to user"
        return ToolImplOutput(msg, msg, auxiliary_data={"success": True})