"""Pre-warmed sandbox pool: nullable session_id + pool_state/pool_slot/retire_at/claimed_at.

Adds support for the pre-warmed sandbox pool feature. Pool-managed sandbox
rows have ``session_id=NULL`` until they are claimed by a session.

Revision ID: 20260422_000006
Revises: 20260416_000005
Create Date: 2026-04-22
"""

from alembic import op
import sqlalchemy as sa


revision = "20260422_000006"
down_revision = "20260416_000005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Make session_id nullable so pool rows can exist before being claimed.
    op.alter_column(
        "agent_sandboxes",
        "session_id",
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        nullable=True,
    )

    # Pool fields. All nullable — NULL means "not pool-managed".
    op.add_column(
        "agent_sandboxes",
        sa.Column("pool_state", sa.String(20), nullable=True),
    )
    op.add_column(
        "agent_sandboxes",
        sa.Column("pool_slot", sa.Integer(), nullable=True),
    )
    op.add_column(
        "agent_sandboxes",
        sa.Column("retire_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "agent_sandboxes",
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index(
        "ix_agent_sandboxes_pool_state",
        "agent_sandboxes",
        ["pool_state"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_sandboxes_pool_state", table_name="agent_sandboxes")
    op.drop_column("agent_sandboxes", "claimed_at")
    op.drop_column("agent_sandboxes", "retire_at")
    op.drop_column("agent_sandboxes", "pool_slot")
    op.drop_column("agent_sandboxes", "pool_state")

    # Restore NOT NULL on session_id. Any pool rows must be cleaned first
    # (they have no session, so this would fail otherwise).
    op.execute("DELETE FROM agent_sandboxes WHERE session_id IS NULL")
    op.alter_column(
        "agent_sandboxes",
        "session_id",
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        nullable=False,
    )
