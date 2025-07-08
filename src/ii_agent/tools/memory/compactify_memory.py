from typing import Any
from ii_agent.llm.context_manager.base import ContextManager
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
        self, tool_input: dict[str, Any]
    ) -> ToolImplOutput:
        # Note: This tool previously relied on message_history parameter
        # The implementation needs to be updated to work without it
        # For now, return a message indicating the tool needs refactoring
        return ToolImplOutput(
            "Memory compactification tool needs to be refactored to work without message_history parameter.",
            "Memory compactification tool needs refactoring.",
            auxiliary_data={"success": False},
        )
