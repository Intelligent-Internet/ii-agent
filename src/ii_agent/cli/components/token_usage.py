"""
Token usage visualization component.

This module provides components for displaying token usage and warnings.
"""

from typing import Optional
from rich.console import Console
from rich.text import Text
from rich.panel import Panel


class TokenUsageDisplay:
    """Component for displaying token usage information."""
    
    WARNING_THRESHOLD = 100000  # Token threshold for warnings
    
    def __init__(self, console: Console):
        self.console = console
    
    def display_usage(self, 
                     token_count: int, 
                     cached_tokens: Optional[int] = None,
                     show_warning: bool = True) -> None:
        """Display token usage information."""
        
        # Calculate cache percentage if available
        cache_percentage = 0
        if cached_tokens and token_count > 0:
            cache_percentage = round((cached_tokens / token_count) * 100, 1)
        
        # Build display text
        text = Text()
        text.append(f"{token_count:,} tokens", style="white")
        
        if cached_tokens:
            text.append(f" ({cache_percentage}% cached)", style="dim")
        
        # Show warning if threshold exceeded
        if show_warning and token_count > self.WARNING_THRESHOLD:
            self._show_warning(token_count)
        else:
            self.console.print(text)
    
    def _show_warning(self, token_count: int) -> None:
        """Show token usage warning."""
        warning_text = (
            f"⚠️ High token usage: {token_count:,} tokens\n"
            f"Consider using /compact to reduce context size"
        )
        
        warning_panel = Panel(
            warning_text,
            title="Token Usage Warning",
            style="yellow"
        )
        
        self.console.print(warning_panel)
    
    def get_usage_text(self, 
                      token_count: int, 
                      cached_tokens: Optional[int] = None) -> Text:
        """Get token usage text without displaying it."""
        text = Text()
        
        # Add token count
        if token_count > self.WARNING_THRESHOLD:
            text.append(f"{token_count:,} tokens", style="yellow")
        else:
            text.append(f"{token_count:,} tokens", style="dim")
        
        # Add cache percentage if available
        if cached_tokens and token_count > 0:
            cache_percentage = round((cached_tokens / token_count) * 100, 1)
            text.append(f" ({cache_percentage}% cached)", style="dim")
        
        return text