from typing import Any, Optional
from ii_agent.llm.message_history import MessageHistory
from ii_agent.tools.base import LLMTool, ToolImplOutput


class MessageTool(LLMTool):
    name = "message_user"

    description = """\
Send a message to communicate with the user. This is your primary way to interact with the user.

Use this tool when you need to:
- Share your thoughts, reasoning, or analysis about a task
- Ask the user for clarification, additional information, or preferences
- Acknowledge that you received and understood the user's request
- Provide progress updates while working on tasks (e.g., "Now analyzing the codebase...", "Found 5 issues, fixing them...")
- Report completion of tasks or important milestones
- Explain any issues, errors, or unexpected situations you encounter
- Request permission or confirmation before taking significant actions
- Summarize findings or results from your analysis

Important: Always use clear, concise language. The user sees these messages in real-time, so keep them informative but not verbose."""
    
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
        msg = "Sent message to user"
        return ToolImplOutput(msg, msg, auxiliary_data={"success": True})