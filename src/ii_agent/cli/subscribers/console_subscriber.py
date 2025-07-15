"""
Console subscriber for CLI output.

This module provides real-time console output for agent events.
"""

import sys
import time
from typing import Optional, Dict, Any
from threading import Lock

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.syntax import Syntax
from rich.markdown import Markdown
from rich.rule import Rule
from rich import print as rich_print

from ii_agent.core.event import RealtimeEvent, EventType
from ii_agent.core.config.llm_config import LLMConfig


class ConsoleSubscriber:
    """Subscriber that handles console output for agent events."""
    
    def __init__(self, minimal: bool = False):
        self.minimal = minimal
        self._lock = Lock()
        self._current_tool_call: Optional[Dict[str, Any]] = None
        self._thinking_indicator = False
        self.console = Console()
        self._progress: Optional[Progress] = None
        
    def handle_event(self, event: RealtimeEvent) -> None:
        """Handle an event by outputting to console."""
        with self._lock: 
            if event.type == EventType.AGENT_THINKING:
                self._handle_thinking_event(event)
            elif event.type == EventType.TOOL_CALL:
                self._handle_tool_call_event(event)
            elif event.type == EventType.TOOL_RESULT:
                self._handle_tool_result_event(event)
            elif event.type == EventType.AGENT_RESPONSE:
                self._handle_agent_response_event(event)
            elif event.type == EventType.AGENT_RESPONSE_INTERRUPTED:
                self._handle_interrupted_event(event)
            elif event.type == EventType.ERROR:
                self._handle_error_event(event)
            elif event.type == EventType.PROCESSING:
                self._handle_processing_event(event)
    
    def _handle_thinking_event(self, event: RealtimeEvent) -> None:
        """Handle agent thinking event."""
        if not self._thinking_indicator:
            if not self.minimal:
                self.console.print("🤔 [cyan]Agent is thinking...[/cyan]")
            self._thinking_indicator = True
    
    def _handle_tool_call_event(self, event: RealtimeEvent) -> None:
        """Handle tool call event."""
        self._clear_thinking_indicator()
        
        content = event.content
        tool_name = content.get("tool_name", "unknown")
        tool_input = content.get("tool_input", {})
        
        self._current_tool_call = content
        
        if not self.minimal:
            self._print_tool_call(tool_name, tool_input)
        else:
            self.console.print(f"🔧 [blue]Using tool:[/blue] [bold]{tool_name}[/bold]")
    
    def _handle_tool_result_event(self, event: RealtimeEvent) -> None:
        """Handle tool result event."""
        content = event.content
        tool_name = content.get("tool_name", "unknown")
        result = content.get("result", "")
        
        if not self.minimal:
            self._print_tool_result(tool_name, result)
        else:
            self.console.print(f"✅ [green]Tool completed:[/green] [bold]{tool_name}[/bold]")
        
        self._current_tool_call = None
    
    def _handle_agent_response_event(self, event: RealtimeEvent) -> None:
        """Handle agent response event."""
        self._clear_thinking_indicator()
        
        content = event.content
        text = content.get("text", "")
        
        if text.strip():
            self._print_response(text)
    
    def _handle_interrupted_event(self, event: RealtimeEvent) -> None:
        """Handle interrupted event."""
        self._clear_thinking_indicator()
        
        content = event.content
        text = content.get("text", "")
        
        self.console.print(f"⚠️ [yellow]Interrupted:[/yellow] {text}")
    
    def _handle_error_event(self, event: RealtimeEvent) -> None:
        """Handle error event."""
        self._clear_thinking_indicator()
        
        content = event.content
        error_msg = content.get("error", "Unknown error")
        
        self.console.print(Panel(f"❌ Error: {error_msg}", style="red"))
    
    def _handle_processing_event(self, event: RealtimeEvent) -> None:
        """Handle processing event."""
        content = event.content
        message = content.get("message", "Processing...")
        self.console.print(f"⏳ [cyan]{message}[/cyan]")
    
    def _print_status(self, message: str) -> None:
        """Print status message."""
        self.console.print(message)
    
    def _print_response(self, text: str) -> None:
        """Print agent response."""
        # Clear any status indicators
        self._clear_thinking_indicator()
        
        if not self.minimal:
            # Check if text contains code blocks or structured content
            if "```" in text:
                # Use Markdown rendering for code blocks
                self.console.print(Panel(Markdown(text), title="🤖 Agent Response", style="green"))
            else:
                self.console.print(Panel(text, title="🤖 Agent Response", style="green"))
        else:
            self.console.print(f"🤖 [green]{text}[/green]")
    
    def _print_tool_call(self, tool_name: str, tool_input: Dict[str, Any]) -> None:
        """Print detailed tool call information."""
        table = Table(title=f"🔧 Tool Call: {tool_name}", style="blue")
        table.add_column("Parameter", style="cyan")
        table.add_column("Value", style="white")
        
        if tool_input:
            for key, value in tool_input.items():
                # Truncate long values
                if isinstance(value, str) and len(value) > 200:
                    value = value[:200] + "..."
                table.add_row(key, str(value))
        
        self.console.print(table)
    
    def _print_tool_result(self, tool_name: str, result: str) -> None:
        """Print tool result."""
        # Truncate long results
        if len(result) > 1000:
            result = result[:1000] + "\n... (truncated)"
        
        # Try to detect if result contains code or structured data
        if any(marker in result for marker in ["{", "[", "<", "def ", "class ", "import "]):
            try:
                # Try to syntax highlight if it looks like code
                syntax = Syntax(result, "python", theme="monokai", line_numbers=True)
                self.console.print(Panel(syntax, title=f"✅ Tool Result: {tool_name}", style="green"))
            except Exception:
                self.console.print(Panel(result, title=f"✅ Tool Result: {tool_name}", style="green"))
        else:
            self.console.print(Panel(result, title=f"✅ Tool Result: {tool_name}", style="green"))
    
    def _print_error(self, message: str) -> None:
        """Print error message."""
        self.console.print(f"[red]{message}[/red]")
    
    def _clear_thinking_indicator(self) -> None:
        """Clear the thinking indicator."""
        if self._thinking_indicator:
            self._thinking_indicator = False
    
    def print_welcome(self) -> None:
        """Print welcome message."""
        if not self.minimal:
            welcome_panel = Panel(
                "🚀 [bold blue]Intelligent Internet Agent - CLI[/bold blue]\n\n"
                "• Type [bold]/exit[/bold] or [bold]/quit[/bold] to end the session\n"
                "• Type [bold]/help[/bold] for available commands\n"
                "• Use [bold]Ctrl+C[/bold] to interrupt the agent\n"
                "• Type [bold]/clear[/bold] to clear conversation history\n"
                "• Type [bold]/compact[/bold] to truncate context",
                title="Welcome",
                style="cyan"
            )
            self.console.print(welcome_panel)
    
    def print_goodbye(self) -> None:
        """Print goodbye message."""
        if not self.minimal:
            goodbye_panel = Panel(
                "👋 [bold green]Session ended. Goodbye![/bold green]",
                title="Farewell",
                style="green"
            )
            self.console.print(goodbye_panel)
    
    def print_session_info(self, session_name: Optional[str] = None) -> None:
        """Print session information."""
        if not self.minimal and session_name:
            session_panel = Panel(
                f"📝 [bold]Active Session[/bold]\n\nName: [cyan]{session_name}[/cyan]",
                title="Session Info",
                style="yellow"
            )
            self.console.print(session_panel)
    
    def print_config_info(self, config: LLMConfig) -> None:
        """Print configuration information."""
        if not self.minimal:
            table = Table(title="🔧 Agent Configuration", style="blue")
            table.add_column("Setting", style="cyan")
            table.add_column("Value", style="white")
            
            # Extract key config attributes
            config_items = []
            
            # Common LLM config attributes
            if hasattr(config, 'model_name') and config.model_name:
                config_items.append(("Model", config.model_name))
            if hasattr(config, 'provider') and config.provider:
                config_items.append(("Provider", config.provider))
            if hasattr(config, 'temperature') and config.temperature is not None:
                config_items.append(("Temperature", str(config.temperature)))
            if hasattr(config, 'max_tokens') and config.max_tokens:
                config_items.append(("Max Tokens", str(config.max_tokens)))
            if hasattr(config, 'api_base') and config.api_base:
                config_items.append(("API Base", config.api_base))
            
            # Display formatted config items
            if config_items:
                for key, value in config_items:
                    table.add_row(key, value)
            else:
                # Fallback to string representation if no known attributes
                table.add_row("Configuration", str(config))
            
            self.console.print(table)
    
    def print_workspace_info(self, workspace_path: str) -> None:
        """Print workspace information."""
        if not self.minimal:
            workspace_panel = Panel(
                f"📂 [bold]Workspace[/bold]\n\nPath: [cyan]{workspace_path}[/cyan]",
                title="Workspace Info",
                style="yellow"
            )
            self.console.print(workspace_panel)