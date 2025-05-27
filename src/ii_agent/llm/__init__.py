import os
from ii_agent.llm.base import LLMClient
from ii_agent.llm.openai import OpenAIDirectClient
from ii_agent.llm.anthropic import AnthropicDirectClient
from ii_agent.llm.openrouter import OpenRouterClient

# from ii_agent.utils.constants import DEFAULT_MODEL # Optional: if needed for a default model_name here


def get_client(client_name: str | None = None, **kwargs) -> LLMClient:
    """
    Get an LLM client.
    If client_name is explicitly "anthropic-direct", "openrouter", or "openai-direct",
    attempts to load that specific client.
    If client_name is None or "auto", attempts to auto-detect based on available API keys:
    1. Anthropic (if ANTHROPIC_API_KEY is set)
    2. OpenRouter (if OPENROUTER_API_KEY is set)
    """
    resolved_client_name = client_name
    determined_by_auto_logic = False

    if resolved_client_name is None or resolved_client_name == "auto":
        determined_by_auto_logic = True
        if os.getenv("ANTHROPIC_API_KEY"):
            print("Auto-detected ANTHROPIC_API_KEY, using AnthropicDirectClient.")
            resolved_client_name = "anthropic-direct"
        elif os.getenv("OPENROUTER_API_KEY"):
            print("Auto-detected OPENROUTER_API_KEY, using OpenRouterClient.")
            resolved_client_name = "openrouter"
        else:
            raise ValueError(
                "Auto-detection failed: No API key found for Anthropic or OpenRouter. "
                "Please set ANTHROPIC_API_KEY or OPENROUTER_API_KEY."
            )

    if resolved_client_name == "anthropic-direct":
        if not determined_by_auto_logic and not os.getenv("ANTHROPIC_API_KEY"):
            raise ValueError("ANTHROPIC_API_KEY not found for an explicit 'anthropic-direct' client request.")
        # verbose_print(f"Initializing AnthropicDirectClient with kwargs: {kwargs}")
        return AnthropicDirectClient(**kwargs)
    elif resolved_client_name == "openrouter":
        if not determined_by_auto_logic and not os.getenv("OPENROUTER_API_KEY"):
            raise ValueError("OPENROUTER_API_KEY not found for an explicit 'openrouter' client request.")
        openrouter_kwargs = {
            k: v for k, v in kwargs.items() if k in ["model_name", "max_retries"]
        }
        # verbose_print(f"Initializing OpenRouterClient with filtered kwargs: {openrouter_kwargs}")
        return OpenRouterClient(**openrouter_kwargs)
    elif resolved_client_name == "openai-direct":
        # Kept for explicit requests, as per current codebase structure.
        # User mentioned OpenAI is for imagegen, so it's not in auto-detection for LLM client.
        if not os.getenv("OPENAI_API_KEY"):
             raise ValueError("OPENAI_API_KEY not found for an explicit 'openai-direct' client request.")
        # verbose_print(f"Initializing OpenAIDirectClient with kwargs: {kwargs}")
        return OpenAIDirectClient(**kwargs)
    else:
        raise ValueError(f"Unknown or unsupported client name: {resolved_client_name}")


__all__ = [
    "LLMClient",
    "OpenAIDirectClient",
    "AnthropicDirectClient",
    "OpenRouterClient",
    "get_client",
]
