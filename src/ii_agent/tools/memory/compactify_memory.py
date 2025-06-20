from typing import Any
from ii_agent.llm.context_manager.base import ContextManager
from ii_agent.llm.message_history import MessageHistory
from ii_agent.tools.base import LLMTool, ToolImplOutput


class CompactifyMemoryTool(LLMTool):
    """Memory compactification tool that works with any context manager type.

    Applies the context manager's truncation strategy to compress the conversation history.
    This tool adapts to different context management approaches (summarization, simple truncation, etc.).
    """

    name = "compactify_memory"
    description = """Compactifies the conversation memory using the configured context management strategy. 
    Use this tool when the conversation is getting long and you need to free up context space while preserving important information.
    Helps maintain conversation continuity while staying within token limits.
    """

    input_schema = {"type": "object", "properties": {}, "required": []}

    def __init__(self, context_manager: ContextManager):
        self.context_manager = context_manager

    async def run_impl(
        self, tool_input: dict[str, Any], message_history: MessageHistory | None = None
    ) -> ToolImplOutput:
        if not message_history:
            return ToolImplOutput(
                "Message history is required to compactify memory.",
                "Message history is required to compactify memory.",
                auxiliary_data={"success": False},
            )
        truncated = self.context_manager.apply_truncation(
            message_history.get_messages_for_llm()
        )
        message_history.set_message_list(truncated)

        return ToolImplOutput(
            "Memory compactified.",
            "Memory compactified.",
            auxiliary_data={"success": True},
        )
