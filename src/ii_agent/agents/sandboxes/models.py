"""Sandbox ORM model."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ii_agent.agents.sandboxes.types import SandboxProviderType, SandboxStatus
from ii_agent.core.db.base import Base, TimestampColumn


class AgentSandbox(Base):
    """Persisted sandbox record linking a session to a provider instance."""

    __tablename__ = "agent_sandboxes"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        index=True,
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
