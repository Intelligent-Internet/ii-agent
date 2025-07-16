"""
Welcome screen component for CLI.

This module provides a professional welcome screen similar to anon-kode-main
with bordered layout and hierarchical information display.
"""

import os
from typing import Optional, Dict, Any
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.columns import Columns
from rich.align import Align
from ii_agent.cli.theme import get_current_theme
from ii_agent.core.config.llm_config import LLMConfig


class WelcomeScreen:
    """Professional welcome screen with bordered layout."""
    
    def __init__(self, console: Console):
        self.console = console
        self.theme = get_current_theme()
    
    def display(self, 
                workspace_path: str, 
                llm_config: LLMConfig,
                session_name: Optional[str] = None) -> None:
        """Display the welcome screen with system information."""
        
        # Calculate minimum width
        min_width = max(50, len(workspace_path) + 12)
        
        # Create main content
        content = self._create_main_content(workspace_path, llm_config, session_name)
        
        # Create bordered panel
        welcome_panel = Panel(
            content,
            title=f"✻ Welcome to Intelligent Internet Agent",
            title_align="left",
            border_style=self.theme.claude,
            padding=(1, 2),
            width=min_width
        )
        
        self.console.print(welcome_panel)
    
    def _create_main_content(self, 
                           workspace_path: str,
                           llm_config: LLMConfig,
                           session_name: Optional[str] = None) -> str:
        """Create the main content for the welcome screen."""
        
        lines = []
        
        # ASCII logo placeholder
        lines.append(f"🚀 [bold]Intelligent Internet Agent[/bold] research preview!")
        lines.append("")
        
        # Basic information section
        lines.append(f"[{self.theme.secondary_text}]/help for help[/{self.theme.secondary_text}]")
        lines.append(f"[{self.theme.secondary_text}]cwd: {workspace_path}[/{self.theme.secondary_text}]")
        
        # Model information
        model_info = self._get_model_info(llm_config)
        if model_info:
            lines.append(f"[{self.theme.secondary_text}]Model: [bold]{model_info}[/bold][/{self.theme.secondary_text}]")
        
        # Session information
        if session_name:
            lines.append(f"[{self.theme.secondary_text}]Session: [bold]{session_name}[/bold][/{self.theme.secondary_text}]")
        
        # Environment overrides
        overrides = self._get_environment_overrides()
        if overrides:
            lines.append("")
            lines.append("─" * 40)
            lines.append(f"[{self.theme.secondary_text}]Environment Overrides:[/{self.theme.secondary_text}]")
            for override in overrides:
                lines.append(f"[{self.theme.secondary_text}]• {override}[/{self.theme.secondary_text}]")
        
        return "\n".join(lines)
    
    def _get_model_info(self, llm_config: LLMConfig) -> str:
        """Get formatted model information."""
        model_parts = []
        
        if hasattr(llm_config, 'model') and llm_config.model:
            model_parts.append(llm_config.model)
        
        if hasattr(llm_config, 'api_type') and llm_config.api_type:
            model_parts.append(f"({llm_config.api_type.value})")
        
        return " ".join(model_parts) if model_parts else ""
    
    def _get_environment_overrides(self) -> list[str]:
        """Get list of environment overrides."""
        overrides = []
        
        # Check for common environment overrides
        if os.getenv('ANTHROPIC_API_KEY'):
            api_key = os.getenv('ANTHROPIC_API_KEY', '')
            if api_key:
                masked_key = f"sk-ant-…{api_key[-6:]}" if len(api_key) > 10 else "***"
                overrides.append(f"API Key: {masked_key}")
        
        if os.getenv('OPENAI_API_KEY'):
            api_key = os.getenv('OPENAI_API_KEY', '')
            if api_key:
                masked_key = f"sk-…{api_key[-6:]}" if len(api_key) > 10 else "***"
                overrides.append(f"OpenAI Key: {masked_key}")
        
        if os.getenv('GOOGLE_API_KEY'):
            overrides.append("Google API Key: configured")
        
        if os.getenv('DEBUG'):
            overrides.append(f"Debug: {os.getenv('DEBUG')}")
        
        if os.getenv('TEMPERATURE'):
            overrides.append(f"Temperature: {os.getenv('TEMPERATURE')}")
        
        if os.getenv('MAX_TOKENS'):
            overrides.append(f"Max Tokens: {os.getenv('MAX_TOKENS')}")
        
        return overrides
    
    def display_quick_help(self) -> None:
        """Display quick help information."""
        
        help_content = Text()
        help_content.append("Available Commands:", style="bold")
        help_content.append("\\n\\n")
        
        commands = [
            ("/help", "Show detailed help"),
            ("/exit", "Exit the application"),
            ("/clear", "Clear conversation history"),
            ("/compact", "Reduce context size"),
            ("/settings", "Configure LLM settings"),
        ]
        
        for cmd, desc in commands:
            help_content.append(f"  {cmd:<12}", style=self.theme.suggestion)
            help_content.append(f"{desc}", style=self.theme.secondary_text)
            help_content.append("\\n")
        
        help_content.append("\\n")
        help_content.append("Tips:", style="bold")
        help_content.append("\\n")
        help_content.append("• Use Tab for command completion\\n", style=self.theme.secondary_text)
        help_content.append("• Use Ctrl+C to interrupt\\n", style=self.theme.secondary_text)
        help_content.append("• Type naturally for conversation\\n", style=self.theme.secondary_text)
        
        help_panel = Panel(
            help_content,
            title="Quick Help",
            border_style=self.theme.suggestion,
            padding=(1, 2)
        )
        
        self.console.print(help_panel)
    
    def display_status_bar(self, token_count: Optional[int] = None) -> None:
        """Display a status bar with system information."""
        
        status_items = []
        
        # Add token count if available
        if token_count is not None:
            if token_count > 100000:
                status_items.append(Text(f"Tokens: {token_count:,}", style=self.theme.warning))
            else:
                status_items.append(Text(f"Tokens: {token_count:,}", style=self.theme.secondary_text))
        
        # Add mode indicator
        status_items.append(Text("Mode: Chat", style=self.theme.secondary_text))
        
        if status_items:
            status_bar = Text(" | ").join(status_items)
            self.console.print(status_bar)


def create_welcome_screen(console: Console) -> WelcomeScreen:
    """Create a welcome screen instance."""
    return WelcomeScreen(console)