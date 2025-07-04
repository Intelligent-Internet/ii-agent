"""Error observations for ii-agent."""
from __future__ import annotations
from ii_agent.core.schema import ObservationType
from ii_agent.events.observation.observation import Observation

class ErrorObservation(Observation):
    """Observation representing an error that occurred during execution."""
    
    error_id: str = ""
    observation: str = ObservationType.ERROR
    
    @property
    def message(self) -> str:
        return self.content
    
    def __str__(self) -> str:
        return f"[ERROR]: {self.content}"

class SystemObservation(Observation):
    """Observation from the system (e.g., interruptions, status changes)."""
    
    event_type: str = ""
    observation: str = ObservationType.NULL
    
    @property
    def message(self) -> str:
        return f"System event: {self.event_type}"
    
    def __str__(self) -> str:
        return f"[SYSTEM {self.event_type}]: {self.content}"