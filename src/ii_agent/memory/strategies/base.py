"""Base class for memory optimization strategies."""

from abc import ABC, abstractmethod

from ii_agent.agents.models.base import Model
from ii_agent.memory.schemas import MemoryData


class MemoryOptimizationStrategy(ABC):
    """Abstract base class for memory optimization strategies."""

    @abstractmethod
    async def aoptimize(
        self,
        memories: list[MemoryData],
        model: Model,
    ) -> list[MemoryData]:
        """Optimize memories asynchronously."""
        raise NotImplementedError

    def count_tokens(self, memories: list[MemoryData]) -> int:
        """Approximate token count across all memories (4 chars ~ 1 token)."""
        return sum(len(m.memory or "") // 4 for m in memories)
