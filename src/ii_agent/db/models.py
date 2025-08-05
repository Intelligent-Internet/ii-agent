from datetime import datetime, timezone
import uuid
from sqlalchemy import (
    Column,
    String,
    DateTime,
    ForeignKey,
    Boolean,
    Integer,
    Index,
    VARCHAR,
    TIMESTAMP,
)
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.dialects.sqlite import JSON as SQLiteJSON
from typing import Optional

Base = declarative_base()


class User(Base):
    """Database model for users."""

    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(VARCHAR(255), unique=True, nullable=False)
    password_hash = Column(VARCHAR(255), nullable=True)
    first_name = Column(VARCHAR(100), nullable=True)
    last_name = Column(VARCHAR(100), nullable=True)
    role = Column(VARCHAR(50), default="user")
    subscription_tier = Column(VARCHAR(50), default="free")
    is_active = Column(Boolean, default=True)
    email_verified = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        TIMESTAMP,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    last_login_at = Column(TIMESTAMP, nullable=True)
    user_metadata = Column("metadata", SQLiteJSON, nullable=True)
    login_provider = Column(VARCHAR(50), nullable=True)
    organization = Column(VARCHAR(50), nullable=True)

    # Relationships
    sessions = relationship(
        "Session", back_populates="user", cascade="all, delete-orphan"
    )
    ii_keys = relationship("IIKey", back_populates="user", cascade="all, delete-orphan")
    llm_settings = relationship(
        "LLMSetting", back_populates="user", cascade="all, delete-orphan"
    )
    mcp_settings = relationship(
        "MCPSetting", back_populates="user", cascade="all, delete-orphan"
    )
    sandboxes = relationship(
        "Sandbox", back_populates="user", cascade="all, delete-orphan"
    )

    # Add index for email lookup
    __table_args__ = (Index("idx_users_email", "email"),)


class IIKey(Base):
    """Database model for II API keys (future feature)."""

    __tablename__ = "ii_keys"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name = Column(VARCHAR(255), nullable=False)
    key_hash = Column(VARCHAR(255), nullable=False)
    prefix = Column(VARCHAR(20), nullable=False)
    permissions = Column(SQLiteJSON, default=list)
    expires_at = Column(TIMESTAMP, nullable=True)
    last_used_at = Column(TIMESTAMP, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))
    usage_count = Column(Integer, default=0)

    # Relationships
    user = relationship("User", back_populates="ii_keys")

    # Add index for key lookup
    __table_args__ = (Index("idx_ii_keys_prefix", "prefix"),)


class LLMSetting(Base):
    """Database model for LLM provider settings."""

    __tablename__ = "llm_settings"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider = Column(
        VARCHAR(100), nullable=False
    )  # 'openai', 'anthropic', 'bedrock', 'gemini', 'azure'
    encrypted_api_key = Column(VARCHAR(500), nullable=True)
    base_url = Column(VARCHAR(500), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        TIMESTAMP,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    llm_metadata = Column(
        "metadata", SQLiteJSON, nullable=True
    )  # For Azure deployment names, Bedrock config, etc.

    # Relationships
    user = relationship("User", back_populates="llm_settings")

    # Add index for provider lookup
    __table_args__ = (Index("idx_llm_settings_user_provider", "user_id", "provider"),)


class MCPSetting(Base):
    """Database model for MCP (Model Context Protocol) settings."""

    __tablename__ = "mcp_settings"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    mcp_config = Column(SQLiteJSON, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        TIMESTAMP,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    user = relationship("User", back_populates="mcp_settings")


class Session(Base):
    """Database model for agent sessions."""

    __tablename__ = "sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status = Column(VARCHAR(50), default="active")  # 'pending', 'active', 'pause'
    sandbox_id = Column(VARCHAR(255), nullable=True)
    current_plan = Column(SQLiteJSON, nullable=True)
    token_usage = Column(SQLiteJSON, nullable=True)
    settings = Column(SQLiteJSON, nullable=True)  # Model settings, preferences
    state_storage = Column(VARCHAR(500), nullable=True)  # URL for state storage
    public_url = Column(VARCHAR(500), nullable=True)
    is_public = Column(Boolean, default=False)

    # Timestamps
    last_message_at = Column(TIMESTAMP, nullable=True)
    created_at = Column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        TIMESTAMP,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    deleted_at = Column(TIMESTAMP, nullable=True)

    # Legacy fields (keeping for compatibility)
    workspace_dir = Column(String, unique=True, nullable=False)
    device_id = Column(String, nullable=True)
    name = Column(String, nullable=True)

    # Relationships
    user = relationship("User", back_populates="sessions")
    events = relationship(
        "Event", back_populates="session", cascade="all, delete-orphan"
    )

    # Add indexes
    __table_args__ = (
        Index("idx_sessions_user_id", "user_id"),
        Index("idx_sessions_status", "status"),
        Index("idx_sessions_created_at", "created_at"),
    )

    def __init__(
        self,
        id: uuid.UUID,
        user_id: uuid.UUID,
        workspace_dir: str,
        device_id: Optional[str] = None,
        name: Optional[str] = None,
    ):
        """Initialize a session with required fields."""
        self.id = str(id)
        self.user_id = str(user_id)
        self.workspace_dir = workspace_dir
        self.device_id = device_id
        self.name = name


class Event(Base):
    """Database model for session events."""

    __tablename__ = "events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(
        String(36), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    type = Column(String, nullable=False)
    content = Column(SQLiteJSON, nullable=False)
    source = Column(String, nullable=True)
    created_at = Column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))

    # Legacy fields (keeping for compatibility)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    event_type = Column(String, nullable=True)
    event_payload = Column(SQLiteJSON, nullable=True)

    # Relationships
    session = relationship("Session", back_populates="events")

    # Add indexes
    __table_args__ = (
        Index("idx_events_session_id", "session_id"),
        Index("idx_events_created_at", "created_at"),
        Index("idx_events_type", "type"),
    )

    def __init__(
        self,
        session_id: uuid.UUID,
        type: str,
        content: dict,
        source: Optional[str] = None,
    ):
        """Initialize an event."""
        self.session_id = str(session_id)
        self.type = type
        self.content = content
        self.source = source
        # Support legacy fields
        self.event_type = type
        self.event_payload = content


class Sandbox(Base):
    """Database model for sandboxes."""

    __tablename__ = "sandboxes"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    provider = Column(VARCHAR(50), default="e2b")  # Provider name
    sandbox_id = Column(
        VARCHAR(255), unique=True, nullable=False
    )  # Provider's sandbox ID
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    template = Column(VARCHAR(100), default="base")
    status = Column(
        VARCHAR(50), default="initializing"
    )  # 'initializing', 'running', 'stopped', 'error'
    cpu_limit = Column(Integer, default=1000)  # millicores
    memory_limit = Column(Integer, default=512)  # MB
    disk_limit = Column(Integer, default=1024)  # MB
    network_enabled = Column(Boolean, default=True)
    sandbox_metadata = Column("metadata", SQLiteJSON, nullable=True)

    # Timestamps
    created_at = Column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))
    started_at = Column(TIMESTAMP, nullable=True)
    stopped_at = Column(TIMESTAMP, nullable=True)
    last_activity_at = Column(TIMESTAMP, nullable=True)

    # Relationships
    user = relationship("User", back_populates="sandboxes")

    # Add indexes
    __table_args__ = (
        Index("idx_sandboxes_user_id", "user_id"),
        Index("idx_sandboxes_status", "status"),
        Index("idx_sandboxes_sandbox_id", "sandbox_id"),
    )
