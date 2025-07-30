"""
Enhanced tool confirmation dialog component.

This module provides a modern, visually appealing confirmation dialog
for tool execution requests with improved UX and visual hierarchy.
"""

import sys
import os
from typing import List, Optional, Dict, Any
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.columns import Columns
from rich.box import ROUNDED
from rich import box


class ToolConfirmationDialog:
    """Enhanced tool confirmation dialog with rich visual design."""
    
    def __init__(self, console: Optional[Console] = None):
        """
        Initialize the confirmation dialog.
        
        Args:
            console: Rich console instance (creates new if None)
        """
        self.console = console or Console()
        self.selected_index = 0
        self._last_render_lines = 0
        
        # Define confirmation options with enhanced styling
        self.options = [
            {
                "key": "1",
                "text": "Execute Once",
                "description": "Run this tool once and ask again next time",
                "icon": "✅",
                "style": "green",
                "risk": "low"
            },
            {
                "key": "2", 
                "text": "Always Allow This Tool",
                "description": "Auto-approve this tool for the rest of this session",
                "icon": "🔓",
                "style": "blue",
                "risk": "medium"
            },
            {
                "key": "3",
                "text": "Allow All Tools",
                "description": "Auto-approve ALL tools for the rest of this session",
                "icon": "⚡",
                "style": "yellow",
                "risk": "high"
            },
            {
                "key": "4",
                "text": "Deny & Provide Alternative",
                "description": "Don't execute and tell ii-agent what to do instead",
                "icon": "❌",
                "style": "red",
                "risk": "safe"
            }
        ]
    
    def show_confirmation(self, 
                         tool_name: str, 
                         tool_input: Dict[str, Any], 
                         message: str = "") -> Optional[int]:
        """
        Show the enhanced confirmation dialog in a unified panel.
        
        Args:
            tool_name: Name of the tool to be executed
            tool_input: Tool parameters
            message: Optional reason/message for confirmation
            
        Returns:
            Selected option index (0-based) or None if cancelled
        """
        try:
            # Hide cursor
            sys.stdout.write('\033[?25l')
            sys.stdout.flush()
            
            # Store the tool info for re-rendering
            self._tool_name = tool_name
            self._tool_input = tool_input
            self._message = message
            
            # Initial render of the unified panel
            self._render_unified_panel()
            
            # Show interactive selection within the panel
            return self._show_unified_interactive_menu()
            
        except KeyboardInterrupt:
            self._clear_previous_render()
            self.console.print("❌ [red]Confirmation cancelled[/red]")
            return None
            
        finally:
            # Show cursor and restore cursor position
            sys.stdout.write('\033[?25h')
            sys.stdout.flush()
    
    def _render_confirmation_panel(self, 
                                  tool_name: str, 
                                  tool_input: Dict[str, Any], 
                                  message: str) -> None:
        """Render the unified confirmation panel with all information."""
        
        # Create unified content including tool info AND options
        unified_content = self._create_unified_content(tool_name, tool_input, message)
        
        # Create the single unified panel
        main_panel = Panel(
            unified_content,
            title="🔒 Tool Execution Confirmation",
            title_align="center",
            border_style="bright_yellow",
            box=box.DOUBLE,
            padding=(2, 4),
            width=90,
            expand=False
        )
        
        self.console.print()
        self.console.print(main_panel)
        self.console.print()
    
    def _create_unified_content(self, 
                               tool_name: str, 
                               tool_input: Dict[str, Any], 
                               message: str) -> Text:
        """Create unified content with tool info and options in one beautifully styled panel."""
        content = Text()
        
        # Header section with nice spacing
        content.append("🔧 ", style="bold cyan")
        content.append("Tool: ", style="bold cyan")
        content.append(f"{tool_name}", style="bold white")
        
        # Add some visual breathing room
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
                # Better indentation and formatting
                content.append("    • ", style="dim cyan")
                content.append(f"{key}: ", style="cyan")
                
                # Format value based on type and length
                formatted_value = self._format_parameter_value(key, value)
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
        
        # Enhanced options with better spacing and visual hierarchy
        for i, option in enumerate(self.options):
            # Create a visual block for each option
            if i == self.selected_index:
                # Selected option with enhanced highlighting
                content.append("  ▶ ", style="bold yellow")
                content.append(f"{option['key']}. ", style="bold white")
                content.append(f"{option['icon']} ", style=f"bold {option['style']}")
                content.append(f"{option['text']}", style=f"bold {option['style']}")
                content.append("\n", style="")
                content.append("      ", style="")
                content.append(f"└─ {option['description']}", style="dim italic")
            else:
                # Normal option with subtle styling
                content.append("    ", style="")
                content.append(f"{option['key']}. ", style="dim")
                content.append(f"{option['icon']} ", style=f"{option['style']}")
                content.append(f"{option['text']}", style=f"bold {option['style']}")
                content.append("\n", style="")
                content.append("      ", style="")
                content.append(f"└─ {option['description']}", style="dim")
            
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
        
        return content
    
    def _create_tool_info_section(self, 
                                 tool_name: str, 
                                 tool_input: Dict[str, Any], 
                                 message: str) -> Text:
        """Create the tool information section (kept for compatibility)."""
        info = Text()
        
        # Tool header
        info.append("🔧 Tool: ", style="bold cyan")
        info.append(f"{tool_name}\n", style="bold white")
        
        # Reason/message if provided
        if message:
            info.append("\n💡 Reason: ", style="bold yellow")
            info.append(f"{message}\n", style="white")
        
        # Parameters section
        if tool_input:
            info.append("\n📋 Parameters:\n", style="bold cyan")
            for key, value in tool_input.items():
                info.append(f"   • {key}: ", style="cyan")
                
                # Format value based on type and length
                formatted_value = self._format_parameter_value(key, value)
                info.append(f"{formatted_value}\n", style="white")
        
        return info
    
    def _format_parameter_value(self, key: str, value: Any) -> str:
        """Format parameter value for display."""
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
    
    def _format_file_path(self, path: str) -> str:
        """Format file path for better readability."""
        try:
            import os
            if os.path.isabs(path):
                rel_path = os.path.relpath(path)
                if len(rel_path) < len(path):
                    return rel_path
        except (ValueError, OSError):
            pass
        
        if len(path) > 60:
            parts = path.split('/')
            if len(parts) > 3:
                return f"{parts[0]}/.../{'/'.join(parts[-2:])}"
            else:
                return f"{path[:30]}...{path[-30:]}"
        
        return path
    
    def _render_unified_panel(self) -> None:
        """Render the unified panel with current selection state."""
        # Clear the entire screen and move to top for consistent rendering
        if hasattr(self, '_initial_render_done'):
            # Clear from current position to end of screen
            sys.stdout.write('\033[0J')
            # Move cursor to saved position
            sys.stdout.write('\033[u')
            sys.stdout.flush()
        else:
            # First render - save the cursor position
            sys.stdout.write('\033[s')
            self._initial_render_done = True
        
        # Create and render the unified panel
        unified_content = self._create_unified_content(self._tool_name, self._tool_input, self._message)
        
        main_panel = Panel(
            unified_content,
            title="🔒 Tool Execution Confirmation",
            title_align="center",
            border_style="bright_yellow",
            box=box.DOUBLE,
            padding=(2, 4),
            width=90,
            expand=False
        )
        
        self.console.print()
        self.console.print(main_panel)
    
    def _show_unified_interactive_menu(self) -> Optional[int]:
        """Show interactive menu within the unified panel."""
        while True:
            key = self._get_key()
            
            if key is None:
                continue
            
            # Handle key presses
            if key == 'up':
                self.selected_index = (self.selected_index - 1) % len(self.options)
                self._render_unified_panel()
                
            elif key == 'down':
                self.selected_index = (self.selected_index + 1) % len(self.options)
                self._render_unified_panel()
                
            elif key == 'enter':
                self._clear_previous_render()
                selected_option = self.options[self.selected_index]
                self._show_selection_confirmation(selected_option)
                return self.selected_index
                
            elif key in ('escape', 'ctrl_c'):
                self._clear_previous_render()
                self.console.print("❌ [red]Confirmation cancelled[/red]")
                return None
                
            elif key.isdigit():
                # Number shortcut
                num = int(key) - 1
                if 0 <= num < len(self.options):
                    self.selected_index = num
                    self._clear_previous_render()
                    selected_option = self.options[self.selected_index]
                    self._show_selection_confirmation(selected_option)
                    return self.selected_index
    
    def _show_interactive_menu(self) -> Optional[int]:
        """Show the interactive option selection menu."""
        # Initial render
        self._render_options_menu()
        
        while True:
            key = self._get_key()
            
            if key is None:
                continue
            
            # Handle key presses
            if key == 'up':
                self.selected_index = (self.selected_index - 1) % len(self.options)
                self._clear_options_menu()
                self._render_options_menu()
                
            elif key == 'down':
                self.selected_index = (self.selected_index + 1) % len(self.options)
                self._clear_options_menu()
                self._render_options_menu()
                
            elif key == 'enter':
                self._clear_options_menu()
                selected_option = self.options[self.selected_index]
                self._show_selection_confirmation(selected_option)
                return self.selected_index
                
            elif key in ('escape', 'ctrl_c'):
                self._clear_options_menu()
                self.console.print("❌ [red]Confirmation cancelled[/red]")
                return None
                
            elif key.isdigit():
                # Number shortcut
                num = int(key) - 1
                if 0 <= num < len(self.options):
                    self.selected_index = num
                    self._clear_options_menu()
                    selected_option = self.options[self.selected_index]
                    self._show_selection_confirmation(selected_option)
                    return self.selected_index
    
    def _render_options_menu(self) -> None:
        """Render the options selection menu."""
        line_count = 0
        
        # Menu title
        title_text = "🎯 Choose your action:"
        print(f"\033[96m{title_text}\033[0m")
        line_count += 1
        
        print()  # Spacing
        line_count += 1
        
        # Render each option
        for i, option in enumerate(self.options):
            is_selected = (i == self.selected_index)
            self._render_option(option, is_selected)
            line_count += 1
        
        # Instructions
        print()
        print(f"\033[90m↑↓ Navigate • Enter Select • Esc Cancel • 1-4 Shortcuts\033[0m")
        line_count += 2
        
        self._last_render_lines = line_count
    
    def _render_option(self, option: Dict[str, Any], is_selected: bool) -> None:
        """Render a single option with enhanced styling."""
        icon = option["icon"]
        key = option["key"]
        text = option["text"]
        description = option["description"]
        risk = option["risk"]
        
        # Build the option line
        if is_selected:
            # Selected option with colored background based on risk level
            bg_color = self._get_risk_background_color(risk)
            prefix = "▶ "
            option_line = f"{prefix}{key}. {icon} {text}"
            print(f"\033[{bg_color}m\033[97m{option_line}\033[0m")
            
            # Show description for selected option
            desc_line = f"     {description}"
            print(f"\033[90m{desc_line}\033[0m")
        else:
            # Normal option with colored text
            text_color = self._get_risk_text_color(risk)
            prefix = "  "
            option_line = f"{prefix}{key}. {icon} {text}"
            print(f"\033[{text_color}m{option_line}\033[0m")
    
    def _get_risk_background_color(self, risk: str) -> str:
        """Get ANSI background color code based on risk level."""
        colors = {
            "safe": "42",    # Green background
            "low": "42",     # Green background
            "medium": "44",  # Blue background
            "high": "43",    # Yellow background
            "danger": "41"   # Red background
        }
        return colors.get(risk, "44")  # Default to blue
    
    def _get_risk_text_color(self, risk: str) -> str:
        """Get ANSI text color code based on risk level."""
        colors = {
            "safe": "92",    # Bright green
            "low": "92",     # Bright green
            "medium": "94",  # Bright blue
            "high": "93",    # Bright yellow
            "danger": "91"   # Bright red
        }
        return colors.get(risk, "37")  # Default to white
    
    def _show_selection_confirmation(self, option: Dict[str, Any]) -> None:
        """Show confirmation of the selected option."""
        icon = option["icon"]
        text = option["text"]
        risk = option["risk"]
        
        # Color based on risk level
        if risk == "high":
            style = "bold yellow"
        elif risk == "medium":
            style = "bold blue"
        elif risk in ["low", "safe"]:
            style = "bold green"
        else:
            style = "bold red"
        
        self.console.print(f"{icon} [{style}]Selected: {text}[/{style}]")
    
    def _clear_options_menu(self) -> None:
        """Clear the options menu from terminal."""
        if self._last_render_lines > 0:
            # Move cursor up to start of our content
            sys.stdout.write(f'\033[{self._last_render_lines}A')
            # Clear from cursor to end of screen
            sys.stdout.write('\033[0J')
            sys.stdout.flush()
    
    def _clear_previous_render(self) -> None:
        """Clear the previous rendering from terminal."""
        if hasattr(self, '_last_render_lines') and self._last_render_lines > 0:
            # Move up and clear more lines to account for the panel structure
            sys.stdout.write(f'\033[{self._last_render_lines + 1}A')
            sys.stdout.write('\033[0J')
            sys.stdout.flush()
            self._last_render_lines = 0
    
    def _get_key(self) -> Optional[str]:
        """
        Get a single keypress from stdin.
        
        Returns:
            Key identifier or None if failed
        """
        if os.name == 'nt':  # Windows
            try:
                import msvcrt
                key = msvcrt.getch()
                if key == b'\xe0':  # Arrow key prefix
                    key = msvcrt.getch()
                    if key == b'H':
                        return 'up'
                    elif key == b'P':
                        return 'down'
                elif key == b'\r':
                    return 'enter'
                elif key == b'\x03':
                    return 'ctrl_c'
                elif key == b'\x1b':
                    return 'escape'
                else:
                    return key.decode('utf-8', errors='ignore')
            except Exception:
                return None
        else:  # Unix/Linux/macOS
            try:
                import tty, termios
                fd = sys.stdin.fileno()
                old_settings = termios.tcgetattr(fd)
                tty.setraw(fd)
                
                try:
                    key = sys.stdin.read(1)
                    if key == '\x1b':  # Escape sequence
                        # Read the rest of the escape sequence
                        key += sys.stdin.read(2)
                        if key == '\x1b[A':
                            return 'up'
                        elif key == '\x1b[B':
                            return 'down'
                        elif key == '\x1b[C':
                            return 'right'
                        elif key == '\x1b[D':
                            return 'left'
                        else:
                            return 'escape'
                    elif key == '\r' or key == '\n':
                        return 'enter'
                    elif key == '\x03':
                        return 'ctrl_c'
                    else:
                        return key
                finally:
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            except Exception:
                return None


def create_enhanced_tool_confirmation_dialog(console: Console) -> ToolConfirmationDialog:
    """
    Create an enhanced tool confirmation dialog.
    
    Args:
        console: Rich console instance
        
    Returns:
        Configured ToolConfirmationDialog instance
    """
    return ToolConfirmationDialog(console)