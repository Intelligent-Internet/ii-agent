"""MCP server observations for ii-agent."""
from __future__ import annotations

from typing import Any

from ii_agent.core.schema import ObservationType
from ii_agent.events.observation.observation import Observation

class MCPObservation(Observation):
    """This data class represents the result of a MCP Server operation."""

    observation: str = ObservationType.MCP
    name: str = ""  # The name of the MCP tool that was called
    arguments: dict[str, Any] = {}  # The arguments passed to the MCP tool

    @property
    def message(self) -> str:
        return self.content
    
    def __str__(self) -> str:
        header = f"[🔌 MCP: {self.name}]"
        args_info = f" with args: {self.arguments}" if self.arguments else ""
        
        if self.content:
            return f"{header}{args_info}\n{self.content}"
        else:
            return f"{header}{args_info}"