"""Base observation class for ii-agent events."""

from __future__ import annotations

from typing import Any, Dict, Optional
from pydantic import model_validator

from ii_agent.events.event import Event, EventSource


class Observation(Event):
    """Base class for all observations from the environment."""
    content: str = ""
    cause: Optional[int] = None  # ID of the action that caused this observation
    tool_call_metadata: Optional[Dict[str, Any]] = None
    
    @model_validator(mode='after')
    def ensure_observation_defaults(self) -> 'Observation':
        """Post-initialization to ensure consistent state."""
        # Call parent validator first
        super().ensure_defaults()
        
        # Observations are always from environment by default
        if self.source is None:
            self.source = EventSource.ENVIRONMENT.value
            
        return self