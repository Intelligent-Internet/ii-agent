"""
Interactive prompt handling for CLI.

This module provides utilities for handling user input in interactive mode.
"""

import sys
from typing import Optional, List, Callable


class InteractivePrompt:
    """Interactive prompt handler with history and tab completion."""
    
    def __init__(self, prompt_text: str = ">>> ", history_file: Optional[str] = None):
        self.prompt_text = prompt_text
        self.history_file = history_file
        self.history: List[str] = []
        self.history_index = 0
        
        # Try to import readline for better input handling
        try:
            import readline
            self.readline = readline
            self._setup_readline()
        except ImportError:
            self.readline = None
    
    def _setup_readline(self):
        """Set up readline for better input handling."""
        if not self.readline:
            return
        
        # Load history
        if self.history_file:
            try:
                self.readline.read_history_file(self.history_file)
            except FileNotFoundError:
                pass
        
        # Set up tab completion
        self.readline.set_completer(self._complete)
        self.readline.parse_and_bind("tab: complete")
        
        # Set up history
        self.readline.set_history_length(1000)
    
    def _complete(self, text: str, state: int) -> Optional[str]:
        """Tab completion handler."""
        # Basic completion for common commands
        commands = [
            'exit', 'quit', 'help', 'clear', 'history',
            'run', 'execute', 'analyze', 'create', 'modify',
            'read', 'write', 'list', 'search', 'find'
        ]
        
        options = [cmd for cmd in commands if cmd.startswith(text)]
        
        if state < len(options):
            return options[state]
        return None
    
    def get_input(self, prompt: Optional[str] = None) -> str:
        """Get user input with prompt."""
        if prompt is None:
            prompt = self.prompt_text
        
        try:
            user_input = input(prompt).strip()
            
            # Add to history if not empty and not a duplicate
            if user_input and (not self.history or user_input != self.history[-1]):
                self.history.append(user_input)
                self.history_index = len(self.history)
                
                # Save to history file
                if self.history_file and self.readline:
                    try:
                        self.readline.write_history_file(self.history_file)
                    except Exception:
                        pass
            
            return user_input
            
        except EOFError:
            return "exit"
        except KeyboardInterrupt:
            print("\n^C")
            return ""
    
    def get_multiline_input(self, prompt: str = ">>> ", continuation_prompt: str = "... ") -> str:
        """Get multiline input from user."""
        lines = []
        
        while True:
            try:
                if not lines:
                    line = input(prompt)
                else:
                    line = input(continuation_prompt)
                
                # Check for end of input
                if line.strip() == "":
                    if lines:
                        break
                    else:
                        continue
                
                lines.append(line)
                
            except EOFError:
                break
            except KeyboardInterrupt:
                print("\n^C")
                return ""
        
        result = "\n".join(lines)
        
        # Add to history
        if result and (not self.history or result != self.history[-1]):
            self.history.append(result)
            self.history_index = len(self.history)
        
        return result
    
    def get_confirmation(self, message: str, default: bool = True) -> bool:
        """Get yes/no confirmation from user."""
        suffix = " [Y/n]" if default else " [y/N]"
        
        while True:
            try:
                response = input(message + suffix).strip().lower()
                
                if not response:
                    return default
                
                if response in ['y', 'yes']:
                    return True
                elif response in ['n', 'no']:
                    return False
                else:
                    print("Please enter 'y' or 'n'")
                    
            except (EOFError, KeyboardInterrupt):
                print("\n")
                return default
    
    def get_choice(self, message: str, choices: List[str], default: Optional[int] = None) -> int:
        """Get a choice from a list of options."""
        print(message)
        for i, choice in enumerate(choices, 1):
            marker = " (default)" if default == i else ""
            print(f"  {i}. {choice}{marker}")
        
        while True:
            try:
                prompt = "Enter choice"
                if default is not None:
                    prompt += f" (default: {default})"
                prompt += ": "
                
                response = input(prompt).strip()
                
                if not response and default is not None:
                    return default
                
                try:
                    choice_num = int(response)
                    if 1 <= choice_num <= len(choices):
                        return choice_num
                    else:
                        print(f"Please enter a number between 1 and {len(choices)}")
                except ValueError:
                    print("Please enter a valid number")
                    
            except (EOFError, KeyboardInterrupt):
                print("\n")
                if default is not None:
                    return default
                return 1
    
    def show_history(self) -> None:
        """Show command history."""
        if not self.history:
            print("No history available")
            return
        
        print("Command History:")
        print("-" * 20)
        for i, cmd in enumerate(self.history, 1):
            print(f"{i:3d}: {cmd}")
    
    def clear_history(self) -> None:
        """Clear command history."""
        self.history.clear()
        self.history_index = 0
        
        if self.history_file and self.readline:
            try:
                self.readline.clear_history()
                self.readline.write_history_file(self.history_file)
            except Exception:
                pass
    
    def set_completer(self, completer: Callable[[str, int], Optional[str]]) -> None:
        """Set custom tab completion function."""
        if self.readline:
            self.readline.set_completer(completer)
    
    def cleanup(self) -> None:
        """Clean up resources."""
        if self.history_file and self.readline:
            try:
                self.readline.write_history_file(self.history_file)
            except Exception:
                pass


def create_cli_prompt(workspace_path: str) -> InteractivePrompt:
    """Create a CLI prompt with appropriate configuration."""
    from pathlib import Path
    
    # Create history file in workspace
    history_dir = Path(workspace_path) / ".ii-agent-history"
    history_dir.mkdir(exist_ok=True)
    history_file = history_dir / "cli_history.txt"
    
    return InteractivePrompt(
        prompt_text="👤 You: ",
        history_file=str(history_file)
    )