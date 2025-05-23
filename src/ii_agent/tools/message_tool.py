from typing import Any, Optional
from ii_agent.llm.message_history import MessageHistory
from ii_agent.tools.base import LLMTool, ToolImplOutput


class MessageTool(LLMTool):
    name = "message_user"

    description = "Send a message to user without requiring a response. Use for sharing your reasoning, acknowledging receipt of messages, providing progress updates, reporting task completion, or explaining changes in approach."
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
        assert tool_input["text"], "Model returned empty message"
        return ToolImplOutput(f"{tool_input['text']}", f"{tool_input['text']}")