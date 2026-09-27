from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Index, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ii_agent.core.db.base import Base, TimestampColumn


class ApplicationEvent(Base):
    """SQLAlchemy model for the ``application_events`` table."""

    __tablename__ = "application_events"

    event_type: Mapped[str] = mapped_column(String(100))
    event_group: Mapped[str] = mapped_column(String(50))
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUID)
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID)
    content: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    stripped_at: Mapped[datetime | None] = mapped_column(TimestampColumn, nullable=True)
    """Set by ``pii_strip.strip_user_pii_art17`` to mark this row as having
    survived an Art. 17 strip pass. Required by I11 to distinguish
    strip-touched rows (must contain only allowlisted keys) from system
    events that legitimately carry no user_id (must be ignored by I11).

    Migration: 20260429_000011_invariant_hardening.py."""

    __table_args__ = (
        Index(
            "idx_app_events_session",
            "session_id",
            "created_at",
        ),
        Index(
            "idx_app_events_session_type",
            "session_id",
            "event_type",
        ),
        Index(
            "idx_app_events_run",
            "run_id",
            "created_at",
            postgresql_where=text("run_id IS NOT NULL"),
        ),
        Index(
            "idx_app_events_group",
            "event_group",
            "created_at",
        ),
        Index(
            "idx_app_events_user",
            "user_id",
            "created_at",
        ),
    )
