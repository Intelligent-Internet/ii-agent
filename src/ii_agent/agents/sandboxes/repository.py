"""Sandbox data access layer."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.agents.sandboxes.models import AgentSandbox
from ii_agent.agents.sandboxes.types import PoolState, SandboxProviderType, SandboxStatus
from ii_agent.core.db.base import BaseRepository


class SandboxRepository(BaseRepository[AgentSandbox]):
    model = AgentSandbox

    async def get_active_by_session_id(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
    ) -> Optional[AgentSandbox]:
        """Find the active (non-deleted) sandbox for a session."""
        result = await db.execute(
            select(AgentSandbox)
            .where(
                AgentSandbox.session_id == session_id,
                AgentSandbox.status != SandboxStatus.DELETED,
            )
            .order_by(AgentSandbox.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    # Alias for consumers that use the shorter name
    get_by_session_id = get_active_by_session_id

    async def update_status(
        self,
        db: AsyncSession,
        sandbox_id: uuid.UUID,
        status: SandboxStatus,
    ) -> Optional[AgentSandbox]:
        """Update the sandbox status."""
        record = await self.get_by_id(db, sandbox_id)
        if record is None:
            return None
        record.status = status
        await db.flush()
        await db.refresh(record)
        return record

    async def update_provider_info(
        self,
        db: AsyncSession,
        sandbox_id: uuid.UUID,
        *,
        status: Optional[SandboxStatus] = None,
        provider_sandbox_id: Optional[str] = None,
        expired_at=None,
        provider_data: Optional[dict] = None,
    ) -> Optional[AgentSandbox]:
        """Update provider-specific fields on the sandbox record."""
        record = await self.get_by_id(db, sandbox_id)
        if record is None:
            return None
        if status is not None:
            record.status = status
        if provider_sandbox_id is not None:
            record.provider_sandbox_id = provider_sandbox_id
        if expired_at is not None:
            record.expired_at = expired_at
        if provider_data is not None:
            record.provider_data = provider_data
        await db.flush()
        await db.refresh(record)
        return record

    # ── Pool-specific queries ─────────────────────────────────────────────

    async def list_active_pool_rows(
        self,
        db: AsyncSession,
        provider: SandboxProviderType = SandboxProviderType.DOCKER,
    ) -> list[AgentSandbox]:
        """Return all pool rows in any non-DELETED state, ordered by slot."""
        result = await db.execute(
            select(AgentSandbox)
            .where(
                AgentSandbox.provider == provider,
                AgentSandbox.pool_state.isnot(None),
                AgentSandbox.status != SandboxStatus.DELETED,
            )
            .order_by(AgentSandbox.pool_slot.asc(), AgentSandbox.created_at.desc())
        )
        return list(result.scalars().all())

    async def claim_oldest_available(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        provider: SandboxProviderType = SandboxProviderType.DOCKER,
    ) -> tuple[Optional[AgentSandbox], Optional[int]]:
        """Atomically claim the oldest AVAILABLE pool row for a session.

        Uses ``SELECT ... FOR UPDATE SKIP LOCKED`` so concurrent claims
        from multiple workers do not race on the same row. Returns
        ``(row, claimed_slot)`` where ``claimed_slot`` is the slot index
        the row was occupying *before* the claim cleared it (needed by
        the pool manager to schedule the replacement). Returns
        ``(None, None)`` when the pool is empty.
        """
        result = await db.execute(
            select(AgentSandbox)
            .where(
                AgentSandbox.provider == provider,
                AgentSandbox.pool_state == PoolState.AVAILABLE,
                AgentSandbox.status == SandboxStatus.RUNNING,
                AgentSandbox.provider_sandbox_id.isnot(None),
            )
            .order_by(AgentSandbox.created_at.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None, None

        # Clear pool_slot at claim time. Once a row is CLAIMED its lifetime
        # belongs to the session, not the pool. Leaving pool_slot set
        # causes SandboxPoolManager._existing_live_slots() to treat the
        # long-lived CLAIMED row as occupying the slot, blocking
        # ensure_full() from ever recreating it if the immediate
        # post-claim replenishment row is later retired.
        claimed_slot = row.pool_slot
        row.session_id = session_id
        row.pool_state = PoolState.CLAIMED
        row.pool_slot = None
        row.claimed_at = datetime.now(timezone.utc)
        await db.flush()
        await db.refresh(row)
        return row, claimed_slot

    async def list_due_for_retirement(
        self,
        db: AsyncSession,
        now: Optional[datetime] = None,
        provider: SandboxProviderType = SandboxProviderType.DOCKER,
    ) -> list[AgentSandbox]:
        """Return AVAILABLE pool rows whose retire_at deadline has passed."""
        cutoff = now or datetime.now(timezone.utc)
        result = await db.execute(
            select(AgentSandbox)
            .where(
                AgentSandbox.provider == provider,
                AgentSandbox.pool_state == PoolState.AVAILABLE,
                AgentSandbox.retire_at.isnot(None),
                AgentSandbox.retire_at <= cutoff,
            )
            .order_by(AgentSandbox.retire_at.asc())
        )
        return list(result.scalars().all())
