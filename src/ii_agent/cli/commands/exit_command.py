"""
Exit command implementation.

This module provides the /exit command that terminates the CLI session
with a Rich confirmation dialog.
"""

from typing import Optional, Any, Dict
from rich.panel import Panel
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML

from .base_command import BaseCommand


class ExitCommand(BaseCommand):
    """Command to exit the CLI application."""
    
    @property
    def name(self) -> str:
        return "exit"
    
    @property
    def description(self) -> str:
        return "Exit the application"
    
    async def execute(self, args: str, context: Dict[str, Any]) -> Optional[str]:
        """Execute the exit command."""
        # Show confirmation dialog
        confirm_panel = Panel(
            "Are you sure you want to exit?\n\n"
            "Your current session will be terminated and you will lose any unsaved work.",
            title="Confirm Exit",
            style="yellow"
        )
        self.console.print(confirm_panel)
        
        try:
            # Get confirmation using async prompt
            session = PromptSession()
            response = await session.prompt_async(
                HTML('<ansigreen>Continue with exit? (y/N): </ansigreen>')
            )
            confirmed = response.strip().lower() in ['y', 'yes']
            
            if confirmed:
                # Show goodbye message
                goodbye_panel = Panel(
                    "👋 [bold green]Thank you for using Intelligent Internet Agent![/bold green]\n\n"
                    "Session terminated successfully.",
                    title="Goodbye",
                    style="green"
                )
                self.console.print(goodbye_panel)
                
                # Signal the app to exit
                context['should_exit'] = True
                return "EXIT_COMMAND"
            else:
                self.console.print("[green]Exit cancelled. Continuing session.[/green]")
                return None
                
        except (EOFError, KeyboardInterrupt):
            # User pressed Ctrl+C during confirmation
            self.console.print("[green]Exit cancelled. Continuing session.[/green]")
            return None
    
    def get_help_text(self) -> str:
        """Get detailed help text for the exit command."""
        return (
            "The /exit command terminates the CLI session.\n\n"
            "Usage:\n"
            "  /exit    - Exit the application with confirmation\n"
            "The command will ask for confirmation before exiting to prevent\n"
            "accidental termination of your session.\n\n"
            "Alternative ways to exit:\n"
            "• Press Ctrl+C during input\n"
            "• Press Ctrl+D (EOF) during input\n"
            "• Close the terminal window"
        )