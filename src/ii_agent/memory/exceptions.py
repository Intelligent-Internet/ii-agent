"""Domain-specific exceptions for memory."""

from ii_agent.core.exceptions import NotFoundError


class MemoryNotFoundError(NotFoundError):
    """Raised when a requested memory does not exist."""

    def __init__(self, memory_id: str) -> None:
        super().__init__(f"Memory not found: {memory_id}")
