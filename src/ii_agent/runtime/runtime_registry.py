from __future__ import annotations
from typing import Dict, Type, TYPE_CHECKING
from ii_agent.runtime.base import BaseRuntime
from ii_agent.runtime.model.constants import RuntimeMode

if TYPE_CHECKING:
    from ii_agent.core.storage.models.settings import Settings


class RuntimeRegistry:
    """Registry-based factory with decorator support."""

    _registry: Dict[str, Type[BaseRuntime]] = {}

    @classmethod
    def register(cls, runtime_type: RuntimeMode):
        """Decorator to register a runtime class."""

        def decorator(runtime_class: Type[BaseRuntime]):
            cls._registry[runtime_type.value] = runtime_class
            return runtime_class

        return decorator

    @classmethod
    def create(
        cls,
        runtime_type: RuntimeMode,
        session_id: str,
        settings: Settings,
    ) -> BaseRuntime:
        """Create a runtime instance."""
        runtime_class = cls._registry.get(runtime_type.value)

        if runtime_class is None:
            available = ", ".join(cls._registry.keys())
            raise ValueError(
                f"Unknown runtime type '{runtime_type.value}'. Available: {available}"
            )

        return runtime_class(session_id=session_id, settings=settings)

    @classmethod
    def list_runtime_types(cls) -> list[str]:
        return list(cls._registry.keys())
