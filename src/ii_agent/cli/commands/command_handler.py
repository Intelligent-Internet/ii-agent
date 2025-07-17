"""
Command handler for processing slash commands.

This module provides the main command handler that processes and executes
slash commands in the CLI.
"""

from typing import Dict, Optional, Any
from rich.console import Console

from .base_command import BaseCommand


class CommandHandler:
    """Handles registration and execution of slash commands."""
    
    def __init__(self, console: Console):
        self.console = console
        self.commands: Dict[str, BaseCommand] = {}
        self._register_default_commands()
    
    def _register_default_commands(self) -> None:
        """Register default slash commands."""
        # Import here to avoid circular imports
        from .help_command import HelpCommand
        from .exit_command import ExitCommand
        from .clear_command import ClearCommand
        from .compact_command import CompactCommand
        from .settings_command import SettingsCommand
        
        default_commands = [
            HelpCommand(self.console),
            ExitCommand(self.console),
            ClearCommand(self.console),
            CompactCommand(self.console),
            SettingsCommand(self.console),
        ]
        
        for command in default_commands:
            self.register_command(command)
    
    def register_command(self, command: BaseCommand) -> None:
        """Register a new command."""
        self.commands[command.name] = command
    
    def get_command(self, name: str) -> Optional[BaseCommand]:
        """Get a command by name."""
        return self.commands.get(name)
    
    def get_all_commands(self) -> Dict[str, BaseCommand]:
        """Get all registered commands."""
        return self.commands.copy()
    
    def is_command(self, text: str) -> bool:
        """Check if text is a slash command."""
        return text.strip().startswith('/')
    
    def parse_command(self, text: str) -> tuple[str, str]:
        """Parse command text and return command name and arguments."""
        text = text.strip()
        if not text.startswith('/'):
            return "", text
        
        # Remove the / prefix
        text = text[1:]
        
        # Split into command and arguments
        parts = text.split(None, 1)
        command_name = parts[0]
        args = parts[1] if len(parts) > 1 else ""
        
        return command_name, args
    
    async def execute_command(self, text: str, context: Dict[str, Any]) -> Optional[str]:
        """
        Execute a slash command.
        
        Args:
            text: Command text (including / prefix)
            context: Execution context containing app state
            
        Returns:
            Optional response message or None to continue normal flow
        """
        command_name, args = self.parse_command(text)
        
        if not command_name:
            return None
         
        command = self.get_command(command_name)
        if not command:
            self.console.print(f"[red]Unknown command: /{command_name}[/red]")
            self.console.print("Type [bold]/help[/bold] for available commands.")
            return None
        
        # Validate arguments
        if not command.validate_args(args):
            self.console.print(f"[red]Invalid arguments for command: /{command_name}[/red]")
            return None
        
        # Execute command
        try:
            # Pass the command handler to the context so commands can access other commands
            context['command_handler'] = self
            result = await command.execute(args, context)
            return result
        except Exception as e:
            self.console.print(f"[red]Error executing command /{command_name}: {e}[/red]")
            return None
    
    def get_command_descriptions(self) -> Dict[str, str]:
        """Get descriptions of all commands for completion."""
        descriptions = {}
        for name, command in self.commands.items():
            descriptions[f'/{name}'] = command.description
         
        return descriptions