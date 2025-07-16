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
from ii_agent.cli.components.spinner import AnimatedSpinner
from ii_agent.cli.components.token_usage import TokenUsageDisplay


class ConsoleSubscriber:
    """Subscriber that handles console output for agent events."""
    
    def __init__(self, minimal: bool = False):
        self.minimal = minimal
        self._lock = Lock()
        self._current_tool_call: Optional[Dict[str, Any]] = None
        self._thinking_indicator = False
        self.console = Console()
        self._progress: Optional[Progress] = None
        self._spinner: Optional[AnimatedSpinner] = None
        self._token_display = TokenUsageDisplay(self.console)
        
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
                # Use animated spinner instead of static text
                self._spinner = AnimatedSpinner(self.console, "Thinking")
                self._spinner.start()
            else:
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
        
        # Simple error format with clean prefix
        from rich.text import Text
        error_text = Text()
        error_text.append("  ⎿ ", style="red")
        error_text.append(f"Error: {error_msg}", style="red")
        self.console.print(error_text)
    
    def _handle_processing_event(self, event: RealtimeEvent) -> None:
        """Handle processing event."""
        content = event.content
        message = content.get("message", "Processing...")
        
        if not self.minimal:
            # Use animated spinner for processing
            if self._spinner:
                self._spinner.stop()
            self._spinner = AnimatedSpinner(self.console, message)
            self._spinner.start()
        else:
            self.console.print(f"⏳ [cyan]{message}[/cyan]")
    
    def _print_status(self, message: str) -> None:
        """Print status message."""
        self.console.print(message)
    
    def _print_response(self, text: str) -> None:
        """Print agent response with clean formatting."""
        # Clear any status indicators
        self._clear_thinking_indicator()
        
        if not self.minimal:
            # Use simple prefix instead of heavy frames
            from rich.text import Text
            from rich.markdown import Markdown
            
            # Add spacing before agent response
            self.console.print()
            
            # Create clean response with agent icon
            response_text = Text()
            response_text.append("🤖 Agent: ", style="green")
            
            # Check if text contains code blocks
            if "```" in text:
                # For code blocks, just add the text and let Rich handle markdown
                response_text.append(text)
                self.console.print(response_text)
            else:
                response_text.append(text, style="white")
                self.console.print(response_text)
        else:
            self.console.print()
            self.console.print(f"🤖 Agent: [white]{text}[/white]")
    
    def _print_tool_call(self, tool_name: str, tool_input: Dict[str, Any]) -> None:
        """Print clean tool call information."""
        from rich.text import Text
        
        # Simple clean format without heavy tables
        tool_text = Text()
        tool_text.append("  🔧 ", style="blue")
        tool_text.append(f"Using {tool_name}", style="blue bold")
        
        # Show key parameters if they exist
        if tool_input:
            key_params = []
            for key, value in tool_input.items():
                if isinstance(value, str) and len(value) > 50:
                    value = value[:50] + "..."
                key_params.append(f"{key}: {value}")
            
            if key_params:
                tool_text.append(f" ({', '.join(key_params[:2])})", style="dim")
        
        self.console.print(tool_text)
    
    def _print_tool_result(self, tool_name: str, result: str) -> None:
        """Print tool result with clean formatting."""
        from rich.text import Text
        
        # Truncate long results
        if len(result) > 1000:
            result = result[:1000] + "\n... (truncated)"
        
        # Don't show the completed line - just show the result with proper formatting
        if result.strip():
            # Print connector
            connector = Text()
            connector.append("  ⎿ ", style="dim")
            self.console.print(connector)
            
            # Enhanced code detection and syntax highlighting
            code_indicators = [
                "{", "[", "<", "def ", "class ", "import ", "function", "const ", "let ", "var ",
                "#!/", "<?php", "<html", "SELECT", "CREATE", "INSERT", "UPDATE", "DELETE"
            ]
            
            if any(marker in result for marker in code_indicators):
                # Try to detect language and show with syntax highlighting
                language = self._detect_language(result)
                try:
                    syntax = Syntax(result, language, theme="monokai", line_numbers=False)
                    # Indent the code block slightly
                    from rich.panel import Panel
                    code_panel = Panel(syntax, border_style="dim", padding=(0, 1))
                    self.console.print(code_panel)
                except Exception:
                    # Simple indented text fallback
                    indented_result = "\n".join(f"    {line}" for line in result.split("\n"))
                    self.console.print(indented_result, style="dim")
            else:
                # Simple indented text
                indented_result = "\n".join(f"    {line}" for line in result.split("\n"))
                self.console.print(indented_result, style="dim")
        
        # Add spacing after tool result
        self.console.print()
    
    def _print_error(self, message: str) -> None:
        """Print error message."""
        self.console.print(f"[red]{message}[/red]")
    
    def _clear_thinking_indicator(self) -> None:
        """Clear the thinking indicator."""
        if self._thinking_indicator:
            if self._spinner:
                self._spinner.stop()
                self._spinner = None
            self._thinking_indicator = False
    
    def print_welcome(self) -> None:
        """Print welcome message."""
        if not self.minimal:
            welcome_panel = Panel(
                "🚀 [bold blue]Intelligent Internet Agent - CLI[/bold blue]\n\n"
                "• Type [bold]/exit[/bold] to end the session\n"
                "• Type [bold]/help[/bold] for available commands\n"
                "• Use [bold]Ctrl+C[/bold] to interrupt the agent\n"
                "• Type [bold]/clear[/bold] to clear conversation history\n"
                "• Type [bold]/compact[/bold] to truncate context\n"
                "• Type [bold]/settings[/bold] to configure LLM settings",
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
            config_items.append(("Model", config.model))
            config_items.append(("Provider", config.api_type.value))
            config_items.append(("Temperature", str(config.temperature)))
            config_items.append(("Max Tokens", str(config.max_message_chars)))
             
            
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
    
    def _detect_language(self, code: str) -> str:
        """Detect programming language from code content."""
        # Simple language detection based on content
        if "def " in code or "import " in code or "class " in code:
            return "python"
        elif "function" in code or "const " in code or "let " in code:
            return "javascript"
        elif "<?php" in code:
            return "php"
        elif "<html" in code or "<div" in code:
            return "html"
        elif "SELECT" in code or "CREATE" in code or "INSERT" in code:
            return "sql"
        elif "{" in code and "}" in code:
            return "json"
        else:
            return "text"
    
    def display_token_usage(self, token_count: int, cached_tokens: Optional[int] = None) -> None:
        """Display token usage information."""
        self._token_display.display_usage(token_count, cached_tokens)
    
    def cleanup(self) -> None:
        """Clean up resources."""
        # Clean up spinner if active
        if self._spinner:
            self._spinner.stop()
            self._spinner = None