"""Sandbox ORM model."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ii_agent.agents.sandboxes.types import PoolState, SandboxProviderType, SandboxStatus
from ii_agent.core.db.base import Base, TimestampColumn


class AgentSandbox(Base):
    """Persisted sandbox record linking a session to a provider instance.

    For pool-managed sandboxes (``pool_state`` not NULL), ``session_id`` is
    NULL until the row is claimed by a session.
    """

    __tablename__ = "agent_sandboxes"

    session_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    provider: Mapped[SandboxProviderType] = mapped_column(
        String(20),
        default=SandboxProviderType.E2B,
    )
    provider_sandbox_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    status: Mapped[SandboxStatus] = mapped_column(
        String(20),
        default=SandboxStatus.INITIALIZING,
    )
    expired_at: Mapped[Optional[datetime]] = mapped_column(
        TimestampColumn,
        nullable=True,
    )
    timeout_at: Mapped[Optional[datetime]] = mapped_column(
        TimestampColumn,
        nullable=True,
    )
    provider_data: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
    )

    # ── Pool fields (NULL for non-pool sandboxes) ────────────────────────
    pool_state: Mapped[Optional[PoolState]] = mapped_column(
        String(20),
        nullable=True,
        index=True,
    )
    pool_slot: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    retire_at: Mapped[Optional[datetime]] = mapped_column(
        TimestampColumn,
        nullable=True,
    )
    claimed_at: Mapped[Optional[datetime]] = mapped_column(
        TimestampColumn,
        nullable=True,
    )
