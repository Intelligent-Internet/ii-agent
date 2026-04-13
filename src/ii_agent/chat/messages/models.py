"""Database models for chat messages and conversation summaries."""

from datetime import datetime, timezone
from typing import Optional
import uuid

from sqlalchemy import ARRAY, BigInteger, Boolean, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB, UUID

from ii_agent.core.db.base import Base, TimestampColumn


class ChatMessage(Base):
    """Chat messages for chat mode conversations.

    Stores messages with structured ContentPart list:
    - content: List of ContentPart objects (text, reasoning, tool_call, tool_result, etc.)
    - usage: Token usage statistics from LLM response
    - tokens: Accumulated total tokens
    """

    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(
        String, nullable=False
    )  # "user", "assistant", "system", or "tool"
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)  # List of ContentPart objects
    usage: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True
    )  # Usage statistics (prompt_tokens, completion_tokens, etc.)
    tokens: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True
    )  # Total accumulated tokens
    model: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    tools: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)  # Tools used in the message
    message_metadata: Mapped[Optional[dict]] = mapped_column(
        "metadata", JSONB, nullable=True
    )  # General message metadata
    provider_metadata: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True
    )  # Provider-specific metadata
    file_ids: Mapped[Optional[list[uuid.UUID]]] = mapped_column(
        ARRAY(UUID), nullable=True
    )  # Array of file IDs associated with the message
    created_at: Mapped[datetime] = mapped_column(
        TimestampColumn, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TimestampColumn,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    parent_message_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_messages.id", ondelete="SET NULL"),
        nullable=True,
    )  # Link to parent message (user message for assistant responses)
    is_finished: Mapped[Optional[bool]] = mapped_column(
        Boolean, nullable=True, default=True
    )  # Indicates if message is complete
    finish_reason: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )  # Reason why message generation finished (for assistant messages)

    __table_args__ = (
        Index("idx_chat_messages_session", "session_id"),
        Index("idx_chat_messages_created", "created_at"),
        Index("idx_chat_messages_parent", "parent_message_id"),
        Index("idx_chat_messages_session_created", "session_id", "created_at"),
    )


class ChatSummary(Base):
    """Conversation summaries for context management."""

    __tablename__ = "chat_summaries"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE")
    )

    # Summary content
    summary_text: Mapped[str] = mapped_column(Text)

    # Range (only end_message_id needed due to chronological order)
    end_message_id: Mapped[uuid.UUID] = mapped_column(UUID)

    # Token metadata
    original_tokens: Mapped[int] = mapped_column(BigInteger)
    summary_tokens: Mapped[int] = mapped_column(BigInteger)
    compression_ratio: Mapped[float] = mapped_column(Float)
    model_id: Mapped[str] = mapped_column(String)

    # Chaining for recursive compression
    parent_summary_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_summaries.id"), nullable=True
    )

    # Authority tracking: which compaction system created this summary.
    # Values: "native" (ii-agent ContextWindowManager), "a2a" (CLI backend),
    # or None (legacy rows created before authority tracking).
    summary_authority: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        TimestampColumn, default=lambda: datetime.now(timezone.utc)
    )

    # Indexes
    __table_args__ = (
        Index("idx_summaries_session", "session_id"),
        Index("idx_summaries_end_message", "end_message_id"),
    )
