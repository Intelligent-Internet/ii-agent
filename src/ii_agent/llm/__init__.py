from ii_agent.core.config.llm_config import APITypes, LLMConfig
from ii_agent.llm.base import LLMClient
from ii_agent.llm.openai import OpenAIDirectClient
from ii_agent.llm.anthropic import AnthropicDirectClient
from ii_agent.llm.gemini import GeminiDirectClient
from ii_agent.llm.minimax import MiniMaxDirectClient

def get_client(config: LLMConfig) -> LLMClient:
    """Get a client for a given client name."""
    if config.api_type == APITypes.ANTHROPIC:
        return AnthropicDirectClient(
            llm_config=config,
        )
    elif config.api_type == APITypes.OPENAI:
        return OpenAIDirectClient(llm_config=config)
    elif config.api_type == APITypes.GEMINI:
        return GeminiDirectClient(llm_config=config)
    elif config.api_type == APITypes.MINIMAX:
        return MiniMaxDirectClient(llm_config=config)


__all__ = [
    "LLMClient",
    "OpenAIDirectClient",
    "AnthropicDirectClient",
    "GeminiDirectClient",
    "MiniMaxDirectClient",
    "get_client",
]
