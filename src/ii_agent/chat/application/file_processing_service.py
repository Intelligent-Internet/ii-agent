"""Chat file processing service for handling file uploads in messages."""

from __future__ import annotations

import logging
import uuid
from typing import Optional, Any, TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.core.config.settings import Settings
from ii_agent.core.storage.client import get_storage
from ii_agent.chat.types import TextContent
from ii_agent.chat.application.file_processor import process_files_for_message
from ii_agent.chat.vectorstore import get_openai_vector_store

if TYPE_CHECKING:
    from ii_agent.chat.types import Message

logger = logging.getLogger(__name__)


class ChatFileProcessor:
    """Service for processing file uploads in chat messages."""

    def __init__(self, *, config: Settings) -> None:
        self._config = config

    async def process_uploads(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        user_message: "Message",
        llm_content: str,
        display_content: str,
    ) -> Optional[Any]:
        """Process file uploads: binary/text to message parts, large files to vector store.

        Mutates user_message.parts in place. Returns the vector store if created.
        """
        vector_store = None
        file_info_lines = ["Files uploaded:"]

        if user_message.file_ids:
            processed_files = await process_files_for_message(
                db_session=db,
                file_ids=user_message.file_ids,
                storage=get_storage(),
                session_id=session_id,
                user_id=user_id,
            )

            if processed_files.binary_parts:
                user_message.parts.extend(processed_files.binary_parts)
                logger.debug(
                    f"[MESSAGE] Added {len(processed_files.binary_parts)} binary file(s) to message"
                )
                file_info_lines.append(
                    f"\n✓ {len(processed_files.binary_parts)} image/PDF file(s) - attached in messages"
                )

            if processed_files.text_parts:
                logger.debug(
                    f"[MESSAGE] Added {len(processed_files.text_parts)} text file(s) to message"
                )
                file_info_lines.append(
                    f"\n✓ {len(processed_files.text_parts)} text file(s) - content extracted"
                )

            if processed_files.large_file_ids:
                logger.debug(
                    f"[VECTOR_STORE] Processing {len(processed_files.large_file_ids)} large file(s) for FileSearchTool"
                )
                openai_vector_store = get_openai_vector_store()
                vector_store = await openai_vector_store.retrieve(
                    user_id=user_id, session_id=session_id
                )
                vs_files = await openai_vector_store.add_files_batch(
                    user_id=user_id,
                    session_id=session_id,
                    file_ids=list(processed_files.large_file_ids),
                )
                logger.debug(
                    f"[VECTOR_STORE] Successfully added {len(vs_files)} large file(s) to vector store"
                )
                file_info_lines.append(
                    f"\n✓ {len(processed_files.large_file_ids)} large file(s) - in vector store for search:"
                )
                for info in processed_files.large_file_info:
                    file_info_lines.append(f"  - {info['file_name']} ({info['size_kb']}KB)")

            if processed_files.skipped_files:
                file_info_lines.append(f"\n⚠ {len(processed_files.skipped_files)} file(s) skipped:")
                for skipped in processed_files.skipped_files:
                    file_info_lines.append(f"  - {skipped['file_name']}: {skipped['reason']}")

            extracted_text = "".join(part.text for part in processed_files.text_parts)
            file_info_text = llm_content + extracted_text + "\n\n" + "\n".join(file_info_lines)
            user_message.parts[0] = TextContent(text=file_info_text)
        else:
            logger.debug("[FILE_PROCESSING] No files to process")
            if llm_content != display_content:
                user_message.parts[0] = TextContent(text=llm_content)

        return vector_store
