"""
Clear command implementation.

This module provides the /clear command that clears the conversation history
and frees up context memory.
"""

from typing import Optional, Any, Dict
from rich.panel import Panel
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML

from .base_command import BaseCommand


class ClearCommand(BaseCommand):
    """Command to clear conversation history and free up context."""
    
    @property
    def name(self) -> str:
        return "clear"
    
    @property
    def description(self) -> str:
        return "Clear conversation history and free up context"
    
    async def execute(self, args: str, context: Dict[str, Any]) -> Optional[str]:
        """Execute the clear command."""
        # Show confirmation dialog
        confirm_panel = Panel(
            "This will clear all conversation history and free up context memory.\n\n"
            "⚠️  [bold yellow]Warning:[/bold yellow] This action cannot be undone.\n\n"
            "You will lose:\n"
            "• All previous messages in this conversation\n"
            "• Context about your current task\n"
            "• Any ongoing work state\n\n"
            "Use this when you want to start fresh or when context becomes too long.",
            title="Clear Conversation History",
            style="yellow"
        )
        self.console.print(confirm_panel)
        
        try:
            # Get confirmation using async prompt
            session = PromptSession()
            response = await session.prompt_async(
                HTML('<ansigreen>Continue with clearing history? (y/N): </ansigreen>')
            )
            confirmed = response.strip().lower() in ['y', 'yes']
            
            if confirmed:
                # Clear the conversation history
                app = context.get('app')
                if app and hasattr(app, 'agent_controller') and app.agent_controller:
                    # Clear the state/history
                    if hasattr(app.agent_controller, 'state'):
                        app.agent_controller.state.clear()
                
                # Show success message
                success_panel = Panel(
                    "✅ [bold green]Conversation history cleared successfully![/bold green]\n\n"
                    "• All previous messages have been removed\n"
                    "• Context memory has been freed up\n"
                    "• You can now start a fresh conversation\n\n"
                    "The agent will treat this as a new session.",
                    title="History Cleared",
                    style="green"
                )
                self.console.print(success_panel)
                
                return "CLEAR_COMMAND"
            else:
                self.console.print("[green]Clear cancelled. History preserved.[/green]")
                return None
                
        except (EOFError, KeyboardInterrupt):
            # User pressed Ctrl+C during confirmation
            self.console.print("[green]Clear cancelled. History preserved.[/green]")
            return None
    
    def get_help_text(self) -> str:
        """Get detailed help text for the clear command."""
        return (
            "The /clear command clears all conversation history and frees up context memory.\n\n"
            "Usage:\n"
            "  /clear    - Clear conversation history with confirmation\n\n"
            "What gets cleared:\n"
            "• All previous messages in the conversation\n"
            "• Context about your current task\n"
            "• Any ongoing work state\n"
            "• Cached information from previous interactions\n\n"
            "When to use /clear:\n"
            "• When you want to start a completely fresh conversation\n"
            "• When the context becomes too long and affects performance\n"
            "• When you want to switch to a completely different task\n"
            "• When you're experiencing issues due to conflicting context\n\n"
            "⚠️  Warning: This action cannot be undone!\n\n"
            "Alternative: Use /compact to reduce context size while keeping important information."
        )