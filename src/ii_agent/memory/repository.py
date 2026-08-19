"""Data access layer for memory domain."""

import uuid

from sqlalchemy import cast, delete, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.core.db.base import BaseRepository
from ii_agent.memory.models import UserMemory


class MemoryRepository(BaseRepository[UserMemory]):
    """Repository for user memory CRUD operations."""

    model = UserMemory

    async def get_user_memories(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        *,
        agent_id: str | None = None,
        limit: int | None = None,
    ) -> list[UserMemory]:
        """Retrieve all memories for a user, newest first."""
        stmt = (
            select(UserMemory)
            .where(UserMemory.user_id == user_id)
            .order_by(UserMemory.updated_at.desc())
        )
        if agent_id is not None:
            stmt = stmt.where(UserMemory.agent_id == agent_id)
        if limit is not None and limit > 0:
            stmt = stmt.limit(limit)

        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_memory_id(
        self,
        db: AsyncSession,
        memory_id: str,
        user_id: uuid.UUID,
    ) -> UserMemory | None:
        """Retrieve a single memory by its logical memory_id."""
        stmt = select(UserMemory).where(
            UserMemory.memory_id == memory_id,
            UserMemory.user_id == user_id,
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_user_memories_paginated(
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
    ) -> tuple[list[UserMemory], int]:
        """Paginated query for the dashboard UI. Returns (items, total_count)."""
        base = select(UserMemory).where(UserMemory.user_id == user_id)

        if search:
            base = base.where(UserMemory.memory.ilike(f"%{search}%"))
        if topics:
            base = base.where(
                or_(
                    *[
                        UserMemory.topics.op("@>")(cast([t], JSONB))
                        for t in topics
                    ]
                )
            )

        # Count
        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await db.execute(count_stmt)).scalar_one()

        # Sort
        if sort_by == "memory":
            order_col = UserMemory.memory
        elif sort_by == "topics_count":
            order_col = func.jsonb_array_length(
                func.coalesce(UserMemory.topics, cast("[]", JSONB))
            )
        else:
            order_col = UserMemory.updated_at

        base = base.order_by(order_col.asc() if sort_order == "asc" else order_col.desc())

        # Paginate
        offset = (page - 1) * per_page
        base = base.offset(offset).limit(per_page)

        result = await db.execute(base)
        rows = list(result.scalars().all())
        return rows, total

    async def get_distinct_topics(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> list[str]:
        """Return all distinct topics across user memories."""
        subq = (
            select(
                func.jsonb_array_elements_text(UserMemory.topics).label("topic")
            )
            .where(UserMemory.user_id == user_id)
            .where(UserMemory.topics.is_not(None))
            .where(func.jsonb_array_length(UserMemory.topics) > 0)
        ).subquery()
        stmt = select(func.distinct(subq.c.topic))
        result = await db.execute(stmt)
        return sorted([row[0] for row in result.all()])

    async def upsert(
        self,
        db: AsyncSession,
        memory: UserMemory,
    ) -> UserMemory:
        """Insert or update a single memory."""
        existing = await db.execute(
            select(UserMemory).where(UserMemory.memory_id == memory.memory_id)
        )
        row = existing.scalar_one_or_none()

        if row is not None:
            row.memory = memory.memory
            row.topics = memory.topics
            row.input = memory.input
            if memory.agent_id is not None:
                row.agent_id = memory.agent_id
            await db.flush()
            await db.refresh(row)
            return row
        else:
            db.add(memory)
            await db.flush()
            await db.refresh(memory)
            return memory

    async def delete_by_memory_id(
        self,
        db: AsyncSession,
        memory_id: str,
        user_id: uuid.UUID,
    ) -> None:
        """Delete a single memory by its logical memory_id."""
        stmt = delete(UserMemory).where(
            UserMemory.memory_id == memory_id,
            UserMemory.user_id == user_id,
        )
        await db.execute(stmt)

    async def delete_by_memory_ids(
        self,
        db: AsyncSession,
        memory_ids: list[str],
        user_id: uuid.UUID,
    ) -> None:
        """Batch-delete memories."""
        if not memory_ids:
            return
        stmt = delete(UserMemory).where(
            UserMemory.memory_id.in_(memory_ids),
            UserMemory.user_id == user_id,
        )
        await db.execute(stmt)

    async def clear_user_memories(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> None:
        """Delete all memories for a user."""
        stmt = delete(UserMemory).where(UserMemory.user_id == user_id)
        await db.execute(stmt)
