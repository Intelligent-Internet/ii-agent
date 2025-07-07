from typing import Any, Optional


from ii_agent.core.storage.models.settings import Settings
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

    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings

    def _get_api_key(self) -> str:
        return (
            self.settings.third_party_integration_config.openai_api_key.get_secret_value()
            if self.settings.third_party_integration_config.openai_api_key
            else None
        )

    def is_available(self) -> bool:
        return self._get_api_key() is not None

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
