"""Session purge — SAR fast-track schema (PR-G part 1).

Adds:
  - sessions.sar_priority      (bool, default false) — fast-track flag
  - sar_intake table           — verified Subject Access Request ledger

Design: docs/design-docs/session-lifecycle-and-data-custody.md §16, I12, I13.

Revision ID: 20260427_000009
Revises: 20260427_000008
Create Date: 2026-04-27
"""

from alembic import op
import sqlalchemy as sa


revision = "20260427_000009"
down_revision = "20260427_000008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---- sessions.sar_priority ----
    op.add_column(
        "sessions",
        sa.Column(
            "sar_priority",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    # Partial index: SAR fast-track queue lookups.
    op.create_index(
        "idx_sessions_sar_priority",
        "sessions",
        ["sar_priority"],
        postgresql_where=sa.text("sar_priority = true AND is_deleted = true"),
    )

    # ---- sar_intake ----
    # Composite PK (user_id, received_at) — a user may have multiple
    # historical SARs; only the (verified_at IS NOT NULL AND closed_at IS NULL)
    # row is "active" at any time. Lawyer memo §5.
    op.create_table(
        "sar_intake",
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "verified_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "closed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("verification_method", sa.String(length=255), nullable=False),
        sa.Column(
            "requesting_authority",
            sa.String(length=128),
            nullable=False,
            server_default="USER_SELF_SERVICE",
        ),
        sa.Column(
            "scope",
            sa.String(length=64),
            nullable=False,
            server_default="ALL",
        ),
        sa.Column(
            "session_count_flagged",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "retention_exception_kind",
            sa.String(length=32),
            nullable=True,
        ),
        sa.Column(
            "retention_exception_detail",
            sa.Text(),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("user_id", "received_at", name="pk_sar_intake"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_sar_intake_user",
        ),
    )
    # Partial index: active SAR lookup is a hot path for restore-endpoint
    # I16 check + grace-sweep I12 check.
    op.create_index(
        "idx_sar_intake_active",
        "sar_intake",
        ["user_id"],
        postgresql_where=sa.text("verified_at IS NOT NULL AND closed_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_sar_intake_active", table_name="sar_intake")
    op.drop_table("sar_intake")
    op.drop_index("idx_sessions_sar_priority", table_name="sessions")
    op.drop_column("sessions", "sar_priority")
