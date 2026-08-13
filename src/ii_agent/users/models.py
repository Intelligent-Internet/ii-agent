"""SQLAlchemy models for users domain.

- User (Main user model)
- APIKey (User API keys)
- WaitlistEntry (Gated login waitlist)
"""

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Boolean, Text, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from datetime import datetime, timezone
from typing import Any, Dict, Optional, TYPE_CHECKING
import uuid

from ii_agent.core.db.base import Base, TimestampColumn

# Forward references for relationships
if TYPE_CHECKING:
    from ii_agent.sessions.models import Session
    from ii_agent.settings.llm.models import ModelSetting
    from ii_agent.settings.mcp.models import MCPSetting
    from ii_agent.files.models import FileAsset
    from ii_agent.sessions.wishlist.models import SessionWishlist
    from ii_agent.sessions.pin.models import SessionPin
    from ii_agent.integrations.connectors.models import Connector, ComposioProfile
    from ii_agent.billing.models import BillingTransaction
    from ii_agent.projects.models import Project
    from ii_agent.settings.skills.models import Skill


class User(Base):
    """Database model for users."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String, unique=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    avatar: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    role: Mapped[str] = mapped_column(String, default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        TimestampColumn, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TimestampColumn,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(TimestampColumn, nullable=True)
    user_metadata: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)
    login_provider: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    organization: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    subscription_plan: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    subscription_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    subscription_billing_cycle: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    subscription_current_period_end: Mapped[Optional[datetime]] = mapped_column(
        TimestampColumn, nullable=True
    )
    language: Mapped[str] = mapped_column(String, default="en")

    # Relationships (using string references for forward declarations)
    sessions: Mapped[list["Session"]] = relationship(
        "Session", back_populates="user", cascade="all, delete-orphan"
    )
    model_settings: Mapped[list["ModelSetting"]] = relationship(
        "ModelSetting", back_populates="user", cascade="all, delete-orphan"
    )
    mcp_settings: Mapped[list["MCPSetting"]] = relationship(
        "MCPSetting", back_populates="user", cascade="all, delete-orphan"
    )
    file_assets: Mapped[list["FileAsset"]] = relationship(
        "FileAsset", back_populates="user", cascade="all, delete-orphan"
    )
    session_wishlists: Mapped[list["SessionWishlist"]] = relationship(
        "SessionWishlist", back_populates="user", cascade="all, delete-orphan"
    )
    session_pins: Mapped[list["SessionPin"]] = relationship(
        "SessionPin", back_populates="user", cascade="all, delete-orphan"
    )
    api_keys: Mapped[list["APIKey"]] = relationship(
        "APIKey", back_populates="user", cascade="all, delete-orphan"
    )
    connectors: Mapped[list["Connector"]] = relationship(
        "Connector", back_populates="user", cascade="all, delete-orphan"
    )
    composio_profiles: Mapped[list["ComposioProfile"]] = relationship(
        "ComposioProfile", back_populates="user", cascade="all, delete-orphan"
    )
    billing_transactions: Mapped[list["BillingTransaction"]] = relationship(
        "BillingTransaction", back_populates="user", cascade="all, delete-orphan"
    )
    projects: Mapped[list["Project"]] = relationship(
        "Project", back_populates="user", cascade="all, delete-orphan"
    )
    skills: Mapped[list["Skill"]] = relationship(
        "Skill", back_populates="user", cascade="all, delete-orphan"
    )
    user_agents = relationship(
        "UserAgent", back_populates="user", cascade="all, delete-orphan"
    )

    # Add index for email lookup
    __table_args__ = (Index("idx_users_email", "email"),)


class APIKey(Base):
    """Database model for user API keys."""

    __tablename__ = "api_keys"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    api_key: Mapped[str] = mapped_column(String, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        TimestampColumn, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TimestampColumn,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="api_keys")

    # Indexes
    __table_args__ = (
        Index("idx_api_keys_user_id", "user_id"),
        Index("idx_api_keys_is_active", "is_active"),
    )


class WaitlistEntry(Base):
    """Waitlist entries for gated logins."""

    __tablename__ = "waitlist"

    email: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        TimestampColumn,
        default=lambda: datetime.now(timezone.utc),
    )

class UserAgent(Base):
    """User-defined custom agents.

    Stores per-user agent configurations including custom system prompts,
    tool toggles, skill/connector modes, and model preferences.
    Used by the CUSTOM agent type flow in ii_claw.
    """

    __tablename__ = "user_agents"

    # id, created_at, updated_at inherited from Base

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Identity
    agent_name: Mapped[str] = mapped_column(String(128), nullable=False)
    tag: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Model preference (e.g. "claude-sonnet-4-20250514"); NULL = use session default
    model_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # System prompt (injected as custom_system_prompt)
    system_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Tool toggles (same shape as CallAgentInput.tool_args)
    # e.g. {"media_generation": false, "browser": true}
    tool_args: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True, default=dict)

    # Skill / connector modes
    # e.g. "default" | "custom_skill" | "default_and_custom_skill" | null
    skill_mode: Mapped[Optional[str]] = mapped_column(String, nullable=True, default="default")
    connector_mode: Mapped[Optional[str]] = mapped_column(String, nullable=True, default="default")

    # Flexible JSONB bags for future extension
    skill_config: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    connector_config: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    agent_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column("metadata", JSONB, nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="user_agents")

    # Indexes & constraints
    __table_args__ = (
        UniqueConstraint("user_id", "agent_name", name="uq_user_agents_user_name"),
        Index("idx_user_agents_user_id", "user_id"),
        Index("idx_user_agents_active", "user_id", "is_active"),
    )

    __table_args__ = (
        UniqueConstraint("user_id", "agent_name", name="uq_user_agents_user_name"),
        Index("idx_user_agents_user_id", "user_id"),
        Index("idx_user_agents_active", "user_id", "is_active"),
    )