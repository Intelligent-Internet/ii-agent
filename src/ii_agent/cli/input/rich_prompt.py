"""
Enhanced prompt handling with Rich and prompt_toolkit integration.

This module provides a rich interactive prompt system with command completion,
syntax highlighting, and improved user experience.
"""

from typing import Optional, List, Dict
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion, merge_completers
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style
from prompt_toolkit.key_binding import KeyBindings

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ii_agent.cli.components.file_path_completer import MentionCompleter


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
    
    def __init__(self, workspace_path: str, console: Console, command_handler=None):
        self.workspace_path = workspace_path
        self.console = console
        self.history: List[str] = []
        self.history_index = 0
        self.command_handler = command_handler
        
        # Get commands from command handler or use defaults
        self.commands = self._get_commands()
        
        # Create completers
        self.slash_completer = SlashCommandCompleter(self.commands)
        self.mention_completer = MentionCompleter(workspace_path, self.commands)
        
        # Merge completers
        self.completer = merge_completers([self.slash_completer, self.mention_completer])
        
        # Setup prompt session with enhanced styling
        self.style = Style.from_dict({
            'prompt': '#FFD700 bold',
            'input': '#FFFFFF',
            'completion-menu.completion': 'bg:#008888 #ffffff',
            'completion-menu.completion.current': 'bg:#00aaaa #000000',
            'completion-menu.meta.completion': 'bg:#999999 #000000',
            'completion-menu.meta.completion.current': 'bg:#aaaaaa #000000',
            'paste-indicator': '#FFA500 bold',
            'multiline-hint': '#87CEEB',
            'file-completion': 'bg:#4a4a4a fg:#ffffff',
        })
        
        # Create key bindings for enhanced functionality
        bindings = KeyBindings()
        
        @bindings.add('c-m')  # Ctrl+M (Enter)
        def _(event):
            """Handle regular enter."""
            event.app.exit(result=event.app.current_buffer.text)
        
        @bindings.add('escape', 'enter')  # Alt+Enter
        def _(event):
            """Handle alt+enter for multiline."""
            event.app.exit(result=event.app.current_buffer.text + '\n')
        
        self.session = PromptSession(
            style=self.style,
            completer=self.completer,
            complete_while_typing=True,
            vi_mode=False,  # Can be made configurable
            key_bindings=bindings,
        )
        
        # Setup history file
        self.history_file = Path(workspace_path) / ".ii-agent-history" / "prompt_history.txt"
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Load history
        self._load_history()
    
    def _get_commands(self) -> Dict[str, str]:
        """Get available commands from command handler or use defaults."""
        if self.command_handler:
            return self.command_handler.get_command_descriptions()
        else:
            # Fallback to hardcoded commands
            return {
                '/help': 'Show available commands and usage information',
                '/exit': 'Exit the application',
                '/clear': 'Clear conversation history and free up context',
                '/compact': 'Truncate context to save memory',
                '/settings': 'Configure LLM settings and application preferences',
            }
    
    def update_commands(self, command_handler=None) -> None:
        """Update available commands dynamically."""
        if command_handler:
            self.command_handler = command_handler
        self.commands = self._get_commands()
        self.completer = SlashCommandCompleter(self.commands)
    
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
        """Get user input with enhanced prompt and paste detection."""
        try:
            user_input = await self.session.prompt_async(
                HTML(f'<prompt>{prompt_text}</prompt>'),
                multiline=False,
            )
            
            # Check for paste detection (multiple lines or large text)
            if user_input and ('\n' in user_input or len(user_input) > 200):
                return await self._handle_paste_input(user_input)
            
            if user_input.strip():
                self._add_to_history(user_input.strip())
            
            return user_input.strip()
            
        except (EOFError, KeyboardInterrupt):
            return "/exit"
    
    async def get_multiline_input(self, prompt_text: str = "👤 You: ") -> str:
        """Get multiline user input with enhanced handling."""
        try:
            # Show multiline input hint
            hint_panel = Panel(
                "💡 [dim]Multiline mode enabled[/dim]\n\n"
                "• Press Alt+Enter or Ctrl+Enter to submit\n"
                "• Use Escape to cancel\n"
                "• Type normally for multiline input",
                title="Multiline Input",
                style="blue"
            )
            self.console.print(hint_panel)
            
            user_input = await self.session.prompt_async(
                HTML(f'<prompt>{prompt_text}</prompt>'),
                multiline=True,
            )
            
            if user_input.strip():
                self._add_to_history(user_input.strip())
            
            return user_input.strip()
            
        except (EOFError, KeyboardInterrupt):
            return "/exit"
    
    async def get_confirmation(self, message: str, default: bool = True) -> bool:
        """Get confirmation from user with Rich styling."""
        try:
            # Create a styled confirmation panel
            confirmation_panel = Panel(
                message,
                title="Confirmation",
                style="yellow"
            )
            self.console.print(confirmation_panel)
            
            # Use async prompt instead of confirm
            response = await self.session.prompt_async(
                HTML(f'<prompt>Continue? ({"Y/n" if default else "y/N"}): </prompt>')
            )
            
            # Handle response
            if not response.strip():
                return default
            
            return response.strip().lower() in ['y', 'yes']
            
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
        
        # Enhanced usage tips
        tips_panel = Panel(
            "💡 [bold]Tips:[/bold]\n\n"
            "• Use Tab for command completion\n"
            "• Commands are case-sensitive\n"
            "• Type [bold]@filename[/bold] to autocomplete file paths\n"
            "• Type your message normally for conversation\n"
            "• Use Ctrl+C to interrupt or exit\n"
            "• Command history is saved between sessions\n"
            "• Paste detection for multiline input\n"
            "• Alt+Enter for multiline mode",
            title="Usage Tips",
            style="blue"
        )
        self.console.print(tips_panel)
    
    async def _handle_paste_input(self, pasted_text: str) -> str:
        """Handle pasted text input with confirmation."""
        # Count lines in pasted text
        line_count = pasted_text.count('\n') + 1
        
        # Show paste confirmation
        paste_panel = Panel(
            f"📋 [yellow]Pasted text detected![/yellow]\n\n"
            f"Lines: {line_count}\n"
            f"Characters: {len(pasted_text)}\n\n"
            f"Preview: {pasted_text[:100]}{'...' if len(pasted_text) > 100 else ''}",
            title="Paste Detection",
            style="yellow"
        )
        self.console.print(paste_panel)
        
        # Get confirmation
        if await self.get_confirmation("Use this pasted text as input?", default=True):
            self._add_to_history(pasted_text)
            return pasted_text
        else:
            return "/exit"
    
    def cleanup(self) -> None:
        """Clean up resources."""
        self._save_history()


def create_rich_prompt(workspace_path: str, console: Console, command_handler=None) -> RichPrompt:
    """Create a rich prompt instance."""
    return RichPrompt(workspace_path, console, command_handler)