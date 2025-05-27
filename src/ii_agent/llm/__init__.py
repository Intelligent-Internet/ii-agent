import os

from ii_agent.llm.anthropic import AnthropicDirectClient
from ii_agent.llm.base import LLMClient
from ii_agent.llm.openai import OpenAIDirectClient


def get_client(client_name: str, **kwargs) -> LLMClient:
    """Get a client for a given client name."""
    if client_name == "anthropic-direct":
        anthropic_base_url = os.getenv("ANTHROPIC_BASE_URL")
        anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")

        if anthropic_base_url:
            # If ANTHROPIC_BASE_URL is set, assume OpenRouter or similar OpenAI-compatible API
            # Use OpenAIDirectClient with ANTHROPIC_BASE_URL and ANTHROPIC_API_KEY
            kwargs["base_url"] = anthropic_base_url
            if anthropic_api_key: # Pass the key if it exists
                kwargs["api_key"] = anthropic_api_key
            # Ensure model name is passed if present in original kwargs
            model_name = kwargs.pop("model_name", None)
            if model_name:
                 return OpenAIDirectClient(model_name=model_name, **kwargs)
            else: # Fallback if model_name was not in kwargs, though it usually is
                 return OpenAIDirectClient(**kwargs)
        else:
            # Original Anthropic client
            return AnthropicDirectClient(**kwargs)
    elif client_name == "openai-direct":
        # Ensure OPENAI_API_KEY and OPENAI_BASE_URL are used as before for this client
        return OpenAIDirectClient(**kwargs)
    else:
        raise ValueError(f"Unknown client name: {client_name}")


__all__ = [
    "LLMClient",
    "OpenAIDirectClient",
    "AnthropicDirectClient",
    "get_client",
]
