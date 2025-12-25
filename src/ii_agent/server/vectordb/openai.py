"""OpenAI vector store implementation."""

import hashlib
import logging
import mimetypes
from datetime import datetime, timezone, timedelta
from typing import Any, Optional
import uuid

import anyio
from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.core.config.llm_config import APITypes
from ii_agent.db.manager import get_db_session_local
from ii_agent.server.llm_settings.service import get_system_llm_config
from ii_agent.db.llm_provider import ProviderVectorStore
from ii_agent.db.models import FileUpload
from ii_agent.server.vectordb.base import (
    VectorStore,
    VectorStoreMetadata,
    VectorStoreFileObject,
)
from ii_agent.server.shared import storage

logger = logging.getLogger(__name__)


class OpenAIVectorStore(VectorStore):
    """OpenAI vector store implementation."""

    EXPIRES_DAYS = 7

    # Valid MIME types for batch file uploads (PDF, plain text, MD, DOC, PPT)
    VALID_MIME_TYPES = [
        "application/pdf",
        "text/plain",
        "text/markdown",
        "text/md",
        "application/msword",  # .doc
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
        "application/vnd.ms-powerpoint",  # .ppt
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",  # .pptx
    ]

    def __init__(self):
        self.llm_config = get_system_llm_config(model_id="default")
        self.provider = APITypes.OPENAI.value

        # Initialize OpenAI client
        self.client = AsyncOpenAI(
            api_key=self.llm_config.api_key.get_secret_value(),
            base_url=self.llm_config.base_url if self.llm_config.base_url else None,
        )

    async def retrieve(
        self, user_id: str, session_id: str
    ) -> Optional[VectorStoreMetadata]:
        """
        Retrieve vector store metadata for a user session.

        Args:
            db_session: Database session
            user_id: The user's ID
            session_id: The session ID

        Returns:
            VectorStoreMetadata object or None if not found
        """
        # Try to get existing vector store from database
        async with get_db_session_local() as db_session:
            vector_store = await self._get_or_create_vector_store(db_session, user_id)
            await db_session.commit()

        file_list_stores = await self.client.vector_stores.files.list(
            vector_store_id=vector_store.vector_store_id, limit=50, order="desc"
        )
        # Return generic metadata as Pydantic model
        return VectorStoreMetadata(
            provider_store_id=str(vector_store.vector_store_id),
            user_id=vector_store.user_id,
            provider=vector_store.provider,
            created_at=vector_store.created_at,
            updated_at=vector_store.updated_at,
            expires_at=vector_store.expires_at,
            files=file_list_stores.model_dump(),
        )

    async def add_file(self, user_id: str, session_id: str, file_id: str) -> int:
        """
        Add a file to the user's vector store.

        Args:
            user_id: The user's ID
            session_id: The session ID
            file_id: FileUpload ID to read from storage and upload to vector store

        Returns:
            True if successful, False otherwise
        """
        try:
            async with get_db_session_local() as db_session:
                vector_store = await self._get_or_create_vector_store(
                    db_session, user_id
                )
                result = await db_session.execute(
                    select(FileUpload).where(FileUpload.id == file_id)
                )
                file_upload = result.scalar_one_or_none()

            if not file_upload:
                logger.error(f"File {file_id} not found in database")
                return 0

            # Read file from storage (blocking operation, run in thread)
            file_content = await anyio.to_thread.run_sync(
                storage.read, file_upload.storage_path
            )
            if not file_content:
                logger.error(f"Failed to read file {file_id} from storage")
                return False
                # Upload to OpenAI Files API

            openai_file = await self.client.files.create(
                file=(file_upload.file_name, file_content),
                purpose="assistants",
            )

            # Upload file directly to vector store with attributes
            vector_store_file = await self.client.vector_stores.files.create_and_poll(
                vector_store_id=vector_store.vector_store_id,
                file_id=openai_file.id,
                attributes={
                    "user_id": user_id,
                    "session_id": session_id,
                    "date": datetime.utcnow().timestamp(),
                },
                poll_interval_ms=100,
            )

            logger.info(
                f"Added file {file_id} (OpenAI: {vector_store_file.id}) to vector store for user {user_id}"
            )
            return 1

        except Exception as e:
            logger.error(
                f"Failed to add file {file_id} to vector store for user {user_id}: {e}"
            )
            return 0

    async def add_files_batch(
        self,
        user_id: str,
        session_id: str,
        file_ids: list[str],
    ) -> list[VectorStoreFileObject]:
        """
        Add multiple files to the user's vector store in a batch.
        Skips files that already exist in the vector store (based on content hash).

        Args:
            user_id: The user's ID
            session_id: The session ID
            file_ids: List of FileUpload IDs to read from storage and upload to vector store

        Returns:
            List of VectorStoreFileObject with file metadata
        """
        try:
            file_uploads = []
            async with get_db_session_local() as db_session:
                # Get or create vector store first
                vector_store = await self._get_or_create_vector_store(
                    db_session, user_id
                )

                # Get all file upload records from database in one query
                result = await db_session.execute(
                    select(FileUpload).where(FileUpload.id.in_(file_ids))
                )
                file_uploads = result.scalars().all()

            if not file_uploads:
                logger.error("No files found in database")
                return []

            # Get existing files in vector store to check for duplicates
            existing_files = await self.client.vector_stores.files.list(
                vector_store_id=vector_store.vector_store_id, limit=100, order="desc"
            )

            # Build set of existing content hashes for deduplication
            existing_hashes = set()
            for f in existing_files.data:
                if f.attributes and f.attributes.get("content_hash"):
                    existing_hashes.add(f.attributes["content_hash"])

            # Upload files to OpenAI Files API first and track metadata
            uploaded_files = []
            openai_file_ids = []
            skipped_count = 0

            for file_upload in file_uploads:
                # Guess MIME type from file name
                guessed_mime_type = mimetypes.guess_type(file_upload.file_name)[0]

                # Validate MIME type - only support PDF, plain text, MD, PPT
                if guessed_mime_type not in self.VALID_MIME_TYPES:
                    logger.warning(
                        f"File {file_upload.id} ({file_upload.file_name}) has unsupported MIME type {guessed_mime_type}, skipping"
                    )
                    continue

                # Read file from storage (blocking operation, run in thread)
                # storage.read returns a BinaryIO file-like object, we need to read the bytes
                file_io = await anyio.to_thread.run_sync(
                    storage.read, file_upload.storage_path
                )
                if not file_io:
                    logger.warning(
                        f"Failed to read file {file_upload.id} from storage, skipping"
                    )
                    continue

                # Read bytes from the file-like object
                file_content = file_io.read()

                # Compute content hash for deduplication
                content_hash = hashlib.sha256(file_content).hexdigest()[:16]

                # Check if file with same content already exists
                if content_hash in existing_hashes:
                    logger.info(
                        f"Skipping duplicate file {file_upload.file_name} (hash: {content_hash})"
                    )
                    skipped_count += 1
                    continue

                # Upload to OpenAI Files API
                openai_file = await self.client.files.create(
                    file=(file_upload.file_name, file_content),
                    purpose="assistants",
                )
                openai_file_ids.append(openai_file.id)

                # Track uploaded file metadata (include content_hash for future dedup)
                uploaded_files.append(
                    {
                        "openai_file_id": openai_file.id,
                        "file_name": file_upload.file_name,
                        "content_type": guessed_mime_type,
                        "bytes": file_upload.file_size,
                        "content_hash": content_hash,
                    }
                )

                # Add to existing hashes to handle duplicates within same batch
                existing_hashes.add(content_hash)

            if skipped_count > 0:
                logger.info(f"Skipped {skipped_count} duplicate file(s)")

            if not openai_file_ids:
                logger.debug("No new files to upload to OpenAI (all duplicates or errors)")
                return []

            logger.info(f"Creating batch for {len(openai_file_ids)} files in vector store {vector_store.vector_store_id}")
            # Create batch with file IDs and attributes
            batch = await self.client.vector_stores.file_batches.create(
                vector_store_id=vector_store.vector_store_id,
                files=[
                    {
                        "file_id": f["openai_file_id"],
                        "attributes": {
                            "user_id": user_id,
                            "session_id": session_id,
                            "file_name": f["file_name"],
                            "content_type": f["content_type"],
                            "content_hash": f["content_hash"],
                            "date": datetime.now(timezone.utc).timestamp(),
                        },
                    }
                    for f in uploaded_files
                ],
            )

            logger.info(f"Batch created: {batch.id}, status: {batch.status}")

            # Don't poll for completion - files will be searchable once processed by OpenAI
            # Polling can take a long time (30+ seconds) for large PDFs and blocks the chat
            # The file_search tool will still work once OpenAI finishes processing in the background

            logger.info(
                 f"Added {len(openai_file_ids)} files to vector store for user {user_id} (batch: {batch.id})"
            )

            # Return list of VectorStoreFileObject
            return [
                VectorStoreFileObject(
                    id=file["openai_file_id"],
                    file_name=file["file_name"],
                    content_type=file["content_type"],
                    bytes=file["bytes"],
                )
                for file in uploaded_files
            ]

        except Exception as e:
            logger.error(
                f"Failed to add files batch to vector store for user {user_id}: {e}"
            )
            return []

    async def delete(
        self, db_session: AsyncSession, user_id: str, session_id: str
    ) -> bool:
        """
        Delete vector store for a user session.

        Args:
            db_session: Database session
            user_id: The user's ID
            session_id: The session ID

        Returns:
            True if deleted, False if not found
        """
        # Get vector store from database
        vector_store = await self._get_vector_store_from_db(db_session, user_id)

        if not vector_store:
            logger.warning(f"No vector store found for user {user_id}")
            return False

        # Delete from provider
        try:
            await self.client.vector_stores.delete(vector_store.vector_store_id)
            logger.info(f"Deleted vector store from provider for user {user_id}")
        except Exception as e:
            logger.warning(
                f"Failed to delete vector store from provider (may not exist): {e}"
            )

        # Delete from database
        await db_session.delete(vector_store)
        await db_session.commit()

        logger.info(f"Deleted vector store from database for user {user_id}")
        return True

    async def search(
        self, user_id: str, session_id: str, query: str
    ) -> list[dict[str, Any]]:
        """
        Search through vector store using a query.

        Args:
            db_session: Database session
            user_id: The user's ID
            session_id: The session ID
            query: Search query string

        Returns:
            List of search results with content, score, and metadata
        """
        try:
            async with get_db_session_local() as db_session:
                # Get or create vector store
                vector_store = await self._get_or_create_vector_store(
                    db_session, user_id
                )

            # Use OpenAI Responses API with file_search tool
            response = await self.client.responses.create(
                model=self.llm_config.model,
                tools=[
                    {
                        "type": "file_search",
                        "vector_store_ids": [vector_store.vector_store_id],
                        "max_num_results": 20,
                    }
                ],
                instructions="You are a search assistant. Return relevant information from the documents based on the query.",
                input=[
                    {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": query}],
                    }
                ],
            )

            # Extract search results
            results = []
            for item in response.output:
                if hasattr(item, "content"):
                    for content_part in item.content:
                        if hasattr(content_part, "text"):
                            result = {
                                "content": content_part.text,
                                "score": None,  # OpenAI doesn't provide scores directly
                                "metadata": {},
                            }

                            # Extract citations/annotations if available
                            if hasattr(content_part, "annotations"):
                                citations = []
                                for annotation in content_part.annotations:
                                    if hasattr(annotation, "file_citation"):
                                        citations.append(
                                            {
                                                "file_id": annotation.file_citation.file_id,
                                                "quote": getattr(
                                                    annotation.file_citation,
                                                    "quote",
                                                    None,
                                                ),
                                            }
                                        )
                                if citations:
                                    result["metadata"]["citations"] = citations

                            results.append(result)

            logger.info(
                f"Search completed for user {user_id}, found {len(results)} results"
            )
            return results

        except Exception as e:
            logger.error(f"Failed to search vector store for user {user_id}: {e}")
            return []

    async def _get_or_create_vector_store(
        self, db_session: AsyncSession, user_id: str
    ) -> ProviderVectorStore:
        vector_store = await self._get_vector_store_from_db(db_session, user_id)
        now = datetime.now(timezone.utc)

        # Check if vector store exists and is not expired
        if vector_store:
            should_check_expired = await self._is_vector_store_expired(vector_store)
            if not should_check_expired:
                return vector_store
            else:
                # Check if vector store still exists on provider side
                exists = await self._check_vector_store_exists_on_provider(
                    vector_store.vector_store_id
                )

                if exists:
                    logger.info(f"Using existing vector store for user {user_id}")
                    return vector_store

            # Vector store expired or doesn't exist on provider, create new one and update record
            logger.info(
                f"Vector store is expired or doesn't exist, creating new one for user {user_id}"
            )
            new_vector_store = await self._create_vector_store_on_provider(user_id)
            vector_store.vector_store_id = new_vector_store.id
            vector_store.raw_vector_object = new_vector_store.model_dump()
            vector_store.expires_at = now + timedelta(days=self.EXPIRES_DAYS)
            vector_store.updated_at = now
            await db_session.commit()
            return vector_store

        # Create new vector store
        logger.info(f"Creating new vector store for user {user_id}")
        new_vector_store = await self._create_vector_store_on_provider(user_id)

        # Store in database
        vector_store = await self._save_vector_store_to_db(
            db_session, user_id, new_vector_store.id, new_vector_store.model_dump()
        )

        return vector_store

    async def _get_vector_store_from_db(
        self, db_session: AsyncSession, user_id: str
    ) -> Optional[ProviderVectorStore]:
        """Get vector store from database for a specific user."""
        result = await db_session.execute(
            select(ProviderVectorStore).where(
                ProviderVectorStore.user_id == user_id,
                ProviderVectorStore.provider == self.provider,
            )
        )
        return result.scalar_one_or_none()

    async def _is_vector_store_expired(self, vector_store: ProviderVectorStore) -> bool:
        """Check if vector store has expired."""
        if vector_store.expires_at is None:
            return False

        now = datetime.now(timezone.utc)
        return now >= vector_store.expires_at

    async def _check_vector_store_exists_on_provider(
        self, vector_store_id: str
    ) -> bool:
        """Check if vector store still exists on OpenAI."""
        try:
            vector_store = await self.client.vector_stores.retrieve(vector_store_id)
            return vector_store.status != "expired"
        except Exception as e:
            logger.warning(f"Vector store {vector_store_id} not found on provider: {e}")
            return False

    async def _create_vector_store_on_provider(self, user_id: str) -> Any:
        """Create a new vector store on OpenAI."""
        try:
            # Create vector store with a name
            vector_store = await self.client.vector_stores.create(
                name=f"vs_{user_id}",
                expires_after={
                    "anchor": "last_active_at",
                    "days": self.EXPIRES_DAYS,  # Auto-expire after 7 days of inactivity
                },
            )

            logger.info(f"Created vector store {vector_store.id} for user {user_id}")
            return vector_store
        except Exception as e:
            logger.error(f"Failed to create vector store for user {user_id}: {e}")
            raise

    async def _save_vector_store_to_db(
        self,
        db_session: AsyncSession,
        user_id: str,
        vector_store_id: str,
        raw_vector_object: dict,
    ) -> ProviderVectorStore:
        """Save vector store information to database."""
        try:
            # Calculate expiration date (7 days from now)
            expires_at = datetime.now(timezone.utc) + timedelta(days=self.EXPIRES_DAYS)

            # Create database record
            db_vector_store = ProviderVectorStore(
                id=uuid.uuid4(),
                user_id=user_id,
                provider=self.provider,
                vector_store_id=vector_store_id,
                raw_vector_object=raw_vector_object,
                expires_at=expires_at,
            )

            db_session.add(db_vector_store)
            await db_session.commit()

            logger.info(
                f"Saved vector store {vector_store_id} to database for user {user_id}"
            )
            return db_vector_store
        except Exception as e:
            logger.error(
                f"Failed to save vector store {vector_store_id} to database: {e}"
            )
            await db_session.rollback()
            raise


openai_vector_store = OpenAIVectorStore()
