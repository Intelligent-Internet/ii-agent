"""
Arrow key navigation selector for CLI interactions.

This module provides a reusable component for selecting options using arrow keys
instead of typing numbers, improving the user experience for CLI tools.
"""

import sys
from typing import List, Optional, Tuple
from rich.console import Console
from rich.text import Text

try:
    from prompt_toolkit.keys import Keys
    from prompt_toolkit.input import create_input
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.application import Application
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.layout.containers import VSplit, HSplit, Window
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.formatted_text import HTML
    from prompt_toolkit.shortcuts import prompt
    HAS_PROMPT_TOOLKIT = True
except ImportError:
    HAS_PROMPT_TOOLKIT = False


class ArrowSelector:
    """Arrow key navigation selector for CLI options."""
    
    def __init__(
        self,
        options: List[str],
        console: Console,
        title: str = "Select an option:",
        selected_index: int = 0,
        show_numbers: bool = True,
        colors: Optional[dict] = None
    ):
        """
        Initialize the arrow selector.
        
        Args:
            options: List of option strings to display
            console: Rich console instance for output
            title: Title to display above options
            selected_index: Initially selected option index
            show_numbers: Whether to show numbers alongside options
            colors: Dictionary of color styles for different states
        """
        self.options = options
        self.console = console
        self.title = title
        self.selected_index = max(0, min(selected_index, len(options) - 1))
        self.show_numbers = show_numbers
        
        # Default color scheme
        self.colors = colors or {
            'title': 'bold white',
            'selected': 'bold green on black',
            'normal': 'white',
            'cursor': 'bold yellow',
            'instruction': 'dim white'
        }
    
    def _get_terminal_size(self) -> Tuple[int, int]:
        """Get terminal size (width, height)."""
        try:
            import shutil
            return shutil.get_terminal_size()
        except:
            return (80, 24)  # Fallback
    
    def _prompt_toolkit_select(self) -> Optional[int]:
        """Use prompt_toolkit for enhanced arrow key selection."""
        if not HAS_PROMPT_TOOLKIT:
            return self._fallback_select()
        
        try:
            from prompt_toolkit.shortcuts import radiolist_dialog
            from prompt_toolkit.formatted_text import HTML
            
            # Convert options to radiolist format
            radio_options = []
            for i, option in enumerate(self.options):
                radio_options.append((i, option))
            
            # Show the dialog
            result = radiolist_dialog(
                title=HTML(f'<b>🔒 Tool Confirmation Required</b>'),
                text=HTML('<i>Use arrow keys to navigate, Enter to select, Esc to cancel</i>'),
                values=radio_options,
                default=self.selected_index
            ).run()
            
            return result
            
        except Exception as e:
            # If radiolist_dialog fails, try a simpler approach
            return self._simple_select()
    
    def _simple_select(self) -> Optional[int]:
        """Simple selection with in-place updates to avoid screen corruption."""
        try:
            import sys
            import tty
            import termios
            
            # Display initial state
            print()  # Add some space
            if self.title:
                print(self.title)
                print()
            
            # Show options with initial selection
            lines_printed = 0
            for i, option in enumerate(self.options):
                if i == self.selected_index:
                    print(f"\033[32m▶ {i + 1}. {option}\033[0m")
                else:
                    print(f"  {i + 1}. {option}")
                lines_printed += 1
            
            print("\nUse ↑↓ arrows, Enter to select, numbers for shortcuts")
            lines_printed += 2
            
            # Set up terminal for raw input
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            
            try:
                tty.setraw(fd)
                
                while True:
                    key = sys.stdin.read(1)
                    
                    if key == '\r' or key == '\n':  # Enter
                        # Move cursor past our display
                        print(f"\033[{lines_printed}B", end="")
                        return self.selected_index
                        
                    elif key == '\x1b':  # Escape sequence
                        next_chars = sys.stdin.read(2)
                        if next_chars == '[A':  # Up arrow
                            self.selected_index = (self.selected_index - 1) % len(self.options)
                            # Update display in place
                            self._update_display_in_place(lines_printed - 2)
                        elif next_chars == '[B':  # Down arrow
                            self.selected_index = (self.selected_index + 1) % len(self.options)
                            # Update display in place
                            self._update_display_in_place(lines_printed - 2)
                        else:  # ESC or other
                            print(f"\033[{lines_printed}B", end="")
                            return None
                            
                    elif key == '\x03':  # Ctrl+C
                        print(f"\033[{lines_printed}B", end="")
                        return None
                        
                    elif key.isdigit():  # Number shortcuts
                        num = int(key) - 1
                        if 0 <= num < len(self.options):
                            print(f"\033[{lines_printed}B", end="")
                            return num
                            
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                
        except Exception:
            return self._fallback_select()
    
    def _update_display_in_place(self, option_lines):
        """Update the options display without clearing the screen."""
        import sys
        
        # Move cursor up to the start of options
        sys.stdout.write(f"\033[{option_lines}A")
        
        # Redraw options
        for i, option in enumerate(self.options):
            sys.stdout.write("\033[2K")  # Clear current line
            if i == self.selected_index:
                sys.stdout.write(f"\033[32m▶ {i + 1}. {option}\033[0m\n")
            else:
                sys.stdout.write(f"  {i + 1}. {option}\n")
        
        sys.stdout.flush()
    
    def select(self) -> Optional[int]:
        """
        Start the selection process.
        
        Returns:
            Selected option index (0-based), or None if cancelled
        """
        # Try prompt_toolkit radiolist first (best experience)
        if HAS_PROMPT_TOOLKIT:
            try:
                result = self._prompt_toolkit_select()
                if result is not None:
                    return result
            except Exception as e:
                # If prompt_toolkit fails, show a message and fall back
                print(f"[Arrow navigation unavailable: {e}]")
        
        # Fallback to clean numbered input
        return self._fallback_select()
    
    def _fallback_select(self) -> Optional[int]:
        """
        Fallback to numbered input selection.
        
        Returns:
            Selected option index (0-based), or None if cancelled
        """
        self.console.clear()
        
        # Display title
        if self.title:
            self.console.print(f"[{self.colors['title']}]{self.title}[/]")
            self.console.print()
        
        # Display options with numbers
        for i, option in enumerate(self.options):
            color = self.colors['selected'] if i == self.selected_index else self.colors['normal']
            self.console.print(f"[{color}]{i + 1}. {option}[/]")
        
        self.console.print()
        
        self.console.print("[dim]Press 1-4 for quick selection:[/dim]")
        
        while True:
            try:
                response = input().strip()
                
                if not response:
                    continue
                
                try:
                    choice_num = int(response)
                    if 1 <= choice_num <= len(self.options):
                        return choice_num - 1
                    else:
                        self.console.print(f"[red]Please enter a number between 1 and {len(self.options)}[/red]")
                except ValueError:
                    self.console.print("[red]Please enter a valid number[/red]")
            
            except (KeyboardInterrupt, EOFError):
                return None


def create_tool_confirmation_selector(
    console: Console,
    tool_name: str,
    reason: str,
    tool_input: dict
) -> ArrowSelector:
    """
    Create a specialized arrow selector for tool confirmation.
    
    Args:
        console: Rich console instance
        tool_name: Name of the tool requiring confirmation
        reason: Reason for tool execution
        tool_input: Tool input parameters
    
    Returns:
        Configured ArrowSelector instance
    """
    options = [
        "Yes",
        "Yes, and don't ask again for this tool this session",
        "Yes, approve for all tools in this session",
        "No, and tell ii-agent what to do differently"
    ]
    
    # Create a detailed title
    title = f"🔒 Tool Confirmation Required\nTool: {tool_name}\nReason: {reason}"
    
    colors = {
        'title': 'bold yellow',
        'selected': 'bold white on blue',
        'normal': 'white',
        'cursor': 'bold cyan',
        'instruction': 'dim cyan'
    }
    
    return ArrowSelector(
        options=options,
        console=console,
        title=title,
        selected_index=0,
        show_numbers=True,
        colors=colors
    )