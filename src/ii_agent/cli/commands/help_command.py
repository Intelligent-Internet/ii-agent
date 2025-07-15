"""
Help command implementation.

This module provides the /help command that displays available commands
and usage information.
"""

from typing import Optional, Any, Dict
from rich.table import Table
from rich.panel import Panel

from .base_command import BaseCommand


class HelpCommand(BaseCommand):
    """Command to display help information."""
    
    @property
    def name(self) -> str:
        return "help"
    
    @property
    def description(self) -> str:
        return "Show available commands and usage information"
    
    async def execute(self, args: str, context: Dict[str, Any]) -> Optional[str]:
        """Execute the help command."""
        command_handler = context.get('command_handler')
        if not command_handler:
            self.console.print("[red]Error: Command handler not available[/red]")
            return None
        
        # Create help table
        help_table = Table(title="Available Commands", style="cyan")
        help_table.add_column("Command", style="green", no_wrap=True)
        help_table.add_column("Description", style="white")
        
        # Add all commands
        for name, command in command_handler.get_all_commands().items():
            help_table.add_row(f"/{name}", command.description)
        
        # Add aliases
        help_table.add_row("/quit", "Alias for /exit")
        help_table.add_row("/truncate", "Alias for /compact")
        
        self.console.print(help_table)
        
        # Show usage tips
        tips_panel = Panel(
            "💡 [bold]Usage Tips:[/bold]\n\n"
            "• Use Tab for command completion\n"
            "• Commands are case-sensitive\n"
            "• Type your message normally for conversation\n"
            "• Use Ctrl+C to interrupt or exit\n"
            "• Command history is saved between sessions\n"
            "• Use /help <command> for detailed help on a specific command",
            title="Tips",
            style="blue"
        )
        self.console.print(tips_panel)
        
        # Show conversation tips
        conversation_panel = Panel(
            "💬 [bold]Conversation Tips:[/bold]\n\n"
            "• Be specific about your goals and requirements\n"
            "• Provide context and relevant details\n"
            "• Break complex tasks into smaller steps\n"
            "• Use /clear to start fresh when context gets too long\n"
            "• Use /compact to reduce context size while keeping important information",
            title="Conversation Tips",
            style="green"
        )
        self.console.print(conversation_panel)
        
        return None
    
    def get_help_text(self) -> str:
        """Get detailed help text for the help command."""
        return (
            "The /help command displays all available commands and usage information.\n\n"
            "Usage:\n"
            "  /help          - Show all available commands\n"
            "  /help <command> - Show detailed help for a specific command\n\n"
            "Examples:\n"
            "  /help\n"
            "  /help exit\n"
            "  /help clear"
        )