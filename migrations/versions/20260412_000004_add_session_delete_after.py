"""Add delete_after column to sessions for timed deletion.

Nullable timestamp that, when set and in the past, triggers automatic
soft-deletion by the orphan cleanup loop.

Revision ID: 20260412_000004
Revises: 20260407_000003
Create Date: 2026-04-12
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260412_000004"
down_revision = "20260402_000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column("delete_after", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_sessions_delete_after",
        "sessions",
        ["delete_after"],
        postgresql_where=sa.text("delete_after IS NOT NULL AND is_deleted = false"),
    )


def downgrade() -> None:
    op.drop_index("idx_sessions_delete_after", table_name="sessions")
    op.drop_column("sessions", "delete_after")
