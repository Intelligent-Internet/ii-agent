"""Repository layer for sessions domain - data access only."""

import uuid
from typing import Optional, List

from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ii_agent.core.db import BaseRepository
from ii_agent.sessions.models import Session


class SessionRepository(BaseRepository[Session]):
    """Data access layer for Session model."""

    model = Session

    # ==================== Basic CRUD ====================

    async def get_by_id(self, db: AsyncSession, entity_id: uuid.UUID) -> Optional[Session]:
        """Get a session by its ID."""
        result = await db.execute(select(Session).where(Session.id == entity_id))
        return result.scalar_one_or_none()

    async def get_by_id_with_project(
        self, db: AsyncSession, session_id: uuid.UUID
    ) -> Optional[Session]:
        """Get a session by ID with project eagerly loaded."""
        result = await db.execute(
            select(Session).options(selectinload(Session.project)).where(Session.id == session_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id_and_user(
        self, db: AsyncSession, session_id: uuid.UUID, user_id: uuid.UUID
    ) -> Optional[Session]:
        """Get a non-deleted session for a specific user with project loaded."""
        result = await db.execute(
            select(Session)
            .options(selectinload(Session.project))
            .where(
                Session.id == session_id,
                Session.user_id == user_id,
                Session.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_workspace(self, db: AsyncSession, workspace_dir: str) -> Optional[Session]:
        """Get a session by its workspace directory."""
        result = await db.execute(select(Session).where(Session.workspace_dir == workspace_dir))
        return result.scalar_one_or_none()

    async def get_public_by_id(self, db: AsyncSession, session_id: uuid.UUID) -> Optional[Session]:
        """Get a public, non-deleted session by ID."""
        result = await db.execute(
            select(Session).where(
                Session.id == session_id,
                Session.is_public,
                Session.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def get_user_id(self, db: AsyncSession, session_id: uuid.UUID) -> Optional[uuid.UUID]:
        """Get the user ID for a session."""
        session = await self.get_by_id(db, session_id)
        if not session:
            return None
        return session.user_id

    # ==================== Query Operations ====================

    async def get_model_setting_id(
        self, db: AsyncSession, session_id: uuid.UUID
    ) -> Optional[uuid.UUID]:
        """Get the LLM setting ID for a session."""
        result = await db.execute(select(Session.model_setting_id).where(Session.id == session_id))
        return result.scalar_one_or_none()

    async def get_user_sessions(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        search_term: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
        public_only: Optional[bool] = False,
        session_type: Optional[str] = None,
    ) -> tuple[List[Session], int]:
        """Get paginated sessions for a user with optional filters."""
        conditions = [Session.user_id == user_id, Session.is_deleted.is_(False)]

        if public_only:
            conditions.append(Session.is_public)
        if search_term:
            conditions.append(Session.name.ilike(f"%{search_term}%"))
        if session_type == "chat":
            conditions.append(Session.app_kind == "chat")
        elif session_type == "agent":
            conditions.append(Session.app_kind == "agent")

        count_query = select(func.count()).select_from(Session).where(*conditions)
        count_result = await db.execute(count_query)
        total = count_result.scalar()

        offset = (page - 1) * per_page
        data_query = (
            select(Session)
            .options(selectinload(Session.project))
            .where(*conditions)
            .order_by(desc(Session.created_at))
            .limit(per_page)
            .offset(offset)
        )

        result = await db.execute(data_query)
        sessions = list(result.scalars().all())

        return sessions, total

    async def get_non_deleted_by_ids_and_user(
        self, db: AsyncSession, session_ids: list[uuid.UUID], user_id: uuid.UUID
    ) -> list[Session]:
        """Get non-deleted sessions matching the given IDs for a specific user."""
        result = await db.execute(
            select(Session).where(
                Session.id.in_(session_ids),
                Session.user_id == user_id,
                Session.is_deleted.is_(False),
            )
        )
        return list(result.scalars().all())

    async def get_non_deleted_by_ids(
        self, db: AsyncSession, session_ids: list[uuid.UUID]
    ) -> list[Session]:
        """Get non-deleted sessions matching the given IDs."""
        if not session_ids:
            return []
        result = await db.execute(
            select(Session).where(
                Session.id.in_(session_ids),
                Session.is_deleted.is_(False),
            )
        )
        return list(result.scalars().all())

    # ==================== Update Operations ====================

    async def update_api_version(
        self, db: AsyncSession, session_id: uuid.UUID, api_version: str
    ) -> None:
        """Update the api_version of a session."""
        await db.execute(
            update(Session).where(Session.id == session_id).values(api_version=api_version)
        )
        await db.flush()
