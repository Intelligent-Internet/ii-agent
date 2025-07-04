"""Empty/null observations for ii-agent."""
from __future__ import annotations
from ii_agent.core.schema import ObservationType
from ii_agent.events.observation.observation import Observation

class NullObservation(Observation):
    """A null observation that represents no meaningful result."""
    
    observation: str = ObservationType.NULL
    
    @property
    def message(self) -> str:
        return "No result"
    
    def __str__(self) -> str:
        return "[No output]"