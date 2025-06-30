from typing import Dict, Type

from ii_agent.prompts.system_prompt import SystemPromptBuilder
from ii_agent.tools.clients.terminal_client import TerminalClient
from ii_agent.utils.web_template_processor.base_processor import BaseProcessor
from ii_agent.utils.workspace_manager import WorkspaceManager


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
        workspace_manager: WorkspaceManager,
        terminal_client: TerminalClient,
        system_prompt_builder: SystemPromptBuilder,
        project_name: str,
    ) -> BaseProcessor:
        """Create a processor instance."""
        processor_class = cls._registry.get(framework_name)

        if processor_class is None:
            available = ", ".join(cls._registry.keys())
            raise ValueError(
                f"Unknown framework '{framework_name}'. Available: {available}"
            )

        return processor_class(
            workspace_manager, terminal_client, system_prompt_builder, project_name
        )

    @classmethod
    def list_frameworks(cls) -> list[str]:
        return list(cls._registry.keys())
