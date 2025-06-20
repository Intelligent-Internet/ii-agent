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

    async def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        assert tool_input["text"], "Model returned empty message"
        msg = "Sent message to user"
        return ToolImplOutput(msg, msg, auxiliary_data={"success": True})