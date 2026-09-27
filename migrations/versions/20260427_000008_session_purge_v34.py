"""Session purge v3.4 — three-phase purge schema (PR-A + PR-B).

PR-A — sessions purge columns + indexes:
    - sessions.purge_after        (DateTime, nullable)  — when grace expires
    - sessions.custody            (varchar,  nullable)  — 'standard' | 'ephemeral' | 'legal_hold'
    - sessions.purge_started_at   (DateTime, nullable)  — phase-(a) claim timestamp
    - sessions.purge_attempts     (int, default 0)      — retry counter

PR-B — purge_dead_letter table + users.is_purging:
    - purge_dead_letter table     — operator-visible leaked-resource ledger
    - users.is_purging            (bool, default false) — gates mutation endpoints
                                                          during user-account purge

Design: docs/design-docs/session-lifecycle-and-data-custody.md §3.5, §4.1, §4.5.

Revision ID: 20260427_000008
Revises: 20260425_000007
Create Date: 2026-04-27
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260427_000008"
down_revision = "20260425_000007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---- PR-A: sessions purge columns ----
    op.add_column(
        "sessions",
        sa.Column("purge_after", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "sessions",
        sa.Column(
            "custody",
            sa.String(length=32),
            nullable=False,
            server_default="standard",
        ),
    )
    op.add_column(
        "sessions",
        sa.Column("purge_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "sessions",
        sa.Column(
            "purge_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    # Partial index: only rows actively being considered for purge.
    op.create_index(
        "idx_sessions_purge_after",
        "sessions",
        ["purge_after"],
        postgresql_where=sa.text(
            "purge_after IS NOT NULL AND is_deleted = true AND custody != 'legal_hold'"
        ),
    )
    # Operator triage: stuck-claim observability.
    op.create_index(
        "idx_sessions_purge_stuck",
        "sessions",
        ["purge_started_at"],
        postgresql_where=sa.text("purge_started_at IS NOT NULL"),
    )

    # ---- PR-B: purge_dead_letter ----
    op.create_table(
        "purge_dead_letter",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "session_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("resource_kind", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=512), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "resolved_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("resolved_by", sa.String(length=128), nullable=True),
        sa.Column("resolved_note", sa.Text(), nullable=True),
    )
    op.create_index(
        "idx_purge_dead_letter_unresolved",
        "purge_dead_letter",
        ["created_at"],
        postgresql_where=sa.text("resolved_at IS NULL"),
    )
    op.create_index(
        "idx_purge_dead_letter_user",
        "purge_dead_letter",
        ["user_id"],
    )

    # ---- PR-B: users.is_purging ----
    op.add_column(
        "users",
        sa.Column(
            "is_purging",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "is_purging")
    op.drop_index("idx_purge_dead_letter_user", table_name="purge_dead_letter")
    op.drop_index("idx_purge_dead_letter_unresolved", table_name="purge_dead_letter")
    op.drop_table("purge_dead_letter")
    op.drop_index("idx_sessions_purge_stuck", table_name="sessions")
    op.drop_index("idx_sessions_purge_after", table_name="sessions")
    op.drop_column("sessions", "purge_attempts")
    op.drop_column("sessions", "purge_started_at")
    op.drop_column("sessions", "custody")
    op.drop_column("sessions", "purge_after")
