from typing import Any, Optional
from ii_agent.controller.state import State
from ii_agent.tools.base import LLMTool, ToolImplOutput


class MessageTool(LLMTool):
    name = "message_user"

    description = """\
Send a message to the user. Use this tool to communicate with users in various scenarios:

<Communication Types>
- Progress updates and status reports
- Task completion notifications with deliverables
- Clarifying questions or requests for additional information
- Acknowledgment of user messages
- Explanations of strategy changes or issues encountered
- Sharing reasoning or thought processes
</Communication Types>

<Usage Guidelines>
- Always respond immediately to new user messages before other operations
- Initial replies should be brief acknowledgments without detailed solutions
- Use "notify" mode for non-blocking progress updates
- Use "ask" mode only when user input is essential - this blocks execution
- Include relevant files as attachments since users may lack filesystem access
- Always message users with final results before task completion
- Follow questions with `return_control_to_user` tool to transfer control back
</Usage Guidelines>
"""
    
    input_schema = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "The message to send to the user"},
        },
        "required": ["text"],
    }

    def is_read_only(self) -> bool:
        """Message tool is read-only - it only communicates, doesn't modify state."""
        return True

    async def run_impl(
        self,
        tool_input: dict[str, Any],
        state: Optional[State] = None,
    ) -> ToolImplOutput:
        assert tool_input["text"], "Model returned empty message"
        msg = "Sent message to user"
        return ToolImplOutput(msg, msg, auxiliary_data={"success": True})