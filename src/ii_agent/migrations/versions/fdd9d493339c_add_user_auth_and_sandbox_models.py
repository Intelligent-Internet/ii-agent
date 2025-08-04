"""Add user auth and sandbox models

Revision ID: fdd9d493339c
Revises: a89eabebd4fa
Create Date: 2025-08-04 17:47:56.567421

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "fdd9d493339c"
down_revision: Union[str, None] = "a89eabebd4fa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create users table
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("email", sa.VARCHAR(255), nullable=False),
        sa.Column("username", sa.VARCHAR(100), nullable=False),
        sa.Column("password_hash", sa.VARCHAR(255), nullable=True),
        sa.Column("first_name", sa.VARCHAR(100), nullable=True),
        sa.Column("last_name", sa.VARCHAR(100), nullable=True),
        sa.Column("role", sa.VARCHAR(50), nullable=True),
        sa.Column("subscription_tier", sa.VARCHAR(50), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("email_verified", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("last_login_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("login_provider", sa.VARCHAR(50), nullable=True),
        sa.Column("organization", sa.VARCHAR(50), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("username"),
    )
    op.create_index("idx_users_email", "users", ["email"], unique=False)
    op.create_index("idx_users_username", "users", ["username"], unique=False)

    # Create ii_keys table
    op.create_table(
        "ii_keys",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("name", sa.VARCHAR(255), nullable=False),
        sa.Column("key_hash", sa.VARCHAR(255), nullable=False),
        sa.Column("prefix", sa.VARCHAR(20), nullable=False),
        sa.Column("permissions", sa.JSON(), nullable=True),
        sa.Column("expires_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("last_used_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("usage_count", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_ii_keys_prefix", "ii_keys", ["prefix"], unique=False)

    # Create llm_settings table
    op.create_table(
        "llm_settings",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("provider", sa.VARCHAR(100), nullable=False),
        sa.Column("encrypted_api_key", sa.VARCHAR(500), nullable=True),
        sa.Column("base_url", sa.VARCHAR(500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_llm_settings_user_provider",
        "llm_settings",
        ["user_id", "provider"],
        unique=False,
    )

    # Create mcp_settings table
    op.create_table(
        "mcp_settings",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("mcp_config", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create sandboxes table
    op.create_table(
        "sandboxes",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("provider", sa.VARCHAR(50), nullable=True),
        sa.Column("sandbox_id", sa.VARCHAR(255), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("template", sa.VARCHAR(100), nullable=True),
        sa.Column("status", sa.VARCHAR(50), nullable=True),
        sa.Column("cpu_limit", sa.Integer(), nullable=True),
        sa.Column("memory_limit", sa.Integer(), nullable=True),
        sa.Column("disk_limit", sa.Integer(), nullable=True),
        sa.Column("network_enabled", sa.Boolean(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("stopped_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("last_activity_at", sa.TIMESTAMP(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sandbox_id"),
    )
    op.create_index("idx_sandboxes_user_id", "sandboxes", ["user_id"], unique=False)
    op.create_index("idx_sandboxes_status", "sandboxes", ["status"], unique=False)
    op.create_index(
        "idx_sandboxes_sandbox_id", "sandboxes", ["sandbox_id"], unique=False
    )

    # Update existing session table to add new fields
    with op.batch_alter_table("session", schema=None) as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.String(36), nullable=True))
        batch_op.add_column(sa.Column("status", sa.VARCHAR(50), nullable=True))
        batch_op.add_column(sa.Column("sandbox_id", sa.VARCHAR(255), nullable=True))
        batch_op.add_column(sa.Column("current_plan", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("token_usage", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("settings", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("state_storage", sa.VARCHAR(500), nullable=True))
        batch_op.add_column(sa.Column("public_url", sa.VARCHAR(500), nullable=True))
        batch_op.add_column(sa.Column("is_public", sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column("last_message_at", sa.TIMESTAMP(), nullable=True))
        batch_op.add_column(sa.Column("updated_at", sa.TIMESTAMP(), nullable=True))
        batch_op.add_column(sa.Column("deleted_at", sa.TIMESTAMP(), nullable=True))
        batch_op.create_foreign_key(
            "fk_session_user_id", "users", ["user_id"], ["id"], ondelete="CASCADE"
        )

    # Rename session table to sessions
    op.rename_table("session", "sessions")

    # Create indexes for sessions table
    op.create_index("idx_sessions_user_id", "sessions", ["user_id"], unique=False)
    op.create_index("idx_sessions_status", "sessions", ["status"], unique=False)
    op.create_index("idx_sessions_created_at", "sessions", ["created_at"], unique=False)

    # Update existing event table to add new fields
    with op.batch_alter_table("event", schema=None) as batch_op:
        batch_op.add_column(sa.Column("type", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("content", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("source", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("created_at", sa.TIMESTAMP(), nullable=True))

    # Rename event table to events
    op.rename_table("event", "events")

    # Update foreign key constraint for events table
    with op.batch_alter_table("events", schema=None) as batch_op:
        batch_op.drop_constraint("event_session_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "fk_events_session_id",
            "sessions",
            ["session_id"],
            ["id"],
            ondelete="CASCADE",
        )

    # Create indexes for events table
    op.create_index("idx_events_session_id", "events", ["session_id"], unique=False)
    op.create_index("idx_events_created_at", "events", ["created_at"], unique=False)
    op.create_index("idx_events_type", "events", ["type"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Drop indexes for events table
    op.drop_index("idx_events_type", table_name="events")
    op.drop_index("idx_events_created_at", table_name="events")
    op.drop_index("idx_events_session_id", table_name="events")

    # Rename events table back to event
    op.rename_table("events", "event")

    # Remove new columns from event table
    with op.batch_alter_table("event", schema=None) as batch_op:
        batch_op.drop_column("created_at")
        batch_op.drop_column("source")
        batch_op.drop_column("content")
        batch_op.drop_column("type")

    # Drop indexes for sessions table
    op.drop_index("idx_sessions_created_at", table_name="sessions")
    op.drop_index("idx_sessions_status", table_name="sessions")
    op.drop_index("idx_sessions_user_id", table_name="sessions")

    # Rename sessions table back to session
    op.rename_table("sessions", "session")

    # Remove new columns from session table
    with op.batch_alter_table("session", schema=None) as batch_op:
        batch_op.drop_constraint("fk_session_user_id", type_="foreignkey")
        batch_op.drop_column("deleted_at")
        batch_op.drop_column("updated_at")
        batch_op.drop_column("last_message_at")
        batch_op.drop_column("is_public")
        batch_op.drop_column("public_url")
        batch_op.drop_column("state_storage")
        batch_op.drop_column("settings")
        batch_op.drop_column("token_usage")
        batch_op.drop_column("current_plan")
        batch_op.drop_column("sandbox_id")
        batch_op.drop_column("status")
        batch_op.drop_column("user_id")

    # Drop new tables
    op.drop_table("sandboxes")
    op.drop_table("mcp_settings")
    op.drop_table("llm_settings")
    op.drop_table("ii_keys")
    op.drop_table("users")
