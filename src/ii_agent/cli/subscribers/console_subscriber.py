"""
Console subscriber for CLI output.

This module provides real-time console output for agent events.
"""

from typing import Optional, Dict, Any, Callable
from threading import Lock

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.progress import Progress
from rich.table import Table
from rich.syntax import Syntax

from ii_agent.core.event import RealtimeEvent, EventType
from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.core.config.ii_agent_config import IIAgentConfig
from ii_agent.core.storage.models.settings import Settings
from ii_agent.cli.components.spinner import AnimatedSpinner
from ii_agent.cli.components.token_usage import TokenUsageDisplay
from ii_agent.cli.components.todo_panel import TodoPanel
from ii_agent.cli.components.markdown_renderer import render_markdown, preprocess_markdown_content


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
            elif event.type == EventType.AST_RESPONSE:
                self._handle_ast_response_event(event)
            elif event.type == EventType.AST_TOOL_CALL:
                self._handle_ast_tool_call_event(event)
            elif event.type == EventType.AST_TOOL_RESULT:
                self._handle_ast_tool_result_event(event)
    
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
        """Handle tool confirmation event with enhanced interactive prompt."""
        content = event.content
        tool_call_id = content.get("tool_call_id", "")
        tool_name = content.get("tool_name", "unknown")
        tool_input = content.get("tool_input", {})
        message = content.get("message", "")
        
        # Check if arrow navigation is enabled in CLI config
        use_arrow_navigation = True  # Default to enabled
        if self.settings and self.settings.cli_config:
            use_arrow_navigation = self.settings.cli_config.enable_arrow_navigation
        
        choice = None
        if use_arrow_navigation:
            # Try to use the new enhanced confirmation dialog first
            try:
                from ii_agent.cli.components.tool_confirmation import create_enhanced_tool_confirmation_dialog
                
                dialog = create_enhanced_tool_confirmation_dialog(self.console)
                choice_index = dialog.show_confirmation(tool_name, tool_input, message)
                
                if choice_index is not None:
                    choice = str(choice_index + 1)  # Convert 0-based to 1-based
                else:
                    choice = '4'  # Default to "no" if cancelled
                    
            except Exception as e:
                # Fallback to enhanced select menu
                try:
                    from ii_agent.cli.components.select_menu import create_tool_confirmation_menu
                    
                    menu = create_tool_confirmation_menu(self.console)
                    choice_index = menu.select()
                    
                    if choice_index is not None:
                        choice = str(choice_index + 1)  # Convert 0-based to 1-based
                    else:
                        choice = '4'  # Default to "no" if cancelled
                        
                except Exception as e2:
                    # Last resort: traditional input
                    self.console.print(f"[dim]Enhanced UI unavailable: {e2}[/dim]")
                    use_arrow_navigation = False
        
        if not use_arrow_navigation:
            # Traditional numbered input with enhanced styling
            self._display_tool_confirmation_info(tool_name, tool_input, message)
            choice = self._get_traditional_input()
        
        # Handle the choice with enhanced feedback
        self._process_confirmation_choice(choice, tool_call_id, tool_name)
    
    def _display_tool_confirmation_info(self, tool_name: str, tool_input: Dict[str, Any], message: str) -> None:
        """Display enhanced tool confirmation information in a unified panel."""
        from rich.panel import Panel
        from rich.text import Text
        from rich.columns import Columns
        from rich import box
        
        # Create unified content for the panel with beautiful formatting
        content = Text()
        
        # Header section with nice spacing
        content.append("🔧 ", style="bold cyan")
        content.append("Tool: ", style="bold cyan")
        content.append(f"{tool_name}", style="bold white")
        content.append("\n\n", style="")
        
        # Reason/message if provided with better formatting
        if message:
            content.append("💡 ", style="bold yellow")
            content.append("Reason: ", style="bold yellow")
            content.append(f"{message}", style="white")
            content.append("\n\n", style="")
        
        # Parameters section with enhanced formatting
        if tool_input:
            content.append("📋 ", style="bold cyan")
            content.append("Parameters:", style="bold cyan")
            content.append("\n\n", style="")
            
            for key, value in tool_input.items():
                formatted_value = self._format_parameter_value_for_display(key, value)
                content.append("    • ", style="dim cyan")
                content.append(f"{key}: ", style="cyan")
                content.append(f"{formatted_value}", style="white")
                content.append("\n", style="")
            
            content.append("\n", style="")
        
        # Beautiful separator with padding (adjusted for panel width)
        separator_line = "═" * 78  # Adjusted to match the wider panel width
        content.append(f"{separator_line}\n\n", style="dim blue")
        
        # Options section header with nice styling
        content.append("🎯 ", style="bold cyan")
        content.append("Choose your action:", style="bold cyan")
        content.append("\n\n", style="")
        
        # Enhanced options with icons and colors
        options = [
            ("1", "✅ Execute Once", "green", "Run this tool once and ask again next time"),
            ("2", "🔓 Always Allow This Tool", "blue", "Auto-approve this tool for the rest of this session"),
            ("3", "⚡ Allow All Tools", "yellow", "Auto-approve ALL tools for the rest of this session"),
            ("4", "❌ Deny & Provide Alternative", "red", "Don't execute and tell ii-agent what to do instead")
        ]
        
        for num, text, color, desc in options:
            content.append("    ", style="")
            content.append(f"{num}. ", style="dim")
            content.append(f"{text[0]} ", style=f"bold {color}")  # Icon
            content.append(f"{text[2:]}", style=f"bold {color}")   # Text without icon
            content.append("\n", style="")
            content.append("      ", style="")
            content.append(f"└─ {desc}", style="dim")
            content.append("\n\n", style="")
        
        # Instructions with better formatting
        content.append("═" * 78 + "\n", style="dim blue")
        content.append("   ", style="")
        content.append("⌨️  ", style="dim")
        content.append("↑↓ Navigate", style="dim")
        content.append(" • ", style="dim")
        content.append("Enter Select", style="dim")
        content.append(" • ", style="dim")
        content.append("Esc Cancel", style="dim")
        content.append(" • ", style="dim")
        content.append("1-4 Shortcuts", style="dim")
        
        # Create the unified panel with enhanced styling
        self.console.print()
        unified_panel = Panel(
            content,
            title="🔒 Tool Execution Confirmation",
            title_align="center",
            border_style="bright_yellow",
            box=box.DOUBLE,
            padding=(2, 4),
            width=90,
            expand=False
        )
        self.console.print(unified_panel)
        self.console.print()
    
    def _format_parameter_value_for_display(self, key: str, value: Any) -> str:
        """Format parameter value for enhanced display."""
        if isinstance(value, str):
            # Special handling for file paths
            if key.endswith('_path') or key == 'file_path' or ('/' in value or '\\' in value):
                return self._format_file_path(value)
            
            # Truncate long strings
            if len(value) > 80:
                return f'"{value[:80]}..."'
            else:
                return f'"{value}"'
        else:
            return str(value)
    
    def _display_traditional_confirmation_menu(self) -> None:
        """Display traditional confirmation menu with enhanced styling (now within unified panel)."""
        # This method is deprecated - menu is now shown in _display_tool_confirmation_info
        pass
        
    def _process_confirmation_choice(self, choice: str, tool_call_id: str, tool_name: str) -> None:
        """Process the confirmation choice with enhanced feedback."""
        approved = False
        alternative_instruction = ""
        
        if choice == '1':
            self.console.print("✅ [bold green]Tool execution approved[/bold green]")
            approved = True
            
        elif choice == '2':
            self.console.print(f"🔓 [bold blue]Tool '{tool_name}' approved for this session[/bold blue]")
            approved = True
            # Add tool to allow_tools set
            if self.config:
                self.config.allow_tools.add(tool_name)
            
        elif choice == '3':
            self.console.print("⚡ [bold yellow]All tools approved for this session[/bold yellow]")
            approved = True
            # Set auto_approve_tools to True
            if self.config:
                self.config.set_auto_approve_tools(True)
            
        elif choice == '4':
            self.console.print("❌ [bold red]Tool execution denied[/bold red]")
            approved = False
            # Get alternative instruction with enhanced prompt
            try:
                from rich.prompt import Prompt
                alternative = Prompt.ask(
                    "\n[cyan]What should ii-agent do instead?[/cyan]",
                    console=self.console
                ).strip()
                
                if alternative:
                    self.console.print(f"📝 [green]Alternative instruction recorded:[/green] {alternative}")
                    alternative_instruction = alternative
                else:
                    self.console.print("📝 [dim]No alternative instruction provided[/dim]")
            except (KeyboardInterrupt, EOFError):
                self.console.print("📝 [dim]No alternative instruction provided[/dim]")
        
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
        """Print agent response with clean formatting and markdown rendering."""
        # Clear any status indicators immediately
        self._clear_thinking_indicator()
        
        if not self.minimal:
            from rich.text import Text
            
            # Add spacing before agent response
            self.console.print()
            
            # Create clean response with agent icon
            response_prefix = Text()
            response_prefix.append("🤖 Agent: ", style="green")
            self.console.print(response_prefix)
            
            # Always try to render as markdown first
            try:
                # Preprocess and render with custom markdown renderer
                processed_text = preprocess_markdown_content(text)
                render_markdown(processed_text, self.console)
            except Exception:
                # Fallback to plain text if markdown parsing fails
                self.console.print(text, style="white")
        else:
            self.console.print()
            # For minimal mode, still try basic markdown rendering
            try:
                markdown_prefix = f"🤖 Agent: "
                self.console.print(markdown_prefix, style="green", end="")
                # Preprocess and render with custom markdown renderer
                processed_text = preprocess_markdown_content(text)
                render_markdown(processed_text, self.console)
            except Exception:
                # Fallback to plain text
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
    
    def _handle_ast_response_event(self, event: RealtimeEvent) -> None:
        """Handle agent-as-tool response event."""
        content = event.content
        agent_name = content.get("name", "Agent")
        text = content.get("text", "")
        task_description = content.get("task_description", "")
        
        # Create unique agent key using agent name + description
        agent_key = f"{agent_name}({task_description}): {text}"

        self.console.print(f"🤖🔧 [cyan]{agent_key}[/cyan]")
        
    
    def _handle_ast_tool_call_event(self, event: RealtimeEvent) -> None:
        """Handle agent-as-tool tool call event."""
        content = event.content
        agent_name = content.get("name", "Agent")
        tool_name = content.get("tool_name", "unknown")
        tool_input = content.get("tool_input", {})
        task_description = content.get("task_description", "")
        
        # Create unique agent key using agent name + description
        agent_key = f"{agent_name}({task_description}): {tool_name}"
        
        self.console.print(f"🤖🔧 [cyan]{agent_key}[/cyan]")

    
    def _handle_ast_tool_result_event(self, event: RealtimeEvent) -> None:
        """Handle agent-as-tool tool result event."""
        # TODO: handle this
        pass

    def cleanup(self) -> None:
        """Clean up resources."""
        # Clean up spinner if active
        if self._spinner:
            self._spinner.stop()
            self._spinner = None