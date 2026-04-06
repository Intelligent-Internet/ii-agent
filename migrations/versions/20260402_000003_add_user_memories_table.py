"""Add user_memories table for persistent agent memory.

Revision ID: 20260402_000003
Revises: 20260402_000002
Create Date: 2026-04-02
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision = "20260402_000003"
down_revision = "20260402_000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_memories",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("memory_id", sa.String(), nullable=False, unique=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("agent_id", sa.String(), nullable=True),
        sa.Column("memory", sa.String(), nullable=False),
        sa.Column("topics", JSONB(), nullable=True),
        sa.Column("input", sa.String(), nullable=True),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_index("ix_user_memories_user_id", "user_memories", ["user_id"])
    op.create_index("ix_user_memories_user_agent", "user_memories", ["user_id", "agent_id"])
    op.create_index("ix_user_memories_memory_id", "user_memories", ["memory_id"], unique=True)
    op.create_index("ix_user_memories_updated_at", "user_memories", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_user_memories_updated_at", table_name="user_memories")
    op.drop_index("ix_user_memories_memory_id", table_name="user_memories")
    op.drop_index("ix_user_memories_user_agent", table_name="user_memories")
    op.drop_index("ix_user_memories_user_id", table_name="user_memories")
    op.drop_table("user_memories")
