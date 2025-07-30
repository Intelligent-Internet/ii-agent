"""
Session selector component for --resume functionality.

This module provides a UI for selecting from available chat sessions
to resume from, using the existing ArrowSelector component.
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from rich.console import Console
from rich.text import Text

try:
    from prompt_toolkit.shortcuts import radiolist_dialog
    from prompt_toolkit.formatted_text import HTML
    HAS_PROMPT_TOOLKIT = True
except ImportError:
    HAS_PROMPT_TOOLKIT = False


class SessionSelector:
    """Session selector UI for choosing which session to resume."""
    
    def __init__(self, console: Console):
        """Initialize the session selector.
        
        Args:
            console: Rich console instance for output
        """
        self.console = console
    
    def format_session_option(self, session: Dict[str, Any]) -> str:
        """Format a session for display in the selector.
        
        Args:
            session: Session info dictionary
            
        Returns:
            Formatted string for display
        """
        # Format timestamp
        timestamp_str = session.get("timestamp", "")
        try:
            if timestamp_str:
                timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                formatted_time = timestamp.strftime("%Y-%m-%d %H:%M")
            else:
                formatted_time = "Unknown date"
        except:
            formatted_time = "Unknown date"
        
        # Get session info
        session_name = session.get("session_name") or "Unnamed session"
        workspace = session.get("workspace_path", "").replace(str(session.get("workspace_path", "")).split("/")[-1], ".../" + str(session.get("workspace_path", "")).split("/")[-1]) if len(str(session.get("workspace_path", ""))) > 40 else session.get("workspace_path", "")
        message_count = session.get("message_count", 0)
        
        # Format the display string
        return f"{formatted_time} | {session_name} | {workspace} | {message_count} messages"
    
    def select_session(self, sessions: List[Dict[str, Any]]) -> Optional[str]:
        """Show session selector and return selected session ID.
        
        Args:
            sessions: List of available sessions
            
        Returns:
            Selected session ID or None if cancelled/new session
        """
        if not sessions:
            self.console.print("[yellow]No previous sessions found. Starting new session.[/yellow]")
            return None
        
        # Use prompt_toolkit if available for better UI
        if HAS_PROMPT_TOOLKIT:
            try:
                return self._prompt_toolkit_select(sessions)
            except Exception as e:
                self.console.print(f"[yellow]Arrow navigation failed: {e}. Using numbered selection.[/yellow]")
        
        # Fallback to numbered selection
        return self._numbered_select(sessions)
    
    def _prompt_toolkit_select(self, sessions: List[Dict[str, Any]]) -> Optional[str]:
        """Use prompt_toolkit for selection with arrow keys."""
        # Create radiolist options
        radio_options = []
        for i, session in enumerate(sessions):
            label = self.format_session_option(session)
            radio_options.append((session["session_id"], label))
        
        # Add new session option
        radio_options.append((None, "Start new session"))
        
        # Show dialog
        result = radiolist_dialog(
            title=HTML('<b>Select a session to resume:</b>'),
            text=HTML('<i>Use arrow keys to navigate, Enter to select, Esc to cancel</i>'),
            values=radio_options,
            default=sessions[0]["session_id"] if sessions else None
        ).run()
        
        return result
    
    def _numbered_select(self, sessions: List[Dict[str, Any]]) -> Optional[str]:
        """Fallback to simple numbered selection."""
        self.console.print("\n[bold cyan]Select a session to resume:[/bold cyan]\n")
        
        # Display options
        for i, session in enumerate(sessions):
            option_text = self.format_session_option(session)
            self.console.print(f"  {i + 1}. {option_text}")
        
        self.console.print(f"  {len(sessions) + 1}. [green]Start new session[/green]")
        self.console.print()
        
        # Get user choice
        while True:
            try:
                choice = input("Enter your choice (number): ").strip()
                if not choice:
                    continue
                
                choice_num = int(choice)
                if choice_num == len(sessions) + 1:
                    return None  # New session
                elif 1 <= choice_num <= len(sessions):
                    return sessions[choice_num - 1]["session_id"]
                else:
                    self.console.print(f"[red]Please enter a number between 1 and {len(sessions) + 1}[/red]")
            except ValueError:
                self.console.print("[red]Please enter a valid number[/red]")
            except (KeyboardInterrupt, EOFError):
                self.console.print("\n[yellow]Session selection cancelled. Starting new session.[/yellow]")
                return None
    
    def display_session_info(self, session: Dict[str, Any]) -> None:
        """Display information about a selected session.
        
        Args:
            session: Session info dictionary
        """
        timestamp_str = session.get("timestamp", "")
        try:
            if timestamp_str:
                timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                formatted_time = timestamp.strftime("%Y-%m-%d %H:%M:%S")
            else:
                formatted_time = "Unknown"
        except:
            formatted_time = "Unknown"
        
        session_name = session.get("session_name") or "Unnamed session"
        workspace = session.get("workspace_path", "Unknown")
        message_count = session.get("message_count", 0)
        
        self.console.print()
        self.console.print("[bold green]Resuming session:[/bold green]")
        self.console.print(f"  [cyan]Name:[/cyan] {session_name}")
        self.console.print(f"  [cyan]Date:[/cyan] {formatted_time}")
        self.console.print(f"  [cyan]Workspace:[/cyan] {workspace}")
        self.console.print(f"  [cyan]Messages:[/cyan] {message_count}")
        self.console.print()