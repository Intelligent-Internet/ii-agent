"""Base Action class for ii-agent events."""

from __future__ import annotations

from typing import ClassVar, Optional
from pydantic import model_validator

from ii_agent.core.schema import ConfirmationStatus, SecurityRisk
from ii_agent.events.event import Event, EventSource


class Action(Event):
    """Base class for all actions that can be performed by agents."""
    
    runnable: ClassVar[bool] = False  # Whether this action type can be executed
    confirmation_state: ConfirmationStatus = ConfirmationStatus.CONFIRMED
    security_risk: Optional[SecurityRisk] = None
    thought: str = ""  # Agent's reasoning for this action
    
    @model_validator(mode='after')
    def ensure_action_defaults(self) -> 'Action':
        """Post-initialization to ensure consistent state."""
        # Call parent validator first
        super().ensure_defaults()
        
        # Actions are always from agents by default
        if self.source is None:
            self.source = EventSource.AGENT.value
            
        return self

    @property
    def message(self) -> str:
        """Get a human-readable message describing this action."""
        return f"Action: {self.__class__.__name__}"