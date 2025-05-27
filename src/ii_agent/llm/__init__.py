from ii_agent.llm.base import LLMClient
from ii_agent.llm.openai import OpenAIDirectClient
from ii_agent.llm.anthropic import AnthropicDirectClient
import os


def get_client(client_name: str, **kwargs) -> LLMClient:
    """Get a client for a given client name."""
    if client_name == "anthropic-direct":
        anthropic_base_url = os.getenv("ANTHROPIC_BASE_URL")
        if anthropic_base_url:
            kwargs["base_url"] = anthropic_base_url
        return AnthropicDirectClient(**kwargs)
    elif client_name == "openai-direct":
        return OpenAIDirectClient(**kwargs)
    else:
        raise ValueError(f"Unknown client name: {client_name}")


__all__ = [
    "LLMClient",
    "OpenAIDirectClient",
    "AnthropicDirectClient",
    "get_client",
]
