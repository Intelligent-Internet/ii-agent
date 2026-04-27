"""SQLAlchemy models for the session purge subsystem.

Tables:
  - purge_dead_letter — operator-visible ledger of provider-cleanup
    failures. One row per leaked upstream resource. Phase (b) of §4.1
    writes here when retries are exhausted (§4.5).

Design: docs/design-docs/session-lifecycle-and-data-custody.md §3.5 + §4.5.
Migration: 20260427_000008_session_purge_v34.py
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ii_agent.core.db.base import Base, TimestampColumn


class PurgeDeadLetter(Base):
    """One row per upstream resource that failed deletion past the retry budget.

    `session_id` is nullable — a row may outlive its session (purge_one_session
    will eventually DELETE the session and orphan the dead-letter rows by design;
    operator triage uses `user_id` + `provider` + `resource_id`).

    Resolution flow (manual, operator):
      1. Operator runs the leaked-resource DELETE out-of-band.
      2. Operator UPDATEs `resolved_at = now()`, `resolved_by`, `resolved_note`.
      3. Rows older than `dead_letter_retention_seconds` AND `resolved_at IS NOT NULL`
         are eligible for archival/deletion (out of scope here).
    """

    __tablename__ = "purge_dead_letter"

    # id, created_at, updated_at inherited from Base.
    # NOTE: this model intentionally re-declares created_at to bind it to
    # nullable=False; Base sets server_default=now() which suffices.

    session_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    """Originating session. Nullable: session row will be DELETEd later by
    phase (c); the dead-letter row outlives it for audit/triage."""

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    """User who owned the leaked resource. Required for operator triage."""

    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    """Upstream system identifier. E.g. 'openai', 'gcs', 'composio'."""

    resource_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    """Provider-specific resource type. E.g. 'file', 'container', 'vector_store'."""

    resource_id: Mapped[str] = mapped_column(String(512), nullable=False)
    """The leaked upstream ID — what the operator must DELETE manually."""

    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    """Last-attempt error message. Truncated by caller if huge."""

    resolved_at: Mapped[Optional[datetime]] = mapped_column(TimestampColumn, nullable=True)
    """Set when an operator confirms the upstream resource is gone."""

    resolved_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    """Operator identifier (email / on-call rotation handle)."""

    resolved_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    """Free-form resolution narrative."""
