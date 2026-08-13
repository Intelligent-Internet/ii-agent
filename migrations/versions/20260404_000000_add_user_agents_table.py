"""Add user_agents table for custom agent configurations.

Revision ID: 20260404_000000
Revises: 20260402_000002
Create Date: 2026-04-04
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision = "20260404_000000"
down_revision = "20260402_000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create user_agents table."""
    op.create_table(
        "user_agents",
        # PK: UUID matching Base convention
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        # FK: UUID matching users.id type
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Identity
        sa.Column("agent_name", sa.String(128), nullable=False),
        sa.Column("tag", sa.String(64), nullable=True),
        # Model preference
        sa.Column("model_id", sa.String(), nullable=True),
        # System prompt
        sa.Column("system_prompt", sa.Text(), nullable=True),
        # Tool toggles (JSONB)
        sa.Column("tool_args", JSONB(), nullable=True),
        # Skill / connector modes
        sa.Column("skill_mode", sa.String(), nullable=True, server_default="default"),
        sa.Column("connector_mode", sa.String(), nullable=True, server_default="default"),
        # Flexible JSONB bags
        sa.Column("skill_config", JSONB(), nullable=True),
        sa.Column("connector_config", JSONB(), nullable=True),
        sa.Column("metadata", JSONB(), nullable=True),
        # Status
        sa.Column("is_active", sa.Boolean(), nullable=True, server_default=sa.text("true")),
        # Timestamps: DateTime(timezone=True) matching TimestampColumn
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "agent_name", name="uq_user_agents_user_name"),
    )

    # Indexes
    op.create_index("idx_user_agents_user_id", "user_agents", ["user_id"])
    op.create_index("idx_user_agents_active", "user_agents", ["user_id", "is_active"])


def downgrade() -> None:
    """Drop user_agents table."""
    op.drop_index("idx_user_agents_active", table_name="user_agents")
    op.drop_index("idx_user_agents_user_id", table_name="user_agents")
    op.drop_table("user_agents")
