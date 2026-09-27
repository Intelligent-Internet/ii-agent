"""Add summary_authority column to chat_summaries.

Tracks which compaction system (native vs A2A CLI backend) created each
summary, enabling cross-authority chaining prevention.

Revision ID: 20260407_000003
Revises: 20260402_000002
Create Date: 2026-04-07
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260407_000003"
down_revision = "20260402_000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chat_summaries",
        sa.Column("summary_authority", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("chat_summaries", "summary_authority")
