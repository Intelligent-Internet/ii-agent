"""
Enhanced prompt input component.

This module provides a sophisticated prompt input similar to anon-kode-main
with mode switching, command suggestions, and better visual design.
"""

import asyncio
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
from enum import Enum

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.shortcuts import confirm
from prompt_toolkit.styles import Style
from prompt_toolkit.key_binding import KeyBindings
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.columns import Columns

from ii_agent.cli.theme import get_current_theme


class InputMode(Enum):
    """Input modes for the prompt."""
    PROMPT = "prompt"
    BASH = "bash"


class EnhancedPromptCompleter(Completer):
    """Enhanced completer with command suggestions and mode awareness."""
    
    def __init__(self, commands: Dict[str, str], mode: InputMode = InputMode.PROMPT):
        self.commands = commands
        self.mode = mode
        self.theme = get_current_theme()
    
    def get_completions(self, document: Document, complete_event):
        text = document.text_before_cursor
        
        if self.mode == InputMode.PROMPT and text.startswith('/'):
            # Command completion
            word = text[1:]  # Remove '/' prefix
            
            for command, description in self.commands.items():
                command_name = command[1:] if command.startswith('/') else command
                if command_name.startswith(word):
                    yield Completion(
                        command_name,
                        start_position=-len(word),
                        display_meta=description,
                        style=f'class:completion-suggestion'
                    )
        elif self.mode == InputMode.BASH:
            # Basic bash completion (can be enhanced)
            if ' ' not in text:
                # Command completion
                common_commands = ['ls', 'cd', 'pwd', 'cat', 'grep', 'find', 'git', 'python', 'pip']
                for cmd in common_commands:
                    if cmd.startswith(text):
                        yield Completion(
                            cmd,
                            start_position=-len(text),
                            display_meta=f"Execute {cmd}",
                            style='class:completion-bash'
                        )


