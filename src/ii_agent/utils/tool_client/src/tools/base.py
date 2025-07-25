"""Base tool class for external tools."""

from abc import ABC, abstractmethod


class BaseTool(ABC):
    """Base class for tools."""
    
    name = "base_tool"
    description = "Base tool"
    
    @abstractmethod
    def run_impl(self, **kwargs):
        """Implementation of the tool."""
        pass