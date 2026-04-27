"""SQLAlchemy models for sessions domain.

ChatSummary (formerly ConversationSummary) has been moved to ii_agent.chat.models (only used by chat).
"""

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING
import uuid

from ii_agent.agents.types import AgentType
from ii_agent.core.db.base import Base, TimestampColumn
from ii_agent.sessions.types import AppKind, SessionCustody, SessionState

# Forward references for relationships
if TYPE_CHECKING:
    from ii_agent.users.models import User
    from ii_agent.settings.llm.models import ModelSetting
    from ii_agent.projects.models import Project
    from ii_agent.realtime.events.models import ApplicationEvent
    from ii_agent.content.slides.models import SlideContent, SlideVersion
    from ii_agent.content.storybook.models import Storybook
    from ii_agent.sessions.wishlist.models import SessionWishlist
    from ii_agent.sessions.pin.models import SessionPin
    from ii_agent.projects.databases.models import ProjectDatabase


class Session(Base):
    """Database model for agent sessions."""

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    version: Mapped[int] = mapped_column(BigInteger, default=0)
    model_setting_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("model_settings.id"), nullable=True
    )
    name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    status: Mapped[SessionState] = mapped_column(String, default=SessionState.ACTIVE)
    agent_type: Mapped[Optional[AgentType]] = mapped_column(String, nullable=True)
    app_kind: Mapped[AppKind] = mapped_column(
        String, nullable=False, default=AppKind.AGENT, server_default=AppKind.AGENT
    )
    public_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    api_version: Mapped[str] = mapped_column(String, default="v0")
    parent_session_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=True
    )

    # Session metadata
    session_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Timestamps
    last_message_at: Mapped[Optional[datetime]] = mapped_column(TimestampColumn, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TimestampColumn, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TimestampColumn,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    delete_after: Mapped[Optional[datetime]] = mapped_column(TimestampColumn, nullable=True)

    # ---- Purge subsystem (§4.1, three-phase purge driver) ----
    # See docs/design-docs/session-lifecycle-and-data-custody.md §3.5 + §4.1
    # PR-A migration: 20260427_000008_session_purge_v34.py
    purge_after: Mapped[Optional[datetime]] = mapped_column(TimestampColumn, nullable=True)
    """When grace expires and the session becomes eligible for hard purge.
    Backfilled by the cleanup-loop bulk update (§4.1 step 0)."""

    custody: Mapped[SessionCustody] = mapped_column(
        String(32),
        nullable=False,
        default=SessionCustody.STANDARD,
        server_default=SessionCustody.STANDARD.value,
    )
    """Retention custody (I1/I3): legal_hold blocks purge entirely."""

    purge_started_at: Mapped[Optional[datetime]] = mapped_column(TimestampColumn, nullable=True)
    """Phase-(a) claim timestamp. Set by claim_one_session, refreshed by
    heartbeat_claim, cleared on release_claim. Stale (> claim_timeout) =
    reclaimable (Adversarial #19)."""

    purge_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    """Retry counter. >= max_attempts ⇒ permanent dead-letter (§4.5)."""

    # Relationships (using string references)
    user: Mapped["User"] = relationship("User", back_populates="sessions")
    model_setting: Mapped[Optional["ModelSetting"]] = relationship(
        "ModelSetting", back_populates="sessions"
    )
    project: Mapped[Optional["Project"]] = relationship(
        "Project", back_populates="session", uselist=False
    )
    events: Mapped[list["ApplicationEvent"]] = relationship(
        "ApplicationEvent",
        primaryjoin="Session.id == foreign(ApplicationEvent.session_id)",
        cascade="all, delete-orphan",
        viewonly=True,
    )
    # NOTE: Files are linked via SessionAsset many-to-many, not direct FK.
    # Access session files via FileRepository.get_by_session_id() instead.
    slide_contents: Mapped[list["SlideContent"]] = relationship(
        "SlideContent", back_populates="session", cascade="all, delete-orphan"
    )
    slide_versions: Mapped[list["SlideVersion"]] = relationship(
        "SlideVersion", back_populates="session", cascade="all, delete-orphan"
    )
    storybooks: Mapped[list["Storybook"]] = relationship(
        "Storybook", back_populates="session", cascade="all, delete-orphan"
    )
    wishlisted_by: Mapped[list["SessionWishlist"]] = relationship(
        "SessionWishlist", back_populates="session", cascade="all, delete-orphan"
    )
    pinned_by: Mapped[list["SessionPin"]] = relationship(
        "SessionPin", back_populates="session", cascade="all, delete-orphan"
    )
    databases: Mapped[list["ProjectDatabase"]] = relationship(
        "ProjectDatabase", back_populates="session", cascade="all, delete-orphan"
    )

    # Indexes
    __table_args__ = (
        Index("idx_sessions_user_id", "user_id"),
        Index("idx_sessions_status", "status"),
        Index("idx_sessions_created_at", "created_at"),
        Index("idx_sessions_model_setting_id", "model_setting_id"),
    )

    __mapper_args__ = {"version_id_col": version}

    def get_workspace_dir(self) -> str:
        """Get the workspace directory for this session."""
        from ii_agent.core.config.settings import get_settings

        settings = get_settings()
        return f"{settings.workspace_path}/{self.id}"
