"""Message-related action classes."""

from __future__ import annotations

from typing import Any, ClassVar, Optional
from pydantic import Field

from ii_agent.core.schema import ActionType, SecurityRisk
from ii_agent.events.action.action import Action


class MessageAction(Action):
    """Action representing a message from the agent."""
    
    content: str = ""
    file_urls: Optional[list[str]] = None
    image_urls: Optional[list[str]] = None
    wait_for_response: bool = False
    action: str = ActionType.MESSAGE
    runnable: ClassVar[bool] = False 
    resume: bool = False

    @property
    def message(self) -> str:
        return self.content

    def __str__(self) -> str:
        ret = f"**MessageAction** (source={self.source})\n"
        ret += f"CONTENT: {self.content}"
        if self.image_urls:
            for url in self.image_urls:
                ret += f"\nIMAGE_URL: {url}"
        if self.file_urls:
            for url in self.file_urls:
                ret += f"\nFILE_URL: {url}"
        return ret


class SystemMessageAction(Action):
    """
    Action that represents a system message for an agent, including the system prompt
    and available tools. This should be the first message in the event stream.
    """

    content: str = ""
    tools: Optional[list[Any]] = None
    agent_version: Optional[str] = None
    agent_class: Optional[str] = None
    action: str = ActionType.SYSTEM
    runnable: ClassVar[bool] = False

    @property
    def message(self) -> str:
        return self.content

    def __str__(self) -> str:
        ret = f"**SystemMessageAction** (source={self.source})\n"
        ret += f"CONTENT: {self.content}"
        if self.tools:
            ret += f"\nTOOLS: {len(self.tools)} tools available"
        if self.agent_class:
            ret += f"\nAGENT_CLASS: {self.agent_class}"
        return ret