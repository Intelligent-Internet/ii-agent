from abc import ABC, abstractmethod
from typing import Any
from ii_agent.controller.state import State
from ii_agent.llm.base import AssistantContentBlock
from ii_agent.llm.base import LLMClient
from ii_agent.core.config.agent_config import AgentConfig
from ii_agent.llm.base import ToolParam


class Agent(ABC):
    name: str
    description: str
    input_schema: dict[str, Any]

    def __init__(
        self, llm: LLMClient, config: AgentConfig, tools: list[ToolParam] | None = None
    ):
        self.llm = llm
        self.config = config
        self._complete = False
        if tools is None:
            self._tools = []
        else:
            self._tools = tools

    @abstractmethod
    def step(self, state: State) -> list[AssistantContentBlock]:
        pass

    @property
    def tools(self) -> list[ToolParam]:
        return self._tools

    @classmethod
    def get_agent(cls, agent_name: str) -> "Agent":
        raise NotImplementedError

    def get_agent_param(self) -> ToolParam:
        return ToolParam(
            name=self.name,
            description=self.description,
            input_schema=self.input_schema,
            type="agent",
        )
