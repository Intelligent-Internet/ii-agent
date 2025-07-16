"""
Enhanced prompt handling with Rich and prompt_toolkit integration.

This module provides a rich interactive prompt system with command completion,
syntax highlighting, and improved user experience.
"""

import asyncio
from typing import Optional, List, Dict, Any, Callable
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.shortcuts import confirm
from prompt_toolkit.styles import Style
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.application import Application

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table


class SlashCommandCompleter(Completer):
    """Completer for slash commands."""
    
    def __init__(self, commands: Dict[str, str]):
        self.commands = commands
    
    def get_completions(self, document: Document, complete_event):
        text = document.text_before_cursor
        
        # Only complete if the text starts with '/'
        if text.startswith('/'):
            word = text[1:]  # Remove the '/' prefix
            
            for command, description in self.commands.items():
                command_name = command[1:]  # Remove the '/' prefix from command
                if command_name.startswith(word):
                    yield Completion(
                        command_name,
                        start_position=-len(word),
                        display_meta=description,
                        style='bg:ansidarkgray fg:ansigreen'
                    )


class RichPrompt:
    """Rich interactive prompt with command completion and enhanced UX."""
    
    def __init__(self, workspace_path: str, console: Console):
        self.workspace_path = workspace_path
        self.console = console
        self.history: List[str] = []
        self.history_index = 0
        
        # Define available slash commands
        self.commands = {
            '/help': 'Show available commands and usage information',
            '/exit': 'Exit the application',
            '/clear': 'Clear conversation history and free up context',
            '/compact': 'Truncate context to save memory',
        }
        
        # Create completer
        self.completer = SlashCommandCompleter(self.commands)
        
        # Setup prompt session
        self.style = Style.from_dict({
            'prompt': '#FFD700 bold',
            'input': '#FFFFFF',
            'completion-menu.completion': 'bg:#008888 #ffffff',
            'completion-menu.completion.current': 'bg:#00aaaa #000000',
            'completion-menu.meta.completion': 'bg:#999999 #000000',
            'completion-menu.meta.completion.current': 'bg:#aaaaaa #000000',
        })
        
        self.session = PromptSession(
            style=self.style,
            completer=self.completer,
            complete_while_typing=True,
            vi_mode=False,  # Can be made configurable
        )
        
        # Setup history file
        self.history_file = Path(workspace_path) / ".ii-agent-history" / "prompt_history.txt"
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Load history
        self._load_history()
    
    def _load_history(self) -> None:
        """Load command history from file."""
        try:
            if self.history_file.exists():
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    self.history = [line.strip() for line in f.readlines() if line.strip()]
                    self.history_index = len(self.history)
        except Exception:
            # Ignore errors when loading history
            pass
    
    def _save_history(self) -> None:
        """Save command history to file."""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                # Keep only last 1000 entries
                recent_history = self.history[-1000:] if len(self.history) > 1000 else self.history
                for entry in recent_history:
                    f.write(entry + '\n')
        except Exception:
            # Ignore errors when saving history
            pass
    
    def _add_to_history(self, command: str) -> None:
        """Add command to history."""
        if command and (not self.history or command != self.history[-1]):
            self.history.append(command)
            self.history_index = len(self.history)
            self._save_history()
    
    async def get_input(self, prompt_text: str = "👤 You: ") -> str:
        """Get user input with enhanced prompt."""
        try:
            user_input = await self.session.prompt_async(
                HTML(f'<prompt>{prompt_text}</prompt>'),
                multiline=False,
            )
            
            if user_input.strip():
                self._add_to_history(user_input.strip())
            
            return user_input.strip()
            
        except (EOFError, KeyboardInterrupt):
            return "/exit"
    
    async def get_multiline_input(self, prompt_text: str = "👤 You: ") -> str:
        """Get multiline user input."""
        try:
            user_input = await self.session.prompt_async(
                HTML(f'<prompt>{prompt_text}</prompt>'),
                multiline=True,
            )
            
            if user_input.strip():
                self._add_to_history(user_input.strip())
            
            return user_input.strip()
            
        except (EOFError, KeyboardInterrupt):
            return "/exit"
    
    def get_confirmation(self, message: str, default: bool = True) -> bool:
        """Get confirmation from user with Rich styling."""
        try:
            # Create a styled confirmation panel
            confirmation_panel = Panel(
                message,
                title="Confirmation",
                style="yellow"
            )
            self.console.print(confirmation_panel)
            
            # Use prompt_toolkit's confirm function
            result = confirm(
                HTML(f'<prompt>Continue? ({"Y/n" if default else "y/N"}): </prompt>'),
                default=default
            )
            return result
            
        except (EOFError, KeyboardInterrupt):
            return False
    
    async def get_choice(self, message: str, choices: List[str], default: Optional[int] = None) -> int:
        """Get a choice from user with Rich styling."""
        try:
            # Create a styled choice panel
            choice_text = message + "\n\n"
            for i, choice in enumerate(choices, 1):
                marker = " (default)" if default == i else ""
                choice_text += f"  {i}. {choice}{marker}\n"
            
            choice_panel = Panel(
                choice_text.strip(),
                title="Choose an option",
                style="cyan"
            )
            self.console.print(choice_panel)
            
            while True:
                try:
                    prompt_text = "Enter choice"
                    if default is not None:
                        prompt_text += f" (default: {default})"
                    prompt_text += ": "
                    
                    response = await self.session.prompt_async(
                        HTML(f'<prompt>{prompt_text}</prompt>')
                    )
                    
                    if not response.strip() and default is not None:
                        return default
                    
                    choice_num = int(response.strip())
                    if 1 <= choice_num <= len(choices):
                        return choice_num
                    else:
                        self.console.print(f"[red]Please enter a number between 1 and {len(choices)}[/red]")
                        
                except ValueError:
                    self.console.print("[red]Please enter a valid number[/red]")
                except (EOFError, KeyboardInterrupt):
                    return default if default is not None else 1
                    
        except Exception:
            return default if default is not None else 1
    
    def is_slash_command(self, text: str) -> bool:
        """Check if the input is a slash command."""
        return text.strip().startswith('/')
    
    def parse_slash_command(self, text: str) -> tuple[str, str]:
        """Parse slash command and return command and arguments."""
        text = text.strip()
        if not text.startswith('/'):
            return "", text
        
        parts = text.split(None, 1)
        command = parts[0]
        args = parts[1] if len(parts) > 1 else ""
        
        return command, args
    
    def get_available_commands(self) -> Dict[str, str]:
        """Get available slash commands."""
        return self.commands.copy()
    
    def show_help(self) -> None:
        """Display help information."""
        help_table = Table(title="Available Commands", style="cyan")
        help_table.add_column("Command", style="green", no_wrap=True)
        help_table.add_column("Description", style="white")
        
        for command, description in self.commands.items():
            help_table.add_row(command, description)
        
        self.console.print(help_table)
        
        # Also show usage tips
        tips_panel = Panel(
            "💡 [bold]Tips:[/bold]\n\n"
            "• Use Tab for command completion\n"
            "• Commands are case-sensitive\n"
            "• Type your message normally for conversation\n"
            "• Use Ctrl+C to interrupt or exit\n"
            "• Command history is saved between sessions",
            title="Usage Tips",
            style="blue"
        )
        self.console.print(tips_panel)
    
    def cleanup(self) -> None:
        """Clean up resources."""
        self._save_history()


def create_rich_prompt(workspace_path: str, console: Console) -> RichPrompt:
    """Create a rich prompt instance."""
    return RichPrompt(workspace_path, console)