class EnhancedPrompt:
    """Enhanced prompt with mode switching and better UX."""
    
    def __init__(self, workspace_path: str, console: Console, command_handler=None):
        self.workspace_path = workspace_path
        self.console = console
        self.command_handler = command_handler
        self.theme = get_current_theme()
        self.mode = InputMode.PROMPT
        self.history: List[str] = []
        self.history_index = 0
        
        # Get commands
        self.commands = self._get_commands()
        
        # Create completer
        self.completer = EnhancedPromptCompleter(self.commands, self.mode)
        
        # Enhanced styling
        self.style = Style.from_dict({
            'prompt': self.theme.claude + ' bold',
            'input': self.theme.text,
            'completion-menu.completion': f'bg:{self.theme.secondary_border} {self.theme.text}',
            'completion-menu.completion.current': f'bg:{self.theme.suggestion} {self.theme.text}',
            'completion-menu.meta.completion': f'bg:{self.theme.secondary_text} {self.theme.text}',
            'completion-menu.meta.completion.current': f'bg:{self.theme.suggestion} {self.theme.text}',
            'completion-suggestion': self.theme.suggestion,
            'completion-bash': self.theme.bash_border,
            'bash-prompt': self.theme.bash_border + ' bold',
            'mode-indicator': self.theme.secondary_text,
        })
        
        # Setup key bindings
        self.bindings = self._create_key_bindings()
        
        # Create session
        self.session = PromptSession(
            style=self.style,
            completer=self.completer,
            complete_while_typing=True,
            vi_mode=False,
            key_bindings=self.bindings,
        )
        
        # Setup history
        self.history_file = Path(workspace_path) / ".ii-agent-history" / "enhanced_history.txt"
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        self._load_history()
    
    def _create_key_bindings(self) -> KeyBindings:
        """Create enhanced key bindings."""
        bindings = KeyBindings()
        
        @bindings.add('!')
        def _(event):
            """Switch to bash mode when '!' is typed at start."""
            if event.app.current_buffer.cursor_position == 0:
                self.mode = InputMode.BASH
                self.completer.mode = InputMode.BASH
                event.app.current_buffer.insert_text('!')
        
        @bindings.add('escape')
        def _(event):
            """Switch back to prompt mode on escape."""
            if self.mode == InputMode.BASH:
                self.mode = InputMode.PROMPT
                self.completer.mode = InputMode.PROMPT
                event.app.current_buffer.reset()
        
        @bindings.add('c-c')
        def _(event):
            """Handle Ctrl+C."""
            event.app.exit(exception=KeyboardInterrupt)
        
        return bindings
    
    def _get_commands(self) -> Dict[str, str]:
        """Get available commands."""
        if self.command_handler:
            return self.command_handler.get_command_descriptions()
        else:
            return {
                '/help': 'Show available commands and usage information',
                '/exit': 'Exit the application',
                '/clear': 'Clear conversation history and free up context',
                '/compact': 'Truncate context to save memory',
                '/settings': 'Configure LLM settings and preferences',
                '/bash': 'Switch to bash mode',
            }
    
    def _load_history(self) -> None:
        """Load command history from file."""
        try:
            if self.history_file.exists():
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    self.history = [line.strip() for line in f.readlines() if line.strip()]
                    self.history_index = len(self.history)
        except Exception:
            pass
    
    def _save_history(self) -> None:
        """Save command history to file."""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                # Keep only last 1000 entries
                recent_history = self.history[-1000:] if len(self.history) > 1000 else self.history
                for entry in recent_history:
                    f.write(entry + '\\n')
        except Exception:
            pass
    
    def _add_to_history(self, command: str) -> None:
        """Add command to history."""
        if command and (not self.history or command != self.history[-1]):
            self.history.append(command)
            self.history_index = len(self.history)
            self._save_history()
    
    def _get_prompt_text(self) -> str:
        """Get the prompt text based on current mode."""
        if self.mode == InputMode.BASH:
            return f'<bash-prompt>! </bash-prompt>'
        else:
            return f'<prompt>👤 </prompt>'
    
    def _get_mode_indicator(self) -> str:
        """Get mode indicator text."""
        if self.mode == InputMode.BASH:
            return f'<mode-indicator>bash mode</mode-indicator>'
        else:
            return f'<mode-indicator>chat mode</mode-indicator>'
    
    async def get_input(self) -> Tuple[str, InputMode]:
        """Get user input with mode information."""
        try:
            # Show mode indicator
            mode_text = self._get_mode_indicator()
            
            # Get input
            prompt_text = self._get_prompt_text()
            user_input = await self.session.prompt_async(
                HTML(prompt_text),
                multiline=False,
            )
            
            # Handle mode switching
            if user_input.startswith('!') and self.mode == InputMode.PROMPT:
                self.mode = InputMode.BASH
                user_input = user_input[1:]  # Remove '!' prefix
            elif user_input == 'exit' and self.mode == InputMode.BASH:
                self.mode = InputMode.PROMPT
                return '', InputMode.PROMPT
            
            # Add to history
            if user_input.strip():
                self._add_to_history(user_input.strip())
            
            return user_input.strip(), self.mode
            
        except (EOFError, KeyboardInterrupt):
            return '/exit', InputMode.PROMPT
    
    def display_suggestions(self, suggestions: List[str]) -> None:
        """Display command suggestions."""
        if not suggestions:
            return
        
        suggestion_text = Text()
        suggestion_text.append("Suggestions:\\n", style="bold")
        
        for i, suggestion in enumerate(suggestions[:5]):  # Show max 5 suggestions
            command_info = self.commands.get(suggestion, "")
            suggestion_text.append(f"  {suggestion}", style=self.theme.suggestion)
            if command_info:
                suggestion_text.append(f" - {command_info}", style=self.theme.secondary_text)
            suggestion_text.append("\\n")
        
        suggestion_panel = Panel(
            suggestion_text,
            title="Command Suggestions",
            border_style=self.theme.suggestion,
            padding=(0, 1)
        )
        
        self.console.print(suggestion_panel)
    
    def display_mode_info(self) -> None:
        """Display information about current mode."""
        if self.mode == InputMode.BASH:
            info_text = Text()
            info_text.append("🔧 Bash Mode", style=self.theme.bash_border + " bold")
            info_text.append("\\n")
            info_text.append("• Commands are executed in shell\\n", style=self.theme.secondary_text)
            info_text.append("• Use 'exit' to return to chat mode\\n", style=self.theme.secondary_text)
            info_text.append("• Use Escape to cancel\\n", style=self.theme.secondary_text)
            
            mode_panel = Panel(
                info_text,
                title="Mode Information",
                border_style=self.theme.bash_border,
                padding=(0, 1)
            )
            
            self.console.print(mode_panel)
    
    def display_status(self, message: str, style: Optional[str] = None) -> None:
        """Display a status message."""
        if style is None:
            style = self.theme.secondary_text
        
        status_text = Text(message, style=style)
        self.console.print(status_text)
    
    def cleanup(self) -> None:
        """Clean up resources."""
        self._save_history()


def create_enhanced_prompt(workspace_path: str, console: Console, command_handler=None) -> EnhancedPrompt:
    """Create an enhanced prompt instance."""
    return EnhancedPrompt(workspace_path, console, command_handler)