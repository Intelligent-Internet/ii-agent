"""MCP server actions for ii-agent."""

from __future__ import annotations

from typing import Any, ClassVar, Optional
from pydantic import Field

from ii_agent.core.schema import ActionType, SecurityRisk
from ii_agent.events.action.action import Action


class MCPAction(Action):
    """Action to interact with MCP (Model Context Protocol) servers."""
    
    name: str = ""
    arguments: dict[str, Any] = Field(default_factory=dict)
    thought: str = ""
    action: str = ActionType.MCP
    runnable: ClassVar[bool] = True
    security_risk: Optional[SecurityRisk] = None

    @property
    def message(self) -> str:
        return (
            f"I am interacting with the MCP server with name:\n"
            f"```\n{self.name}\n```\n"
            f"and arguments:\n"
            f"```\n{self.arguments}\n```"
        )

    def __str__(self) -> str:
        ret = "**MCPAction**\n"
        if self.thought:
            ret += f"THOUGHT: {self.thought}\n"
        ret += f"NAME: {self.name}\n"
        ret += f"ARGUMENTS: {self.arguments}"
        return ret