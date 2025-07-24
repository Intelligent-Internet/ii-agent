"""
Console subscriber for CLI output.

This module provides real-time console output for agent events.
"""

from typing import Optional, Dict, Any, Callable, Tuple
from threading import Lock
import sys
import termios
import tty
import difflib
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.progress import Progress
from rich.table import Table
from rich.syntax import Syntax
from rich.prompt import Prompt, Confirm

from ii_agent.cli.state_persistence import StateManager
from ii_agent.core.event import RealtimeEvent, EventType
from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.core.config.ii_agent_config import IIAgentConfig
from ii_agent.core.storage.models.settings import Settings
from ii_agent.cli.components.spinner import AnimatedSpinner
from ii_agent.cli.components.token_usage import TokenUsageDisplay
from ii_agent.cli.components.todo_panel import TodoPanel
from ii_agent.cli.session_config import SessionConfig


class ConsoleSubscriber:
    """Subscriber that handles console output for agent events."""
    
    def __init__(
        self, 
        minimal: bool = False, 
        config: Optional[IIAgentConfig] = None,
        settings: Optional[Settings] = None,
        confirmation_callback: Optional[Callable[[str, str, bool, str], None]] = None
    ):
        self.minimal = minimal
        self.config = config
        self.settings = settings
        self.confirmation_callback = confirmation_callback
        self._lock = Lock()
        self._current_tool_call: Optional[Dict[str, Any]] = None
        self._thinking_indicator = False
        self.console = Console()
        self._progress: Optional[Progress] = None
        self._spinner: Optional[AnimatedSpinner] = None
        self._token_display = TokenUsageDisplay(self.console)
        self._todo_panel = TodoPanel(self.console)
        
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
            elif event.type == EventType.TOOL_CONFIRMATION:
                self._handle_tool_confirmation_event(event)
    
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
        error_text = Text()
        error_text.append("  ⎿ ", style="red")
        error_text.append(f"Error: {error_msg}", style="red")
        self.console.print(error_text)
    
    def _handle_tool_confirmation_event(self, event: RealtimeEvent) -> None:
        """Handle tool confirmation event with interactive prompt."""
        content = event.content
        tool_call_id = content.get("tool_call_id", "")
        tool_name = content.get("tool_name", "unknown")
        tool_input = content.get("tool_input", {})
        message = content.get("message", "")
        
        # Show the tool details
        self.console.print()
        self.console.print("🔒 [yellow]Tool Confirmation Required[/yellow]")
        self.console.print(f"   Tool: [bold]{tool_name}[/bold]")
        if message:
            self.console.print(f"   Reason: {message}")
        
        # Show key parameters
        if tool_input:
            self.console.print("   Parameters:")
            for key, value in tool_input.items():
                if isinstance(value, str) and len(value) > 100:
                    value = value[:100] + "..."
                self.console.print(f"     {key}: {value}")
        
        self.console.print()
        
        # Check if arrow navigation is enabled in CLI config
        use_arrow_navigation = True  # Default to enabled
        if self.settings and self.settings.cli_config:
            use_arrow_navigation = self.settings.cli_config.enable_arrow_navigation
        
        if use_arrow_navigation:
            # Use the new reliable select menu with arrow navigation
            try:
                from ii_agent.cli.components.select_menu import create_tool_confirmation_menu
                
                menu = create_tool_confirmation_menu(self.console)
                choice_index = menu.select()
                
                if choice_index is not None:
                    choice = str(choice_index + 1)  # Convert 0-based to 1-based
                else:
                    choice = '4'  # Default to "no" if cancelled
                    
            except Exception as e:
                # Fallback to traditional input
                self.console.print(f"[dim]Arrow navigation unavailable: {e}[/dim]")
                use_arrow_navigation = False
        
        if not use_arrow_navigation:
            # Traditional numbered input
            self.console.print("Do you want to execute this tool?")
            self.console.print("[bold green]1.[/bold green] Yes")
            self.console.print("[bold blue]2.[/bold blue] Yes, and don't ask again for this tool this session")
            self.console.print("[bold cyan]3.[/bold cyan] Yes, approve for all tools in this session")
            self.console.print("[bold red]4.[/bold red] No, and tell ii-agent what to do differently")
            self.console.print()
            choice = self._get_traditional_input()
        
        # Handle the choice
        approved = False
        alternative_instruction = ""
        
        if choice == '1':
            self.console.print("✅ [green]Tool execution approved[/green]")
            approved = True
            
        elif choice == '2':
            self.console.print(f"✅ [blue]Tool '{tool_name}' approved for this session[/blue]")
            approved = True
            # Add tool to allow_tools set
            if self.config:
                self.config.allow_tools.add(tool_name)
            
        elif choice == '3':
            self.console.print("✅ [cyan]All tools approved for this session[/cyan]")
            approved = True
            # Set auto_approve_tools to True
            if self.config:
                self.config.set_auto_approve_tools(True)
            
        elif choice == '4':
            self.console.print("❌ [red]Tool execution denied[/red]")
            approved = False
            # Get alternative instruction
            try:
                alternative = input("What should ii-agent do instead? ").strip()
                if alternative:
                    self.console.print(f"📝 Alternative instruction: {alternative}")
                    alternative_instruction = alternative
                else:
                    self.console.print("📝 No alternative instruction provided")
            except (KeyboardInterrupt, EOFError):
                self.console.print("📝 No alternative instruction provided")
        
        # Send response back via callback
        if self.confirmation_callback:
            self.confirmation_callback(tool_call_id, tool_name, approved, alternative_instruction)
        
        self.console.print()
    
    def _get_single_key_choice(self) -> str:
        """Get user choice with single key press (enhanced UX)."""
        try:
            import sys
            import tty
            import termios
            
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            
            try:
                tty.setraw(fd)
                while True:
                    key = sys.stdin.read(1)
                    if key in ['1', '2', '3', '4']:
                        # Echo the choice
                        print(f"\nSelected: {key}")
                        return key
                    elif key == '\x03':  # Ctrl+C
                        print("\nCancelled")
                        return '4'
                    elif key == '\r' or key == '\n':  # Enter without selection
                        continue
                        
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                
        except Exception:
            # Fallback to traditional input
            return self._get_traditional_input()
    
    def _get_traditional_input(self) -> str:
        """Get user choice with traditional input method."""
        while True:
            try:
                choice = input("Enter your choice (1-4): ").strip()
                if choice in ['1', '2', '3', '4']:
                    return choice
                else:
                    self.console.print("[red]Please enter 1, 2, 3, or 4[/red]")
            except (KeyboardInterrupt, EOFError):
                return '4'  # Default to no on interrupt
    
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
        # Clear any status indicators immediately
        self._clear_thinking_indicator()
        
        if not self.minimal:
            # Use simple prefix instead of heavy frames
            from rich.text import Text
            
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
        
        # Special handling for todo tools
        if tool_name in ["TodoRead", "TodoWrite"]:
            tool_text = Text()
            tool_text.append("  📋 ", style="bright_blue")
            tool_text.append(f"Using {tool_name}", style="bright_blue bold")
            self.console.print(tool_text)
            
            # For TodoWrite, show task preview with checkboxes
            if tool_name == "TodoWrite" and "todos" in tool_input:
                todos = tool_input.get("todos", [])
                if todos:
                    # Show first few tasks (limit to 5 for space)
                    max_preview = 5
                    for i, todo in enumerate(todos[:max_preview]):
                        task_text = Text()
                        if i == 0:
                            task_text.append("    ⎿  ", style="dim blue")
                        else:
                            task_text.append("       ", style="dim")
                        
                        # Choose checkbox based on status
                        status = todo.get("status", "pending")
                        if status == "completed":
                            task_text.append("☒ ", style="green")
                        elif status == "in_progress":
                            task_text.append("☐ ", style="cyan")
                        else:  # pending
                            task_text.append("☐ ", style="dim white")
                        
                        # Add task content (truncate if too long)
                        content = todo.get("content", "")
                        if len(content) > 60:
                            content = content[:57] + "..."
                        task_text.append(content, style="white")
                        
                        self.console.print(task_text)
                    
                    # If there are more tasks, show count
                    if len(todos) > max_preview:
                        more_text = Text()
                        more_text.append("       ", style="dim")
                        more_text.append(f"... and {len(todos) - max_preview} more tasks", style="dim cyan")
                        self.console.print(more_text)
            return
        
        # Enhanced tool call display for other tools
        tool_text = Text()
        tool_text.append("  🔧 ", style="bright_blue")
        tool_text.append(f"Using {tool_name}", style="bright_blue bold")
        
        # Show formatted parameters
        if tool_input:
            self.console.print(tool_text)
            self._print_tool_params(tool_input)
        else:
            self.console.print(tool_text)
    
    def _print_tool_params(self, tool_input: Dict[str, Any]) -> None:
        """Print tool parameters with enhanced formatting."""
        for key, value in tool_input.items():
            param_text = Text()
            param_text.append("    ├─ ", style="dim blue")
            param_text.append(f"{key}: ", style="cyan")
            
            # Special handling for file paths
            if key.endswith('_path') or key == 'file_path' or (isinstance(value, str) and ('/' in value or '\\' in value)):
                formatted_path = self._format_file_path(str(value))
                param_text.append(formatted_path, style="yellow")
            # Special handling for long strings
            elif isinstance(value, str) and len(value) > 80:
                truncated = value[:80] + "..."
                # Check if it's likely code/content
                if any(marker in value[:100] for marker in ['{', '[', '<', '\\n', 'def ', 'class ']):
                    param_text.append(f'"{truncated}"', style="dim green")
                else:
                    param_text.append(f'"{truncated}"', style="white")
            else:
                # Regular values
                if isinstance(value, str):
                    param_text.append(f'"{value}"', style="white")
                else:
                    param_text.append(str(value), style="magenta")
            
            self.console.print(param_text)
    
    def _format_file_path(self, path: str) -> str:
        """Format file path for better readability."""
        # Show relative path from working directory if possible
        try:
            import os
            if os.path.isabs(path):
                # Try to make it relative to current working directory
                rel_path = os.path.relpath(path)
                if len(rel_path) < len(path):
                    return rel_path
        except (ValueError, OSError):
            pass
        
        # Truncate very long paths intelligently
        if len(path) > 60:
            parts = path.split('/')
            if len(parts) > 3:
                return f"{parts[0]}/.../{'/'.join(parts[-2:])}"
            else:
                return f"{path[:30]}...{path[-30:]}"
        
        return path
    
    def _print_tool_result(self, tool_name: str, result: str) -> None:
        """Print tool result with enhanced formatting and visual hierarchy."""
        
        if not result.strip():
            return
        
        # Special handling for todo-related tools
        if tool_name.lower() in ["todoread", "todowrite", "todo_read", "todo_write"]:
            self._print_todo_result(tool_name, result)
            return
        
        # Show result header with success indicator
        result_header = Text()
        result_header.append("  ✓ ", style="bright_green")
        result_header.append(f"{tool_name} completed", style="green")
        self.console.print(result_header)
        
        # Print visual connector
        connector = Text()
        connector.append("  │", style="dim green")
        self.console.print(connector)
        
        # Format the result content
        self._format_and_print_result(result)
    
    def _print_todo_result(self, tool_name: str, result: str) -> None:
        """Print todo tool result using the TodoPanel component."""
        try:
            import json
            
            # Parse the result to get todo data
            todos = []
            
            # Try to parse the result as JSON
            try:
                # The result might be a string that contains JSON
                if "todos" in result:
                    # Extract JSON from the result string
                    start_idx = result.find('[')
                    end_idx = result.rfind(']') + 1
                    if start_idx != -1 and end_idx > start_idx:
                        json_str = result[start_idx:end_idx]
                        todos = json.loads(json_str)
                else:
                    # Try direct JSON parse
                    parsed = json.loads(result)
                    if isinstance(parsed, list):
                        todos = parsed
                    elif isinstance(parsed, dict) and 'todos' in parsed:
                        todos = parsed['todos']
            except json.JSONDecodeError:
                # If JSON parsing fails, show raw result
                self._format_and_print_result(result)
                return
            
            # Use TodoPanel to render the todos
            if todos:
                self._todo_panel.render(todos, title=f"📋 {tool_name} Result")
            else:
                # Empty todos
                self._todo_panel.render([], title=f"📋 {tool_name} Result")
                
        except Exception as e:
            # Fallback to regular formatting if something goes wrong
            self.console.print(f"[dim red]Error rendering todo panel: {e}[/dim red]")
            self._format_and_print_result(result)
    
    def _format_and_print_result(self, result: str) -> None:
        """Format and print tool result with appropriate styling."""
        # Truncate very long results
        original_length = len(result)
        if original_length > 2000:
            result = result[:2000] + "\n... (truncated)"
            
        # Detect result type and format accordingly
        if self._is_file_operation_result(result):
            self._print_file_operation_result(result)
        elif self._is_code_content(result):
            self._print_code_result(result)
        elif self._is_structured_data(result):
            self._print_structured_result(result)
        else:
            self._print_plain_result(result)
            
        # Show truncation notice if applicable
        if original_length > 2000:
            truncation_notice = Text()
            truncation_notice.append("  └─ ", style="dim green")
            truncation_notice.append(f"({original_length - 2000} characters truncated)", style="dim yellow")
            self.console.print(truncation_notice)
    
    def _is_file_operation_result(self, result: str) -> bool:
        """Check if result is from a file operation."""
        file_indicators = [
            "Modified file", "Created file", "Deleted file", "File not found",
            "replacement(s)", "added", "removed", "changed"
        ]
        return any(indicator in result for indicator in file_indicators)
    
    def _is_code_content(self, result: str) -> bool:
        """Check if result contains code content."""
        code_indicators = [
            "def ", "class ", "function ", "import ", "from ", "const ", "let ", "var ",
            "#!/", "<?php", "<html", "SELECT", "CREATE", "{", "[", "<"
        ]
        return any(marker in result[:200] for marker in code_indicators)
    
    def _is_structured_data(self, result: str) -> bool:
        """Check if result is structured data (JSON, XML, etc.)."""
        stripped = result.strip()
        return (stripped.startswith('{') and stripped.endswith('}')) or \
               (stripped.startswith('[') and stripped.endswith(']')) or \
               stripped.startswith('<') and stripped.endswith('>')
    
    def _print_file_operation_result(self, result: str) -> None:
        """Print file operation result with special formatting."""
        lines = result.split('\n')
        for line in lines:
            if line.strip():
                formatted_line = Text()
                formatted_line.append("  └─ ", style="dim green")
                
                # Highlight file paths
                if '/' in line or '\\' in line:
                    # Try to identify and highlight file paths
                    words = line.split()
                    for word in words:
                        if '/' in word or '\\' in word:
                            formatted_line.append(word + " ", style="yellow")
                        elif word.endswith('.py') or word.endswith('.js') or word.endswith('.html'):
                            formatted_line.append(word + " ", style="yellow")
                        else:
                            formatted_line.append(word + " ", style="dim white")
                else:
                    formatted_line.append(line, style="dim white")
                
                self.console.print(formatted_line)
    
    def _print_code_result(self, result: str) -> None:
        """Print code content with syntax highlighting."""
        try:
            from rich.panel import Panel
            language = self._detect_language(result)
            syntax = Syntax(result, language, theme="monokai", line_numbers=False, indent_guides=True)
            
            # Create a subtle panel for code
            code_panel = Panel(
                syntax,
                border_style="dim green",
                padding=(0, 1),
                title="Result",
                title_align="left"
            )
            self.console.print(code_panel, style="dim")
        except Exception:
            # Fallback to indented text
            self._print_plain_result(result)
    
    def _print_structured_result(self, result: str) -> None:
        """Print structured data (JSON, XML) with formatting."""
        try:
            import json
            # Try to parse and pretty-print JSON
            if result.strip().startswith(('{', '[')):
                parsed = json.loads(result)
                formatted = json.dumps(parsed, indent=2)
                self._print_code_result(formatted)
                return
        except:
            pass
        
        # Fallback to regular formatting
        self._print_plain_result(result)
    
    def _print_plain_result(self, result: str) -> None:
        """Print plain text result with consistent indentation."""
        lines = result.split('\n')
        for i, line in enumerate(lines):
            if line.strip():  # Skip empty lines
                formatted_line = Text()
                if i == 0:
                    formatted_line.append("  └─ ", style="dim green")
                else:
                    formatted_line.append("     ", style="dim")
                formatted_line.append(line, style="dim white")
                self.console.print(formatted_line)
            elif i > 0 and i < len(lines) - 1:  # Keep internal empty lines
                self.console.print("     ", style="dim")
        
    
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
    
    def render_conversation_history(self, history) -> None:
        """Render conversation history using the same formatting as real-time messages."""
        
        if not history or len(history.message_lists) == 0:
            return
        
        self.console.print()
        self.console.print("📜 [bold cyan]Previous Conversation History:[/bold cyan]")
        self.console.print("─" * 80)
        
        # Display each turn in the conversation using existing formatting methods
        for turn in history.message_lists:
            for message in turn:
                self._render_message(message)
        
        self.console.print("─" * 80)
        self.console.print("📍 [dim]Continuing from here...[/dim]")
        self.console.print()
    
    def _render_message(self, message) -> None:
        """Render a single message using the same formatting as real-time display."""
        
        if hasattr(message, 'text'):
            # User message or text result
            if hasattr(message, 'type') and message.type == 'text_prompt':
                # User input - use same formatting as _print_user_input
                user_text = Text()
                user_text.append("👤 You: ", style="bold blue")
                user_text.append(message.text, style="white")
                self.console.print(user_text)
            elif hasattr(message, 'type') and message.type == 'text_result':
                # Agent response - use same formatting as _print_response
                self._print_response(message.text)
        elif hasattr(message, 'tool_name') and hasattr(message, 'tool_input'):
            # Tool call - use same formatting as _print_tool_call
            self._print_tool_call(message.tool_name, message.tool_input)
        elif hasattr(message, 'tool_output'):
            # Tool result - use same formatting as _print_tool_result
            self._print_tool_result(message.tool_name if hasattr(message, 'tool_name') else "Unknown", message.tool_output)
    
    def cleanup(self) -> None:
        """Clean up resources."""
        # Clean up spinner if active
        if self._spinner:
            self._spinner.stop()
            self._spinner = None

    def _interactive_session_selector(
        self, state_manager: StateManager
    ) -> Tuple[Optional[str], bool]:
        """Interactive session selector with arrow keys - sessions always expand on select."""
        sessions = state_manager.get_available_sessions()
        if not sessions:
            return None, False

        selected_index = 0
        search_mode = False
        search_query = ""
        filtered_sessions = sessions.copy()

        # Check if terminal supports raw mode
        if not sys.stdin.isatty():
            # Fallback to simple selection for non-interactive terminals
            self.console.print("\n[bold cyan]📋 Available Sessions[/bold cyan]")
            for i, session in enumerate(sessions, 1):
                self.console.print(f"  {i}. [bright_white]{session}[/bright_white]")

            self.console.print(
                "\n[dim]Enter session number (1-{}) or name, or 'new' to create a new session[/dim]".format(
                    len(sessions)
                )
            )
            choice = Prompt.ask("Selection", default="")

            if choice.lower() == "new":
                new_session_id = Prompt.ask(
                    "Enter new session name"
                )
                return new_session_id, False
            elif choice.isdigit() and 1 <= int(choice) <= len(sessions):
                return sessions[int(choice) - 1], False
            elif choice in sessions:
                return choice, False
            elif choice:
                # Create new session with the given name
                return choice, False
            else:
                return None, False

        def fuzzy_search_sessions(query: str, sessions_list: list) -> list:
            """Perform fuzzy search on sessions list."""
            if not query.strip():
                return sessions_list

            # Use difflib for fuzzy matching
            matches = difflib.get_close_matches(
                query.lower(),
                [s.lower() for s in sessions_list],
                n=len(sessions_list),
                cutoff=0.1,
            )

            # Return original sessions in order of matches
            result = []
            for match in matches:
                # Find original session name with correct case
                for session in sessions_list:
                    if session.lower() == match:
                        result.append(session)
                        break

            # Add sessions that contain the query as substring (not already included)
            for session in sessions_list:
                if query.lower() in session.lower() and session not in result:
                    result.append(session)

            return result if result else sessions_list

        def get_session_content(session_id: str) -> str:
            """Get session content from agent_state.json."""
            try:
                return state_manager.load_state_summary(session_id)
            except Exception as e:
                return f"❌ Error reading state: {str(e)}"

        def render_session_list():
            """Generate session list content without clearing screen."""
            from rich.console import Group
            from rich.text import Text
            from rich.panel import Panel
            from rich.table import Table

            content = []

            # Create elegant header panel matching the theme
            header_content = Text()
            if search_mode:
                header_content.append("🔍 ", style="yellow")
                header_content.append("Search Sessions", style="bold yellow")
            else:
                header_content.append("📋 ", style="cyan")
                header_content.append("Session Manager", style="bold cyan")

            header_panel = Panel(
                header_content,
                title="🚀 ii-agent",
                title_align="left",
                style="yellow" if search_mode else "cyan",
                border_style="bright_yellow" if search_mode else "bright_blue",
                padding=(0, 1),
            )
            content.append(header_panel)
            content.append(Text())  # Spacer

            # Show search bar if in search mode
            if search_mode:
                search_content = Text()
                search_content.append("Search: ", style="bold yellow")
                search_content.append(
                    search_query, style="bright_white on bright_black"
                )
                search_content.append("█", style="blink bright_white")  # Cursor

                search_panel = Panel(
                    search_content,
                    title="🔍 Type to search",
                    title_align="left",
                    border_style="yellow",
                    style="yellow",
                    padding=(0, 1),
                )
                content.append(search_panel)
                content.append(Text())  # Spacer

            # Create instruction panel with consistent styling
            instructions = Text()
            if search_mode:
                instructions.append("Search mode: ", style="bold yellow")
                instructions.append("Type to search ", style="bright_white")
                instructions.append("• ", style="dim")
                instructions.append("↑/↓ arrows ", style="bright_white")
                instructions.append("• ", style="dim")
                instructions.append("Enter ", style="green")
                instructions.append("to select ", style="white")
                instructions.append("• ", style="dim")
                instructions.append("Esc ", style="red")
                instructions.append("to exit search", style="white")
            else:
                instructions.append("Navigation: ", style="bold blue")
                instructions.append("↑/↓ arrows ", style="bright_white")
                instructions.append("• ", style="dim")
                instructions.append("Enter ", style="green")
                instructions.append("to select ", style="white")
                instructions.append("• ", style="dim")
                instructions.append("'s' ", style="magenta")
                instructions.append("to search ", style="white")
                instructions.append("• ", style="dim")
                instructions.append("'n' ", style="yellow")
                instructions.append("for new session ", style="white")
                instructions.append("• ", style="dim")
                instructions.append("Ctrl+C ", style="red")
                instructions.append("to cancel", style="white")

            content.append(Panel(instructions, border_style="dim blue", padding=(0, 1)))
            content.append(Text())  # Spacer

            # Session items with improved visual hierarchy
            session_table = Table(
                show_header=False, show_edge=False, pad_edge=False, box=None
            )
            session_table.add_column("status", width=3, no_wrap=True)
            session_table.add_column("name", min_width=20)
            session_table.add_column("info", style="dim", no_wrap=True)

            for i, session in enumerate(filtered_sessions):
                if i == selected_index:
                    # Selected session with enhanced styling
                    status_icon = Text("▶", style="bold bright_green")
                    session_id = Text(
                        session, style="bold bright_green on bright_black"
                    )
                    info_text = Text("← selected", style="dim green")
                else:
                    # Non-selected sessions with subtle styling
                    status_icon = Text("•", style="dim blue")
                    session_id = Text(session, style="bright_white")
                    # Add search query highlighting if in search mode
                    if search_mode and search_query.strip():
                        # Highlight matching parts
                        highlighted_name = Text()
                        session_lower = session.lower()
                        query_lower = search_query.lower()
                        if query_lower in session_lower:
                            start = session_lower.find(query_lower)
                            end = start + len(query_lower)
                            highlighted_name.append(
                                session[:start], style="bright_white"
                            )
                            highlighted_name.append(
                                session[start:end], style="bold yellow on bright_black"
                            )
                            highlighted_name.append(session[end:], style="bright_white")
                            session_id = highlighted_name

                    # Add session metadata as info
                    try:
                        sessions_dir = Path.home() / ".ii_agent" / "sessions"
                        state_file = sessions_dir / session / "agent_state.json"
                        if state_file.exists():
                            from datetime import datetime

                            mtime = datetime.fromtimestamp(state_file.stat().st_mtime)
                            info_text = Text(
                                mtime.strftime("%m/%d %H:%M"), style="dim cyan"
                            )
                        else:
                            info_text = Text("no state", style="dim yellow")
                    except Exception:
                        info_text = Text("", style="dim")

                session_table.add_row(status_icon, session_id, info_text)

                # Show expanded content for selected session
                if i == selected_index:
                    session_content = get_session_content(session)
                    detail_panel = Panel(
                        session_content,
                        title="📊 Session Details",
                        title_align="left",
                        border_style="dim green",
                        style="dim",
                        padding=(0, 1),
                    )
                    content.append(detail_panel)

            # Add the session table
            if search_mode and search_query.strip():
                title = f"📂 Search Results ({len(filtered_sessions)} of {len(sessions)} sessions)"
            else:
                title = f"📂 Sessions ({len(filtered_sessions)} available)"

            sessions_panel = Panel(
                session_table,
                title=title,
                title_align="left",
                border_style="dim cyan",
                padding=(0, 1),
            )
            content.append(sessions_panel)

            # Enhanced footer with current selection info
            content.append(Text())  # Spacer

            if filtered_sessions:
                current_session = filtered_sessions[selected_index]
                footer_content = Text()
                footer_content.append("📍 Current selection: ", style="dim")
                footer_content.append(current_session, style="bold cyan")
                footer_content.append(" ", style="dim")
                footer_content.append("(details shown)", style="dim green")

                footer_panel = Panel(
                    footer_content, border_style="dim", style="dim", padding=(0, 1)
                )
                content.append(footer_panel)
            else:
                # No sessions match search
                no_results_content = Text()
                no_results_content.append("❌ No sessions match '", style="dim red")
                no_results_content.append(search_query, style="red")
                no_results_content.append("'", style="dim red")

                footer_panel = Panel(
                    no_results_content,
                    border_style="dim red",
                    style="dim",
                    padding=(0, 1),
                )
                content.append(footer_panel)

            return Group(*content)

        # Print welcome message once at the start
        self.console.clear()
        self.print_welcome()

        # Create live display for session list
        from rich.live import Live

        # Save original terminal settings
        old_settings = termios.tcgetattr(sys.stdin)

        with Live(
            render_session_list(),
            console=self.console,
            refresh_per_second=10,
            screen=False,
        ) as live:

            def update_display():
                live.update(render_session_list())

            try:
                # Set terminal to raw mode
                tty.setcbreak(sys.stdin.fileno())

                while True:
                    # Read a single character
                    char = sys.stdin.read(1)

                    if char == "\x03":  # Ctrl+C
                        return None, True
                    elif char == "\r" or char == "\n":  # Enter
                        if filtered_sessions:
                            return filtered_sessions[selected_index], False
                        else:
                            continue  # No sessions to select
                    elif char == "s" or char == "S":  # Search mode
                        if not search_mode:
                            search_mode = True
                            search_query = ""
                            filtered_sessions = sessions.copy()
                            selected_index = 0
                            update_display()
                    elif char == "\x1b":  # Escape sequence (arrow keys or ESC)
                        # Read the next two characters
                        next_chars = sys.stdin.read(2)
                        if next_chars == "[A":  # Up arrow
                            if filtered_sessions:
                                selected_index = (selected_index - 1) % len(
                                    filtered_sessions
                                )
                                update_display()
                        elif next_chars == "[B":  # Down arrow
                            if filtered_sessions:
                                selected_index = (selected_index + 1) % len(
                                    filtered_sessions
                                )
                                update_display()
                        elif search_mode and not next_chars:  # ESC key (exit search)
                            search_mode = False
                            search_query = ""
                            filtered_sessions = sessions.copy()
                            selected_index = 0
                            update_display()
                    elif search_mode:
                        # Handle search input
                        if char == "\x7f":  # Backspace
                            if search_query:
                                search_query = search_query[:-1]
                                filtered_sessions = fuzzy_search_sessions(
                                    search_query, sessions
                                )
                                if filtered_sessions:
                                    selected_index = min(
                                        selected_index, len(filtered_sessions) - 1
                                    )
                                else:
                                    selected_index = 0
                                update_display()
                        elif char.isprintable():
                            search_query += char
                            filtered_sessions = fuzzy_search_sessions(
                                search_query, sessions
                            )
                            if filtered_sessions:
                                selected_index = min(
                                    selected_index, len(filtered_sessions) - 1
                                )
                            else:
                                selected_index = 0
                            update_display()
                    elif char == "n" or char == "N":  # New session
                        # Restore terminal settings temporarily for input
                        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
                        try:
                            live.stop()
                            self.console.clear()
                            self.console.print(
                                "[bold cyan]📝 Create New Session[/bold cyan]"
                            )
                            return None, False
                        finally:
                            # Always restore raw mode
                            tty.setcbreak(sys.stdin.fileno())

            except KeyboardInterrupt:
                return None, True
            finally:
                # Restore original terminal settings
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)

    async def select_session_config(self, state_manager: StateManager) -> SessionConfig:
        """Set up session configuration with interactive user selection."""
        session_id, cancelled = self._interactive_session_selector(
            state_manager
        )
        config = state_manager.get_state_config(session_id=session_id)
        if cancelled:
            # User cancelled, create new session
            self.console.print(
                f"[green]Creating new session: {config.session_id}[/green]"
            )
        elif config.session_id and  state_manager.is_valid_session(config.session_id):
            # Load existing session
            self.console.print(f"[green]Loading session: {config.session_id}[/green]")
        else:
            self.console.print(
                f"[green]Creating new session: {config.session_id}[/green]"
            )
        return config

    async def should_continue_from_state(self) -> bool:
        """Ask user if they want to continue from previous state in current directory."""
        return Confirm.ask(
            "\n[yellow]Found previous state in current directory. Continue from where you left off?[/yellow]",
            default=True,
        )
