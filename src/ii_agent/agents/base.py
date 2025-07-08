from abc import ABC, abstractmethod
from ii_agent.llm.base import LLMClient
from ii_agent.core.config.agent_config import AgentConfig
from ii_agent.core.logger import logger

class BaseAgent(ABC):
    def __init__(
        self,
        llm: LLMClient,
        config: AgentConfig,
    ):
        self.llm = llm
        self.config = config
        self._complete = False


    @abstractmethod
    def step(self, state) -> Action:
        pass

    @property
    def name(self) -> str:
        return self.__class__.__name__


    def reset(self) -> None:
        """Resets the agent's execution status."""
        # Only reset the completion status, not the LLM metrics
        self._complete = False

    @property
    def complete(self) -> bool:
        """Indicates whether the current instruction execution is complete.

        Returns:
        - complete (bool): True if execution is complete; False otherwise.
        """
        return self._complete

