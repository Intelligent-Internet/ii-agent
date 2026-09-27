import logging
import time
from datetime import datetime
from typing import Dict, List, Optional
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from pydantic import TypeAdapter

from ii_agent.chat.messages.models import ChatMessage
from ii_agent.chat.messages.repository import ChatMessageRepository
from ii_agent.files.models import SessionAsset

from ii_agent.billing.schemas import TokenUsage
from ii_agent.chat.types import (
    ContentPart,
    Message,
    MessageRole,
)
import tiktoken

logger = logging.getLogger(__name__)


encoding = tiktoken.get_encoding("cl100k_base")


class MessageService:
    """Service for managing chat messages."""

    parts_adapter: TypeAdapter = TypeAdapter(List[ContentPart])

    def __init__(self, *, chat_repo: ChatMessageRepository | None = None) -> None:
        self._repo = chat_repo or ChatMessageRepository()

    async def create_message(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        role: MessageRole,
        model_id: str,
        parts: List[ContentPart],
        parent_message_id: Optional[uuid.UUID] = None,
        usage: TokenUsage | None = None,
        tools: Optional[Dict[str, bool]] = None,
        provider: Optional[str] = None,
        file_ids: List[str] | None = None,
        metadata: Optional[Dict] = None,
        provider_metadata: Optional[Dict] = None,
        finish_reason: Optional[str] = None,
    ) -> Message:
        """Create a new message with ContentParts."""
        now = int(time.time())

        parts_data = self.parts_adapter.dump_python(parts, mode="json")

        # Link files to session via SessionAsset (idempotent)
        if file_ids:
            for file_id in file_ids:
                existing = await db.execute(
                    select(SessionAsset).where(
                        SessionAsset.asset_id == file_id,
                        SessionAsset.session_id == session_id,
                    )
                )
                if not existing.scalar_one_or_none():
                    db.add(SessionAsset(session_id=session_id, asset_id=file_id))

        db_message = ChatMessage(
            session_id=session_id,
            role=role.value,
            content=parts_data,
            model=model_id,
            is_finished=True,
            file_ids=file_ids,
            parent_message_id=parent_message_id,
            tools=tools,
            usage=usage.model_dump() if usage else None,
            tokens=usage.total_tokens if usage else None,
            message_metadata=metadata,
            provider_metadata=provider_metadata,
            finish_reason=finish_reason,
        )
        db_message = await self._repo.create(db, db_message)

        return Message(
            id=db_message.id,
            role=role,
            session_id=session_id,
            parts=parts,
            model=model_id,
            provider=provider,
            created_at=now,
            tokens=db_message.tokens,
            updated_at=now,
            file_ids=file_ids,
            tools_enabled=tools,
            metadata=metadata,
            provider_metadata=provider_metadata,
            finish_reason=finish_reason,
        )

    def _db_message_to_message(self, db_msg: ChatMessage) -> Optional[Message]:
        """Convert a ChatMessage DB row to a Message domain object.

        Returns None for unfinished messages (they are skipped).
        """
        if db_msg.is_finished is False:
            logger.warning(
                f"Skipping unfinished message {db_msg.id} in session {db_msg.session_id}"
            )
            return None

        if isinstance(db_msg.content, dict) and "parts" in db_msg.content:
            parts_data = db_msg.content["parts"]
        elif isinstance(db_msg.content, list):
            parts_data = db_msg.content
        else:
            parts_data = []

        parts = self.parts_adapter.validate_python(parts_data)

        return Message(
            id=db_msg.id,
            role=MessageRole(db_msg.role),
            session_id=db_msg.session_id,
            parts=parts,
            model=db_msg.model,
            tokens=db_msg.tokens,
            created_at=int(db_msg.created_at.timestamp()),
            updated_at=int(db_msg.updated_at.timestamp()),
            file_ids=([str(fid) for fid in db_msg.file_ids] if db_msg.file_ids else None),
            tools_enabled=db_msg.tools,
            metadata=db_msg.message_metadata,
            provider_metadata=db_msg.provider_metadata,
            finish_reason=db_msg.finish_reason,
        )

    async def update_message_parts(
        self,
        db: AsyncSession,
        message_id: uuid.UUID,
        parts: List[ContentPart],
    ) -> None:
        """Persist updated ContentParts for an existing message.

        Used after file processing adds BinaryContent to an already-committed
        user message so that subsequent turns can access image data.
        """
        parts_data = self.parts_adapter.dump_python(parts, mode="json")
        await db.execute(
            update(ChatMessage).where(ChatMessage.id == message_id).values(content=parts_data)
        )
        await db.flush()

    async def list_messages_after_id(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        after_message_id: uuid.UUID,
        limit: int = 1000,
    ) -> List[Message]:
        """List messages after a specific message ID."""
        db_messages = await self._repo.list_after_id(db, session_id, after_message_id, limit)

        messages = []
        for db_msg in db_messages:
            msg = self._db_message_to_message(db_msg)
            if msg is not None:
                messages.append(msg)
        return messages

    async def list_messages_after_timestamp(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        after_timestamp: datetime,
        limit: int = 1000,
    ) -> List[Message]:
        """List messages created after a specific timestamp.

        Used for advanced mode to load only messages created after entering advanced mode.
        """
        db_messages = await self._repo.list_after_timestamp(db, session_id, after_timestamp, limit)

        messages = []
        for db_msg in db_messages:
            msg = self._db_message_to_message(db_msg)
            if msg is not None:
                messages.append(msg)
        return messages

    async def list_by_session(
        self, db: AsyncSession, session_id: uuid.UUID, limit: int = 50
    ) -> List[Message]:
        """List messages for a session."""
        db_messages = await self._repo.list_by_session(db, session_id, limit)

        messages = []
        for db_msg in db_messages:
            msg = self._db_message_to_message(db_msg)
            if msg is not None:
                messages.append(msg)
        return messages

    async def mark_messages_incomplete(
        self,
        db: AsyncSession,
        parent_message_id: uuid.UUID,
    ) -> None:
        """Mark messages as incomplete when errors occur during streaming.

        Marks all children of the parent message as incomplete in one transaction.

        Args:
            parent_message_id: Parent message ID (user message) to mark incomplete
        """
        await self._repo.mark_incomplete(db, parent_message_id)
