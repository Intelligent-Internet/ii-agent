"""LLM client for xAI models (Grok family)."""

from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.llm.openai import OpenAIDirectClient


XAI_DEFAULT_BASE_URL = "https://api.x.ai/v1"


class XaiDirectClient(OpenAIDirectClient):
    """Use xAI models via their OpenAI-compatible API surface."""

    def __init__(self, llm_config: LLMConfig):
        # xAI follows the OpenAI SDK contract but requires its own base URL.
        if not llm_config.base_url:
            llm_config.base_url = XAI_DEFAULT_BASE_URL
        super().__init__(llm_config)

