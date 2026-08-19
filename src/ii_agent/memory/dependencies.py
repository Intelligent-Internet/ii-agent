"""FastAPI dependencies for memory domain."""

from typing import Annotated

from fastapi import Depends

from ii_agent.core.dependencies import ContainerDep
from ii_agent.memory.repository import MemoryRepository
from ii_agent.memory.service import MemoryService


# ==================== Repository Dependencies ====================


def get_memory_repository() -> MemoryRepository:
    """Provide MemoryRepository instance."""
    return MemoryRepository()


MemoryRepositoryDep = Annotated[MemoryRepository, Depends(get_memory_repository)]


# ==================== Service Dependencies ====================


def _get_memory_service(container: ContainerDep) -> MemoryService:
    return container.memory_service


MemoryServiceDep = Annotated[MemoryService, Depends(_get_memory_service)]
