from typing import Dict, Type
from ii_agent.core.storage.models.settings import Settings
from ii_agent.sandbox.base_sandbox import BaseSandbox
from ii_agent.utils.constants import WorkSpaceMode


class SandboxRegistry:
    """Registry-based factory with decorator support."""

    _registry: Dict[str, Type[BaseSandbox]] = {}

    @classmethod
    def register(cls, sandbox_type: WorkSpaceMode):
        """Decorator to register a processor class."""

        def decorator(processor_class: Type[BaseSandbox]):
            cls._registry[sandbox_type.value] = processor_class
            return processor_class

        return decorator

    @classmethod
    def create(
        cls,
        sandbox_type: WorkSpaceMode,
        container_name: str,
        settings: Settings,
    ) -> BaseSandbox:
        """Create a processor instance."""
        processor_class = cls._registry.get(sandbox_type.value)

        if processor_class is None:
            available = ", ".join(cls._registry.keys())
            raise ValueError(
                f"Unknown sandbox type '{sandbox_type.value}'. Available: {available}"
            )

        return processor_class(container_name, settings)

    @classmethod
    def list_sandbox_types(cls) -> list[str]:
        return list(cls._registry.keys())
