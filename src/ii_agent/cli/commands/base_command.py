"""
Base command class for CLI commands.

This module provides the base class for all CLI slash commands.
"""

from abc import ABC, abstractmethod
from typing import Optional, Any, Dict
from rich.console import Console


class BaseCommand(ABC):
    """Base class for all CLI commands."""
    
    def __init__(self, console: Console):
        self.console = console
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Command name (without the / prefix)."""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Command description for help text."""
        pass
    
    @abstractmethod
    async def execute(self, args: str, context: Dict[str, Any]) -> Optional[str]:
        """
        Execute the command.
        
        Args:
            args: Command arguments as a string
            context: Command execution context containing app state
            
        Returns:
            Optional response message or None to continue normal flow
        """
        pass
    
    def validate_args(self, args: str) -> bool:
        """
        Validate command arguments.
        
        Args:
            args: Command arguments as a string
            
        Returns:
            True if arguments are valid, False otherwise
        """
        return True
    
    def get_help_text(self) -> str:
        """
        Get detailed help text for the command.
        
        Returns:
            Detailed help text
        """
        return self.description