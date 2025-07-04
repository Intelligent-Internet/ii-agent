"""Empty/null action for ii-agent."""

from __future__ import annotations

from typing import ClassVar

from ii_agent.core.schema import ActionType
from ii_agent.events.action.action import Action


class NullAction(Action):
    """Action that represents no action being taken."""
    
    action: str = ActionType.NULL
    runnable: ClassVar[bool] = False
    
    @property
    def message(self) -> str:
        return "No action taken"
    
    def __str__(self) -> str:
        return "**NullAction**"