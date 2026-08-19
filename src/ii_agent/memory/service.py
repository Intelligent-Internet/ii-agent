"""Business logic for memory domain.

Combines DB access via MemoryRepository with Redis caching via MemoryCacheService.
Follows the project's service pattern: takes db: AsyncSession as first parameter.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.memory.cache_service import MemoryCacheService
from ii_agent.memory.models import UserMemory
from ii_agent.memory.repository import MemoryRepository
from ii_agent.memory.schemas import MemoryData, MemoryResponse

logger = logging.getLogger(__name__)


def _to_response(record: UserMemory) -> MemoryResponse:
    """Convert ORM record to API response DTO."""
    return MemoryResponse(
        memory_id=record.memory_id,
        memory=record.memory,
        topics=record.topics,
        input=record.input,
        agent_id=record.agent_id,
        created_at=int(record.created_at.timestamp()) if record.created_at else None,
        updated_at=int(record.updated_at.timestamp()) if record.updated_at else None,
    )


def _to_data(record: UserMemory) -> MemoryData:
    """Convert ORM record to domain DTO."""
    return MemoryData(
        memory_id=record.memory_id,
        memory=record.memory,
        topics=record.topics,
        user_id=record.user_id,
        input=record.input,
        agent_id=record.agent_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


class MemoryService:
    """Service for user memory operations."""

    def __init__(
        self,
        *,
        memory_repo: MemoryRepository,
        cache: MemoryCacheService,
    ) -> None:
        self._repo = memory_repo
        self._cache = cache

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    async def get_user_memories(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        *,
        agent_id: str | None = None,
        limit: int | None = None,
    ) -> list[MemoryData]:
        """Retrieve all memories for a user, newest first.

        Uses cache for the unfiltered case (agent context injection).
        """
        use_cache = agent_id is None and limit is None
        user_id_str = str(user_id)

        if use_cache:
            cached = await self._cache.get_user_memories(user_id_str)
            if cached is not None:
                return [MemoryData.model_validate(d) for d in cached]

        rows = await self._repo.get_user_memories(
            db, user_id, agent_id=agent_id, limit=limit
        )
        memories = [_to_data(row) for row in rows]

        if use_cache:
            await self._cache.set_user_memories(
                user_id_str, [m.model_dump(mode="json") for m in memories]
            )

        return memories

    async def get_memory(
        self,
        db: AsyncSession,
        memory_id: str,
        user_id: uuid.UUID,
    ) -> MemoryResponse | None:
        row = await self._repo.get_by_memory_id(db, memory_id, user_id)
        return _to_response(row) if row else None

    async def get_memories_paginated(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        *,
        page: int = 1,
        per_page: int = 10,
        search: str | None = None,
        topics: list[str] | None = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> tuple[list[MemoryResponse], int]:
        """Paginated query with Redis cache."""
        user_id_str = str(user_id)
        params_str = (
            f"{page}:{per_page}:{search}:"
            f"{sorted(topics) if topics else ''}:{sort_by}:{sort_order}"
        )
        params_hash = hashlib.md5(params_str.encode()).hexdigest()[:12]

        cached = await self._cache.get_paginated_memories(user_id_str, params_hash)
        if cached is not None:
            memories = [MemoryResponse.model_validate(d) for d in cached["memories"]]
            return memories, cached["total"]

        rows, total = await self._repo.get_user_memories_paginated(
            db,
            user_id,
            page=page,
            per_page=per_page,
            search=search,
            topics=topics,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        memories = [_to_response(row) for row in rows]

        await self._cache.set_paginated_memories(
            user_id_str,
            params_hash,
            {"memories": [m.model_dump(mode="json") for m in memories], "total": total},
        )

        return memories, total

    async def get_distinct_topics(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> list[str]:
        user_id_str = str(user_id)
        cached = await self._cache.get_user_topics(user_id_str)
        if cached is not None:
            return cached

        topics = await self._repo.get_distinct_topics(db, user_id)
        await self._cache.set_user_topics(user_id_str, topics)
        return topics

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    async def upsert_memory(
        self,
        db: AsyncSession,
        *,
        memory_id: str,
        user_id: uuid.UUID,
        memory_text: str,
        topics: list[str] | None = None,
        input_text: str | None = None,
        agent_id: str | None = None,
    ) -> MemoryResponse:
        """Insert or update a single memory."""
        record = UserMemory(
            memory_id=memory_id,
            user_id=user_id,
            agent_id=agent_id,
            memory=memory_text,
            topics=topics,
            input=input_text,
        )
        saved = await self._repo.upsert(db, record)
        await self._cache.evict_user_memory_data(str(user_id))
        return _to_response(saved)

    async def delete_memory(
        self,
        db: AsyncSession,
        memory_id: str,
        user_id: uuid.UUID,
    ) -> None:
        await self._repo.delete_by_memory_id(db, memory_id, user_id)
        await self._cache.evict_user_memory_data(str(user_id))

    async def delete_memories(
        self,
        db: AsyncSession,
        memory_ids: list[str],
        user_id: uuid.UUID,
    ) -> None:
        await self._repo.delete_by_memory_ids(db, memory_ids, user_id)
        await self._cache.evict_user_memory_data(str(user_id))

    async def clear_user_memories(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> None:
        await self._repo.clear_user_memories(db, user_id)
        await self._cache.evict_user_memory_data(str(user_id))

    # ------------------------------------------------------------------
    # User preferences
    # ------------------------------------------------------------------

    async def load_user_memory_preferences(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Load memory preferences from user metadata.

        Returns dict with 'has_memory' key, defaulting to True.
        """
        from ii_agent.users.models import User
        from sqlalchemy import select

        user_id_str = str(user_id)

        cached = await self._cache.get_user_prefs(user_id_str)
        if cached is not None:
            return cached

        try:
            result = await db.execute(
                select(User.user_metadata).where(User.id == user_id)
            )
            row = result.scalar_one_or_none()
            if row and isinstance(row, dict):
                prefs = row.get("preferences", {})
                data = {"has_memory": prefs.get("has_memory", True)}
            else:
                data = {"has_memory": True}
        except Exception as e:
            logger.warning(f"Failed to load user memory preferences: {e}")
            data = {"has_memory": True}

        await self._cache.set_user_prefs(user_id_str, data)
        return data
