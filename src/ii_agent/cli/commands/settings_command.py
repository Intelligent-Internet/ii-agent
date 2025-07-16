"""
Settings command implementation.

This module provides the /settings command that allows users to configure
LLM settings including providers, models, and credentials.
"""

from typing import Optional, Any, Dict
from rich.panel import Panel

from .base_command import BaseCommand
from ii_agent.cli.settings_onboard import modify_settings
from ii_agent.core.storage.settings.file_settings_store import FileSettingsStore


class SettingsCommand(BaseCommand):
    """Command to manage LLM and application settings."""
    
    @property
    def name(self) -> str:
        return "settings"
    
    @property
    def description(self) -> str:
        return "Configure LLM settings and application preferences"
    
    async def execute(self, args: str, context: Dict[str, Any]) -> Optional[str]:
        """Execute the settings command."""
        try:
            # Get the settings store from the context
            config = context.get('config')
            if not config:
                self.console.print("[red]Error: Configuration not available[/red]")
                return None
            
            # Create settings store
            settings_store = await FileSettingsStore.get_instance(config=config, user_id=None)
            
            # Show current settings and allow modification
            self.console.print(Panel(
                "⚙️  [bold]Settings Configuration[/bold]\n\n"
                "This will allow you to configure your LLM settings including:\n"
                "• Provider selection (Anthropic, OpenAI, Gemini)\n"
                "• Model selection\n"
                "• API keys and authentication\n"
                "• Vertex AI configuration (for Gemini)\n"
                "• Temperature and other parameters",
                title="Settings",
                style="cyan"
            ))
            
            # Run the settings modification flow
            await modify_settings(settings_store)
            
            self.console.print("\n[green]Settings configuration completed![/green]")
            self.console.print("[dim]Note: Changes will take effect for new conversations.[/dim]")
            
            return None
            
        except Exception as e:
            self.console.print(f"[red]Error configuring settings: {e}[/red]")
            return None
    
    def validate_args(self, args: str) -> bool:
        """Validate command arguments."""
        # Settings command doesn't require any arguments
        return True
    
    def get_help_text(self) -> str:
        """Get detailed help text for the settings command."""
        return (
            "The /settings command allows you to configure LLM settings and preferences.\n\n"
            "Usage:\n"
            "  /settings      - Open interactive settings configuration\n\n"
            "Features:\n"
            "• Configure LLM provider (Anthropic, OpenAI, Gemini)\n"
            "• Select and configure models\n"
            "• Set API keys and authentication\n"
            "• Configure Vertex AI settings for Gemini\n"
            "• Adjust temperature and other parameters\n"
            "• View current configuration\n\n"
            "Examples:\n"
            "  /settings      - Open settings configuration\n\n"
            "Note: Settings are saved persistently and will be used for future sessions."
        )