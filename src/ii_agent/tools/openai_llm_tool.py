from typing import Any, Optional
import os


from ii_agent.tools.base import (
    ToolImplOutput,
    LLMTool,
)
from ii_agent.llm.message_history import MessageHistory


class OpenAILLMTool(LLMTool):
    """Tool for getting a temporary API key for OpenAI LLM"""

    name = "get_openai_api_key"
    description = (
        "Get a temporary API key for OpenAI LLM. This is safe to use and will expire"
    )
    input_schema = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    def __init__(self):
        super().__init__()

    def _get_api_key(self) -> str:
        return os.getenv("OPENAI_API_KEY_TMP")

    async def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        api_key = self._get_api_key()

        return ToolImplOutput(
            tool_output=api_key,
            tool_result_message=f"API key for OpenAI LLM: {api_key}",
        )
