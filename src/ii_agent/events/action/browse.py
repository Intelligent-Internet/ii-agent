"""Browser interaction actions for ii-agent."""

from __future__ import annotations

from typing import ClassVar, Optional

from ii_agent.core.schema import ActionType, SecurityRisk
from ii_agent.events.action.action import Action


class BrowseURLAction(Action):
    """Opens and browses a web page at the specified URL."""
    
    url: str = ""
    thought: str = ""
    return_axtree: bool = False  # whether to return accessibility tree
    action: str = ActionType.BROWSE
    runnable: ClassVar[bool] = True
    security_risk: Optional[SecurityRisk] = SecurityRisk.LOW
    
    @property
    def message(self) -> str:
        return f"Browsing URL: {self.url}"
    
    def __str__(self) -> str:
        ret = "**BrowseURLAction**\n"
        if self.thought:
            ret += f"THOUGHT: {self.thought}\n"
        ret += f"URL: {self.url}"
        if self.return_axtree:
            ret += "\nRETURN_AXTREE: True"
        return ret


class BrowseInteractiveAction(Action):
    """Performs interactive actions on a web page (click, type, scroll, etc)."""
    
    browser_actions: str = ""  # The browser actions to perform
    thought: str = ""
    browsergym_send_msg_to_user: str = ""  # Message to send to user
    return_axtree: bool = False  # whether to return accessibility tree
    action: str = ActionType.BROWSE_INTERACTIVE
    runnable: ClassVar[bool] = True
    security_risk: Optional[SecurityRisk] = SecurityRisk.MEDIUM
    
    @property
    def message(self) -> str:
        action_preview = self.browser_actions[:100] + "..." if len(self.browser_actions) > 100 else self.browser_actions
        return f"Performing browser interactions: {action_preview}"
    
    def __str__(self) -> str:
        ret = "**BrowseInteractiveAction**\n"
        if self.thought:
            ret += f"THOUGHT: {self.thought}\n"
        ret += f"BROWSER_ACTIONS:\n{self.browser_actions}"
        if self.browsergym_send_msg_to_user:
            ret += f"\nUSER_MESSAGE: {self.browsergym_send_msg_to_user}"
        return ret