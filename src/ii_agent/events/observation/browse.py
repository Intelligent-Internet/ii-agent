"""Browser interaction observations for ii-agent."""
from __future__ import annotations

from typing import Optional

from ii_agent.core.schema import ObservationType
from ii_agent.events.observation.observation import Observation

class BrowseObservation(Observation):
    """Observation from browser actions (page load, interaction, etc)."""
    
    url: str = ""
    status_code: Optional[int] = None
    success: bool = True
    error_message: Optional[str] = None
    axtree: Optional[str] = None  # Accessibility tree representation
    observation: str = ObservationType.BROWSE
    
    @property
    def message(self) -> str:
        if self.success:
            return f"Browser action completed for: {self.url}"
        else:
            return f"Browser action failed for: {self.url} - {self.error_message}"
    
    def __str__(self) -> str:
        status_info = f" (HTTP {self.status_code})" if self.status_code else ""
        header = f"[🌐 Browser: {self.url}{status_info}]"
        
        if not self.success and self.error_message:
            return f"{header}\nError: {self.error_message}"
        
        if self.content:
            return f"{header}\n{self.content}"
        else:
            return header

class BrowseInteractiveObservation(Observation):
    """Observation from interactive browser actions (click, type, scroll, etc)."""
    
    browser_actions: str = ""
    success: bool = True
    error_message: Optional[str] = None
    observation: str = ObservationType.BROWSE
    
    @property
    def message(self) -> str:
        if self.success:
            return f"Browser interaction completed: {self.browser_actions[:50]}..."
        else:
            return f"Browser interaction failed: {self.error_message}"
    
    def __str__(self) -> str:
        header = "[🌐 Browser Interaction]"
        
        if not self.success and self.error_message:
            return f"{header}\nActions: {self.browser_actions}\nError: {self.error_message}"
        
        result = f"{header}\nActions: {self.browser_actions}\n"
        if self.content:
            result += f"Result:\n{self.content}"
        
        return result.rstrip()