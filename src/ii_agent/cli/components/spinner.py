"""
Enhanced spinner components for CLI visualization.

This module provides animated spinners with variety of messages and timing,
inspired by the reference implementation.
"""

import time
import random
from typing import Optional
from threading import Thread, Event
from rich.console import Console
from rich.text import Text
from rich.live import Live


class AnimatedSpinner:
    """Enhanced animated spinner with variety of messages and timing."""
    
    # Spinner characters - using cross-platform compatible ones
    CHARACTERS = ['·', '✢', '✳', '∗', '✻', '✽']
    
    # Variety of processing messages
    MESSAGES = [
        'Accomplishing',
        'Actioning',
        'Actualizing',
        'Calculating',
        'Cerebrating',
        'Churning',
        'Clauding',
        'Coalescing',
        'Cogitating',
        'Computing',
        'Conjuring',
        'Considering',
        'Cooking',
        'Crafting',
        'Creating',
        'Crunching',
        'Deliberating',
        'Determining',
        'Doing',
        'Effecting',
        'Finagling',
        'Forging',
        'Forming',
        'Generating',
        'Hatching',
        'Hustling',
        'Ideating',
        'Inferring',
        'Manifesting',
        'Marinating',
        'Mulling',
        'Mustering',
        'Musing',
        'Noodling',
        'Percolating',
        'Pondering',
        'Processing',
        'Puttering',
        'Reticulating',
        'Ruminating',
        'Simmering',
        'Spinning',
        'Stewing',
        'Synthesizing',
        'Thinking',
        'Transmuting',
        'Vibing',
        'Working',
    ]
    
    def __init__(self, console: Console, message: Optional[str] = None):
        self.console = console
        self.message = message or random.choice(self.MESSAGES)
        self.frames = self.CHARACTERS + list(reversed(self.CHARACTERS))
        self.frame_index = 0
        self.start_time = time.time()
        self.stop_event = Event()
        self.thread: Optional[Thread] = None
        self.live: Optional[Live] = None
        
    def _get_display_text(self) -> Text:
        """Get the current display text for the spinner."""
        elapsed = int(time.time() - self.start_time)
        
        # Create spinner character
        spinner_char = self.frames[self.frame_index]
        
        # Build display text
        text = Text()
        text.append(f"{spinner_char} ", style="cyan")
        text.append(f"{self.message}… ", style="cyan")
        text.append(f"({elapsed}s · ", style="dim")
        text.append("esc", style="bold dim")
        text.append(" to interrupt)", style="dim")
        
        return text
    
    def _animate(self) -> None:
        """Animation loop running in separate thread."""
        while not self.stop_event.is_set():
            if self.live:
                self.live.update(self._get_display_text())
            
            # Update frame
            self.frame_index = (self.frame_index + 1) % len(self.frames)
            
            # Wait for next frame (120ms like reference)
            if self.stop_event.wait(0.12):
                break
    
    def start(self) -> None:
        """Start the animated spinner."""
        if self.thread and self.thread.is_alive():
            return
        
        self.stop_event.clear()
        self.live = Live(self._get_display_text(), console=self.console, refresh_per_second=10)
        self.live.start()
        
        self.thread = Thread(target=self._animate, daemon=True)
        self.thread.start()
    
    def stop(self) -> None:
        """Stop the animated spinner."""
        self.stop_event.set()
        
        if self.thread:
            self.thread.join(timeout=0.5)
        
        if self.live:
            try:
                # Update with empty content before stopping
                from rich.text import Text
                self.live.update(Text(""))
                self.live.refresh()
                self.live.stop()
            except Exception:
                self.live.stop()
            self.live = None
    
    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()


class SimpleSpinner:
    """Simple spinner without timing or messages."""
    
    def __init__(self, console: Console):
        self.console = console
        self.frames = AnimatedSpinner.CHARACTERS + list(reversed(AnimatedSpinner.CHARACTERS))
        self.frame_index = 0
        self.stop_event = Event()
        self.thread: Optional[Thread] = None
        self.live: Optional[Live] = None
    
    def _get_display_text(self) -> Text:
        """Get the current display text for the spinner."""
        spinner_char = self.frames[self.frame_index]
        text = Text()
        text.append(spinner_char, style="cyan")
        return text
    
    def _animate(self) -> None:
        """Animation loop running in separate thread."""
        while not self.stop_event.is_set():
            if self.live:
                self.live.update(self._get_display_text())
            
            # Update frame
            self.frame_index = (self.frame_index + 1) % len(self.frames)
            
            # Wait for next frame
            if self.stop_event.wait(0.12):
                break
    
    def start(self) -> None:
        """Start the simple spinner."""
        if self.thread and self.thread.is_alive():
            return
        
        self.stop_event.clear()
        self.live = Live(self._get_display_text(), console=self.console, refresh_per_second=10)
        self.live.start()
        
        self.thread = Thread(target=self._animate, daemon=True)
        self.thread.start()
    
    def stop(self) -> None:
        """Stop the simple spinner."""
        self.stop_event.set()
        
        if self.thread:
            self.thread.join(timeout=0.5)
        
        if self.live:
            try:
                # Update with empty content before stopping
                from rich.text import Text
                self.live.update(Text(""))
                self.live.refresh()
                self.live.stop()
            except Exception:
                self.live.stop()
            self.live = None
    
    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()