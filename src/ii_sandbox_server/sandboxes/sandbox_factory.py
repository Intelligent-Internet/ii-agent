"""Factory for creating sandbox providers."""

import os
from typing import Dict, Optional, Type
from .base import BaseSandbox
from .e2b import E2BSandbox
from .docker import DockerSandbox


class SandboxFactory:
    """Factory class for creating sandbox providers.

    Supported providers:
    - 'e2b': E2B cloud sandbox (requires E2B_API_KEY)
    - 'docker': Local Docker sandbox (requires Docker daemon)

    Set SANDBOX_PROVIDER environment variable to choose the provider,
    or pass provider_type to get_provider().
    """

    _providers: Dict[str, Type[BaseSandbox]] = {
        "e2b": E2BSandbox,
        "docker": DockerSandbox,
        "local": DockerSandbox,  # Alias for docker provider
    }

    @classmethod
    def get_provider(cls, provider_type: Optional[str] = None) -> Type[BaseSandbox]:
        """Create a sandbox provider instance.

        Args:
            provider_type: Provider type ('e2b', etc.). If None, uses SANDBOX_PROVIDER env var or defaults to 'e2b'

        Returns:
            Sandbox provider instance

        Raises:
            ValueError: If provider type is not supported
        """
        if provider_type is None:
            provider_type = os.getenv("SANDBOX_PROVIDER", "e2b")

        if provider_type not in cls._providers:
            available_providers = ", ".join(cls._providers.keys())
            raise ValueError(
                f"Unsupported provider type '{provider_type}'. Available providers: {available_providers}"
            )

        provider_class = cls._providers[provider_type]
        return provider_class

    @classmethod
    def register_provider(
        cls, provider_type: str, provider_class: Type[BaseSandbox]
    ) -> None:
        """Register a new provider type.

        Args:
            provider_type: Provider type name
            provider_class: Provider class that inherits from SandboxProvider
        """
        if not issubclass(provider_class, BaseSandbox):
            raise ValueError("Provider class must inherit from SandboxProvider")

        cls._providers[provider_type] = provider_class

    @classmethod
    def get_available_providers(cls) -> list[str]:
        """Get list of available provider types.

        Returns:
            List of available provider type names
        """
        return list(cls._providers.keys())
