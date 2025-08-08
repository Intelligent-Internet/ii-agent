from typing import Dict, Type

from ii_tool.tools.dev.template_processor.base_processor import BaseProcessor


class WebProcessorRegistry:
    """Registry-based factory with decorator support."""

    _registry: Dict[str, Type[BaseProcessor]] = {}

    @classmethod
    def register(cls, framework_name: str):
        """Decorator to register a processor class."""

        def decorator(processor_class: Type[BaseProcessor]):
            cls._registry[framework_name] = processor_class
            return processor_class

        return decorator

    @classmethod
    def create(
        cls,
        framework_name: str,
        project_dir: str,
    ) -> BaseProcessor:
        """Create a processor instance."""
        processor_class = cls._registry.get(framework_name)

        if processor_class is None:
            available = ", ".join(cls._registry.keys())
            raise ValueError(
                f"Unknown framework '{framework_name}'. Available: {available}"
            )

        return processor_class(project_dir)

    @classmethod
    def list_frameworks(cls) -> list[str]:
        return list(cls._registry.keys())
