from abc import ABC, abstractmethod
from ii_agent.controller.state import State
from ii_agent.llm.base import AssistantContentBlock
from ii_agent.llm.base import LLMClient
from ii_agent.core.config.agent_config import AgentConfig


class Agent(ABC):
    def __init__(
        self,
        llm: LLMClient,
        config: AgentConfig,
    ):
        self.llm = llm
        self.config = config
        self._complete = False

    @abstractmethod
    def step(self, state: State) -> list[AssistantContentBlock]:
        pass