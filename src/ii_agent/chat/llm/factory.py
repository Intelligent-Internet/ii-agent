"""Factory for creating LLM providers (updated for official SDKs).

Routing is based on two axes:

* **Provider** — the model maker (Anthropic, Google, OpenAI, …).
* **ApiType** — the hosting platform (``vertex_ai``, ``azure``, ``bedrock``,
  or ``None`` for the provider's direct API).

The ``ApiType`` is read from ``ModelConfig.api_type`` (stored in
``ModelParams.api_type`` in the JSONB ``configs`` column).
"""

import logging
from typing import Type

from ii_agent.settings.llm import Provider
from ii_agent.settings.llm.schemas import ModelConfig
from ii_agent.settings.llm.types import ApiType
from ii_agent.chat.llm.custom import CustomProvider
from ii_agent.chat.base import LLMClient
from ii_agent.chat.llm.anthropic import AnthropicProvider
from ii_agent.chat.llm.openai import OpenAIProvider
from ii_agent.chat.llm.gemini import GeminiProvider

logger = logging.getLogger(__name__)


class LLMProviderFactory:
    """Factory for creating provider-specific LLM clients using official SDKs.

    Routing logic:
        1. ``(provider, api_type)`` determines the SDK client class.
        2. Each provider class already handles VertexAI / Azure auth internally
           when the relevant config fields (``vertex_project_id``, ``azure_endpoint``)
           are present in ``ModelConfig``.
    """

    # Default registry: provider → client class (direct API)
    _provider_registry: dict[Provider, Type[LLMClient]] = {
        Provider.ANTHROPIC: AnthropicProvider,
        Provider.OPENAI: OpenAIProvider,
        Provider.GOOGLE: GeminiProvider,
        Provider.CEREBRAS: CustomProvider,
        Provider.ATLASCLOUD: CustomProvider,
        Provider.CUSTOM: CustomProvider,
    }

    # ApiType overrides: (provider, api_type) → client class
    # When an api_type is set the provider still uses its own SDK but with
    # platform-specific auth (e.g. AnthropicProvider creates AsyncAnthropicVertex).
    _api_type_registry: dict[tuple[Provider, ApiType], Type[LLMClient]] = {
        (Provider.ANTHROPIC, ApiType.VERTEX_AI): AnthropicProvider,
        (Provider.GOOGLE, ApiType.VERTEX_AI): GeminiProvider,
        (Provider.OPENAI, ApiType.AZURE): OpenAIProvider,
    }

    @classmethod
    def _resolve_provider_class(cls, llm_config: ModelConfig) -> Type[LLMClient]:
        """Resolve the LLMClient subclass for the given config."""
        provider = llm_config.provider
        api_type = llm_config.api_type

        # Check (provider, api_type) override first
        if api_type is not None:
            provider_class = cls._api_type_registry.get((provider, api_type))
            if provider_class:
                return provider_class

        # Fall back to default provider registry
        provider_class = cls._provider_registry.get(provider)
        if provider_class:
            # OpenAI + custom base_url → CustomProvider (backward compat)
            if provider == Provider.OPENAI and llm_config.base_url is not None:
                return CustomProvider
            return provider_class

        supported = ", ".join(t.value for t in cls._provider_registry.keys())
        raise ValueError(
            f"Unsupported provider: {provider.value}. Supported providers: {supported}"
        )

    @classmethod
    def create_provider(cls, llm_config: ModelConfig) -> LLMClient:
        """Create appropriate provider based on provider and api_type.

        Args:
            llm_config: LLM configuration with provider + api_type

        Returns:
            Provider instance using official SDK

        Raises:
            ValueError: If provider not supported
        """
        provider_class = cls._resolve_provider_class(llm_config)

        logger.info(
            "Creating %s for model: %s (provider: %s, api_type: %s)",
            provider_class.__name__,
            llm_config.model,
            llm_config.provider.value,
            llm_config.api_type,
        )

        return provider_class(llm_config)

    @classmethod
    def register_provider(
        cls,
        provider: Provider,
        provider_class: Type[LLMClient],
    ) -> None:
        """
        Register a new provider implementation.

        This allows extending the factory with custom providers at runtime.

        Args:
            provider: Provider enum value
            provider_class: Provider class to register

        Example:
            ```python
            class CustomProvider(ProviderClient):
                ...

            LLMProviderFactory.register_provider(
                Provider.CUSTOM,
                CustomProvider
            )
            ```
        """
        logger.info(f"Registering provider {provider_class.__name__} for {provider.value}")
        cls._provider_registry[provider] = provider_class

    @classmethod
    def get_supported_providers(cls) -> list[str]:
        """
        Get list of supported provider types.

        Returns:
            List of supported provider values
        """
        return [provider.value for provider in cls._provider_registry.keys()]


def get_client(config: ModelConfig) -> LLMClient:
    """Get an LLM client for a given config. Convenience wrapper around LLMProviderFactory."""
    return LLMProviderFactory.create_provider(config)
