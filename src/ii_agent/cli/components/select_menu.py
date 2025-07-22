"""
Terminal select menu with arrow key navigation.

This module provides a reliable arrow key selection interface inspired by 
the working implementation in anon-kode-main but adapted for Python.
"""

import sys
import os
from typing import List, Optional, Callable
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.columns import Columns


class SelectMenu:
    """Arrow key navigable select menu for terminal applications."""
    
    def __init__(
        self,
        options: List[str],
        title: str = "Select an option:",
        console: Optional[Console] = None,
        show_numbers: bool = True
    ):
        """
        Initialize the select menu.
        
        Args:
            options: List of option strings
            title: Title to display above options
            console: Rich console instance (creates new if None)
            show_numbers: Whether to show numbers beside options
        """
        self.options = options
        self.title = title
        self.console = console or Console()
        self.show_numbers = show_numbers
        self.selected_index = 0
        self._last_render_lines = 0
        
    def _clear_previous_render(self) -> None:
        """Clear the previous rendering from terminal."""
        if self._last_render_lines > 0:
            # Move cursor up to start of our content
            sys.stdout.write(f'\033[{self._last_render_lines}A')
            # Clear from cursor to end of screen
            sys.stdout.write('\033[0J')
            sys.stdout.flush()
            
    def _render_menu(self) -> None:
        """Render the current menu state with simple, reliable output."""
        line_count = 0
        
        # Title with simple formatting
        if self.title:
            # Create a simple bordered title
            title_line = f"╭─ {self.title} ─╮"
            print(f"\033[96m{title_line}\033[0m")  # Cyan color
            line_count += 1
        
        # Add a blank line after title
        print()
        line_count += 1
        
        # Options with simple formatting
        for i, option in enumerate(self.options):
            if i == self.selected_index:
                # Selected option with blue background
                if self.show_numbers:
                    text = f"▶ {i + 1}. {option}"
                else:
                    text = f"▶ {option}"
                print(f"\033[44m\033[97m{text}\033[0m")  # Blue background, white text
            else:
                # Normal option
                if self.show_numbers:
                    text = f"  {i + 1}. {option}"
                else:
                    text = f"  {option}"
                print(f"\033[37m{text}\033[0m")  # White text
            line_count += 1
        
        # Instructions
        print()
        print(f"\033[90m↑↓ Navigate • Enter Select • Esc Cancel • 1-9 Shortcuts\033[0m")  # Dark gray
        line_count += 2
        
        self._last_render_lines = line_count
        
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
                
    def select(self) -> Optional[int]:
        """
        Show menu and get user selection.
        
        Returns:
            Selected option index (0-based) or None if cancelled
        """
        try:
            # Hide cursor
            sys.stdout.write('\033[?25l')
            sys.stdout.flush()
            
            # Initial render
            self._render_menu()
            
            while True:
                key = self._get_key()
                
                if key is None:
                    continue
                    
                # Handle key presses
                if key == 'up':
                    self.selected_index = (self.selected_index - 1) % len(self.options)
                    self._clear_previous_render()
                    self._render_menu()
                    
                elif key == 'down':
                    self.selected_index = (self.selected_index + 1) % len(self.options)
                    self._clear_previous_render()
                    self._render_menu()
                    
                elif key == 'enter':
                    # Clear the menu
                    self._clear_previous_render()
                    # Show final selection with ANSI colors
                    print(f"\033[92m✓ Selected: {self.options[self.selected_index]}\033[0m")
                    return self.selected_index
                    
                elif key in ('escape', 'ctrl_c'):
                    # Clear the menu
                    self._clear_previous_render()
                    print(f"\033[93mSelection cancelled\033[0m")
                    return None
                    
                elif key.isdigit():
                    # Number shortcut
                    num = int(key) - 1
                    if 0 <= num < len(self.options):
                        self.selected_index = num
                        # Clear the menu
                        self._clear_previous_render()
                        # Show final selection
                        print(f"\033[92m✓ Selected: {self.options[self.selected_index]}\033[0m")
                        return self.selected_index
                        
        except KeyboardInterrupt:
            # Clear the menu
            self._clear_previous_render()
            print(f"\033[93mSelection cancelled\033[0m")
            return None
            
        finally:
            # Show cursor
            sys.stdout.write('\033[?25h')
            sys.stdout.flush()


def create_tool_confirmation_menu(console: Console) -> SelectMenu:
    """
    Create a select menu for tool confirmation.
    
    Args:
        console: Rich console instance
        
    Returns:
        Configured SelectMenu instance
    """
    options = [
        "Yes",
        "Yes, and don't ask again for this tool this session",
        "Yes, approve for all tools in this session",
        "No, and tell ii-agent what to do differently"
    ]
    
    return SelectMenu(
        options=options,
        title="🔒 Do you want to execute this tool?",
        console=console,
        show_numbers=True
    )