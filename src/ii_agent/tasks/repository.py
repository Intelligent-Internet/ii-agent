"""Repository layer for run tasks — pure CRUD and queries."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.core.db.base import BaseRepository
from ii_agent.tasks.models import RunTask, TaskLog
from ii_agent.tasks.types import RunStatus


class RunTaskRepository(BaseRepository[RunTask]):
    """Data access layer for RunTask — extends BaseRepository with domain queries."""

    model = RunTask

    # ── Queries ────────────────────────────────────────────────────────────

    async def find_last_by_session(self, db: AsyncSession, session_id: uuid.UUID) -> RunTask | None:
        result = await db.execute(
            select(RunTask)
            .where(RunTask.session_id == session_id)
            .order_by(RunTask.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def find_active_by_session(
        self, db: AsyncSession, session_id: uuid.UUID
    ) -> RunTask | None:
        """Find the active (non-terminal) task for a session."""
        active_values = [s.value for s in RunStatus.active_states()]
        result = await db.execute(
            select(RunTask)
            .where(
                RunTask.session_id == session_id,
                RunTask.status.in_(active_values),
            )
            .order_by(RunTask.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_by_session(self, db: AsyncSession, session_id: uuid.UUID) -> list[RunTask]:
        result = await db.execute(
            select(RunTask)
            .where(RunTask.session_id == session_id)
            .order_by(RunTask.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_running_session_ids(self, db: AsyncSession) -> list[str]:
        """Return session ids whose latest task is in a non-terminal state that
        the orphan-cleanup path on startup is responsible for reaping.

        This must include ABORTING — otherwise a run that the user cancelled
        right before a backend crash/restart never gets force-cancelled, the
        task is permanently stuck in ABORTING, and the frontend keeps the
        "thinking" spinner on forever (ABORTING is part of isActiveRunStatus).
        """
        result = await db.execute(
            select(RunTask.session_id).where(
                RunTask.status.in_([RunStatus.RUNNING, RunStatus.ABORTING]),
            )
        )
        return list(result.scalars().all())


class TaskLogRepository(BaseRepository[TaskLog]):
    """Data access layer for TaskLog — append-only audit trail."""

    model = TaskLog

    async def list_by_task(self, db: AsyncSession, task_id: uuid.UUID) -> list[TaskLog]:
        result = await db.execute(
            select(TaskLog).where(TaskLog.task_id == task_id).order_by(TaskLog.created_at.asc())
        )
        return list(result.scalars().all())
