"""SQLAlchemy models for memory domain."""

import uuid
from typing import Optional

from sqlalchemy import BigInteger, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ii_agent.core.db.base import Base


class UserMemory(Base):
    """Persistent storage for user memories.

    Each record represents a single memory about a user, including:
    - The memory text content
    - Optional topic tags for categorization
    - The original user input that triggered memory creation
    - Association with user and agent
    """

    __tablename__ = "user_memories"

    memory_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    agent_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    memory: Mapped[str] = mapped_column(String, nullable=False)
    topics: Mapped[Optional[list[str]]] = mapped_column(JSONB, nullable=True)
    input: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    __mapper_args__ = {"version_id_col": version}

    __table_args__ = (
        Index("ix_user_memories_user_id", "user_id"),
        Index("ix_user_memories_user_agent", "user_id", "agent_id"),
        Index("ix_user_memories_memory_id", "memory_id", unique=True),
        Index("ix_user_memories_updated_at", "updated_at"),
    )
