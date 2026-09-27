"""Add timeout_at column and FK constraint to agent_sandboxes.

R3: Add the foreign key from agent_sandboxes.session_id to sessions.id
    that the ORM model declares but the initial migration omitted.
R6: Add timeout_at column for persistent sandbox timeout tracking.

Revision ID: 20260416_000005
Revises: 20260412_000004
Create Date: 2026-04-16
"""

from alembic import op
import sqlalchemy as sa

revision = "20260416_000005"
down_revision = "20260412_000004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # R6: Add persistent timeout column
    op.add_column(
        "agent_sandboxes",
        sa.Column("timeout_at", sa.DateTime(timezone=True), nullable=True),
    )

    # R3: Add the FK that the ORM model declares but was never created.
    # Clean up any sandbox rows whose session_id no longer exists first,
    # otherwise the FK creation will fail.
    op.execute(
        """
        UPDATE agent_sandboxes
        SET status = 'deleted'
        WHERE session_id NOT IN (SELECT id FROM sessions)
          AND status != 'deleted'
        """
    )
    op.create_foreign_key(
        "fk_agent_sandboxes_session_id",
        "agent_sandboxes",
        "sessions",
        ["session_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_agent_sandboxes_session_id", "agent_sandboxes", type_="foreignkey")
    op.drop_column("agent_sandboxes", "timeout_at")
