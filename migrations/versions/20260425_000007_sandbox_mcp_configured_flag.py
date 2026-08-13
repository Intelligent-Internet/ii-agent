"""Add ``mcp_configured`` + ``mcp_configure_attempted_at`` to ``agent_sandboxes``.

Tracks whether the post-claim ``_configure_mcp`` handshake succeeded so
runtime MCP-tool factories can lazy-retry on demand instead of failing
silently for the entire session lifetime.

See docs/design-docs/sandbox-pool-claim-mcp-handoff-audit.md.

Revision ID: 20260425_000007
Revises: 20260422_000006
Create Date: 2026-04-25
"""

from alembic import op
import sqlalchemy as sa


revision = "20260425_000007"
down_revision = "20260422_000006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_sandboxes",
        sa.Column(
            "mcp_configured",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "agent_sandboxes",
        sa.Column(
            "mcp_configure_attempted_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("agent_sandboxes", "mcp_configure_attempted_at")
    op.drop_column("agent_sandboxes", "mcp_configured")
