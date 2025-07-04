"""Agent-specific observations for ii-agent."""
from __future__ import annotations

from typing import Any, Dict, Optional

from ii_agent.core.schema import ObservationType, AgentState
from ii_agent.events.observation.observation import Observation

class AgentStateChangedObservation(Observation):
    """Observation when agent state changes."""
    
    agent_state: AgentState = AgentState.RUNNING
    observation: str = ObservationType.STATE_CHANGED
    
    @property
    def message(self) -> str:
        return f"Agent state changed to: {self.agent_state.value}"
    
    def __str__(self) -> str:
        return f"[🤖 Agent State: {self.agent_state.value}]"

class AgentThinkObservation(Observation):
    """Observation from agent thinking/reasoning process."""
    
    thought: str = ""
    observation: str = ObservationType.THINK
    
    @property
    def message(self) -> str:
        return f"Agent thinking: {self.thought[:50]}{'...' if len(self.thought) > 50 else ''}"
    
    def __str__(self) -> str:
        return f"[🤔 Agent Think]\n{self.thought}"