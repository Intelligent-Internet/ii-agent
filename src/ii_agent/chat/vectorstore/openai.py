"""OpenAI vector store implementation."""

import logging
import mimetypes
from datetime import datetime, timezone, timedelta
from functools import lru_cache
from typing import Any, Optional
import uuid

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.settings.llm import Provider
from ii_agent.core.db import get_db_session_local
from ii_agent.settings.llm.schemas import ModelConfig
from ii_agent.settings.llm.service import get_system_model_config_from_db
from ii_agent.chat.providers.models import ChatProviderVectorStore
from ii_agent.files.models import FileAsset
from ii_agent.chat.vectorstore.base import (
    VectorStore,
    VectorStoreMetadata,
    VectorStoreFileObject,
)
from ii_agent.core.storage.client import get_storage

logger = logging.getLogger(__name__)


class OpenAIVectorStore(VectorStore):
    """OpenAI vector store implementation."""

    EXPIRES_DAYS = 7
    BUFFER_EXPIRY_MINUTES = 10
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

    def __init__(self) -> None:
        self._llm_config: ModelConfig | None = None
        self._client: AsyncOpenAI | None = None
        self.provider = Provider.OPENAI.value

    async def _get_client(self) -> AsyncOpenAI:
        """Lazy-init the OpenAI client from the DB system config."""
        if self._client is None:
            async with get_db_session_local() as db:
                self._llm_config = await get_system_model_config_from_db(db, model_id="default")
            self._client = AsyncOpenAI(
                api_key=self._llm_config.api_key.get_secret_value()
                if self._llm_config.api_key
                else "",
                base_url=self._llm_config.base_url or None,
            )
        return self._client

    @property
    def llm_config(self) -> ModelConfig:
        """Access LLM config (available after first _get_client call)."""
        if self._llm_config is None:
            raise RuntimeError("LLM config not initialized — call _get_client() first")
        return self._llm_config

    async def retrieve(
        self, user_id: uuid.UUID, session_id: uuid.UUID
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

        client = await self._get_client()
        file_list_stores = await client.vector_stores.files.list(
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

    async def add_file(self, user_id: uuid.UUID, session_id: uuid.UUID, file_id: str) -> int:
        """
        Add a file to the user's vector store.

        Args:
            user_id: The user's ID
            session_id: The session ID
            file_id: FileAsset ID to read from storage and upload to vector store

        Returns:
            True if successful, False otherwise
        """
        try:
            async with get_db_session_local() as db_session:
                vector_store = await self._get_or_create_vector_store(db_session, user_id)
                result = await db_session.execute(select(FileAsset).where(FileAsset.id == file_id))
                file_upload = result.scalar_one_or_none()

            if not file_upload:
                logger.error(f"File {file_id} not found in database")
                return 0

            # Read file from storage
            file_content = await get_storage().read(file_upload.storage_path)
            if not file_content:
                logger.error(f"Failed to read file {file_id} from storage")
                return False
                # Upload to OpenAI Files API

            client = await self._get_client()
            openai_file = await client.files.create(
                file=(file_upload.file_name, file_content),
                purpose="assistants",
            )

            # Upload file directly to vector store with attributes
            vector_store_file = await client.vector_stores.files.create_and_poll(
                vector_store_id=vector_store.vector_store_id,
                file_id=openai_file.id,
                attributes={
                    "user_id": str(user_id),
                    "session_id": str(session_id),
                    "date": datetime.utcnow().timestamp(),
                },
                poll_interval_ms=100,
            )

            logger.info(
                f"Added file {file_id} (OpenAI: {vector_store_file.id}) to vector store for user {user_id}"
            )
            return 1

        except Exception as e:
            logger.error(f"Failed to add file {file_id} to vector store for user {user_id}: {e}")
            return 0

    async def add_files_batch(
        self,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        file_ids: list[str],
    ) -> list[VectorStoreFileObject]:
        """
        Add multiple files to the user's vector store in a batch.

        Args:
            user_id: The user's ID
            session_id: The session ID
            file_ids: List of FileAsset IDs to read from storage and upload to vector store

        Returns:
            List of VectorStoreFileObject with file metadata
        """
        try:
            file_uploads = []
            async with get_db_session_local() as db_session:
                # Get or create vector store first
                vector_store = await self._get_or_create_vector_store(db_session, user_id)

                # Get all file upload records from database in one query
                result = await db_session.execute(
                    select(FileAsset).where(FileAsset.id.in_(file_ids))
                )
                file_uploads = result.scalars().all()

            if not file_uploads:
                logger.error("No files found in database")
                return []

            # Upload files to OpenAI Files API first and track metadata
            uploaded_files = []
            openai_file_ids = []
            for file_upload in file_uploads:
                # Guess MIME type from file name
                guessed_mime_type = mimetypes.guess_type(file_upload.file_name)[0]

                # Validate MIME type - only support PDF, plain text, MD, PPT
                if guessed_mime_type not in self.VALID_MIME_TYPES:
                    logger.warning(
                        f"File {file_upload.id} ({file_upload.file_name}) has unsupported MIME type {guessed_mime_type}, skipping"
                    )
                    continue

                # Read file from storage
                file_content = await get_storage().read(file_upload.storage_path)
                if not file_content:
                    logger.warning(f"Failed to read file {file_upload.id} from storage, skipping")
                    continue

                # Upload to OpenAI Files API
                client = await self._get_client()
                openai_file = await client.files.create(
                    file=(file_upload.file_name, file_content),
                    purpose="assistants",
                )
                openai_file_ids.append(openai_file.id)

                # Track uploaded file metadata
                uploaded_files.append(
                    {
                        "openai_file_id": openai_file.id,
                        "file_name": file_upload.file_name,
                        "content_type": guessed_mime_type,
                        "bytes": file_upload.file_size,
                    }
                )

            if not openai_file_ids:
                logger.debug("No files were successfully uploaded to OpenAI")
                return []
            # Create batch with file IDs and attributes, then poll for completion
            client = await self._get_client()
            batch = await client.vector_stores.file_batches.create(
                vector_store_id=vector_store.vector_store_id,
                files=[
                    {
                        "file_id": f["openai_file_id"],
                        "attributes": {
                            "user_id": str(user_id),
                            "session_id": str(session_id),
                            "file_name": f["file_name"],
                            "content_type": f["content_type"],
                            "date": datetime.now(timezone.utc).timestamp(),
                        },
                    }
                    for f in uploaded_files
                ],
            )

            batch = await client.vector_stores.file_batches.poll(
                batch_id=batch.id,
                vector_store_id=vector_store.vector_store_id,
                poll_interval_ms=100,
            )

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
            logger.error(f"Failed to add files batch to vector store for user {user_id}: {e}")
            return []

    async def delete(
        self, db_session: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID
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
            client = await self._get_client()
            await client.vector_stores.delete(vector_store.vector_store_id)
            logger.info(f"Deleted vector store from provider for user {user_id}")
        except Exception as e:
            logger.warning(f"Failed to delete vector store from provider (may not exist): {e}")

        # Delete from database
        await db_session.delete(vector_store)
        await db_session.commit()

        logger.info(f"Deleted vector store from database for user {user_id}")
        return True

    async def search(
        self, user_id: uuid.UUID, session_id: uuid.UUID, query: str
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
                vector_store = await self._get_or_create_vector_store(db_session, user_id)

            # Use OpenAI Responses API with file_search tool
            client = await self._get_client()
            response = await client.responses.create(
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

            logger.info(f"Search completed for user {user_id}, found {len(results)} results")
            return results

        except Exception as e:
            logger.error(f"Failed to search vector store for user {user_id}: {e}")
            return []

    async def _get_or_create_vector_store(
        self, db_session: AsyncSession, user_id: uuid.UUID
    ) -> ChatProviderVectorStore:
        vector_store = await self._get_vector_store_from_db(db_session, user_id)
        now = datetime.now(timezone.utc)

        # Check if vector store exists and is not expired
        if vector_store:
            should_check_expired = await self._is_vector_store_expired(vector_store)
            if not should_check_expired:
                return vector_store
            else:
                # Check if vector store still exists on provider side
                is_expired = await self._check_vector_store_expired_on_provider(
                    vector_store.vector_store_id
                )

                if not is_expired:
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
            await db_session.refresh(vector_store)
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
        self, db_session: AsyncSession, user_id: uuid.UUID
    ) -> Optional[ChatProviderVectorStore]:
        """Get vector store from database for a specific user."""
        result = await db_session.execute(
            select(ChatProviderVectorStore).where(
                ChatProviderVectorStore.user_id == user_id,
                ChatProviderVectorStore.provider == self.provider,
            )
        )
        return result.scalar_one_or_none()

    async def _is_vector_store_expired(self, vector_store: ChatProviderVectorStore) -> bool:
        """Check if vector store has expired."""
        if vector_store.expires_at is None:
            return False

        now = datetime.now(timezone.utc)
        return now >= vector_store.expires_at - timedelta(minutes=self.BUFFER_EXPIRY_MINUTES)

    async def _check_vector_store_expired_on_provider(self, vector_store_id: str) -> bool:
        """Check if vector store is expired or about to expire on OpenAI."""
        try:
            client = await self._get_client()
            vector_store = await client.vector_stores.retrieve(vector_store_id)

            # Check if already marked as expired
            if vector_store.status == "expired":
                logger.info(f"Vector store {vector_store_id} status is 'expired'")
                return True

            # Check if about to expire (within 10 minutes buffer)
            if vector_store.expires_at:
                # OpenAI returns Unix timestamp (integer seconds since epoch)
                expires_at = datetime.fromtimestamp(vector_store.expires_at, tz=timezone.utc)
                buffer = timedelta(minutes=self.BUFFER_EXPIRY_MINUTES)
                now = datetime.now(timezone.utc)

                if now >= expires_at - buffer:
                    logger.info(
                        f"Vector store {vector_store_id} will expire at {expires_at}, "
                        f"current time {now} is within 10-minute buffer"
                    )
                    return True

            return False
        except Exception as e:
            logger.warning(f"Vector store {vector_store_id} not found on provider: {e}")
            # If we can't retrieve it, treat as expired so a new one will be created
            return True

    async def _create_vector_store_on_provider(self, user_id: uuid.UUID) -> Any:
        """Create a new vector store on OpenAI."""
        try:
            # Create vector store with a name
            client = await self._get_client()
            vector_store = await client.vector_stores.create(
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
        user_id: uuid.UUID,
        vector_store_id: str,
        raw_vector_object: dict,
    ) -> ChatProviderVectorStore:
        """Save vector store information to database."""
        try:
            # Calculate expiration date (7 days from now)
            expires_at = datetime.now(timezone.utc) + timedelta(days=self.EXPIRES_DAYS)

            # Create database record
            db_vector_store = ChatProviderVectorStore(
                id=uuid.uuid4(),
                user_id=user_id,
                provider=self.provider,
                vector_store_id=vector_store_id,
                raw_vector_object=raw_vector_object,
                expires_at=expires_at,
            )

            db_session.add(db_vector_store)
            await db_session.commit()

            logger.info(f"Saved vector store {vector_store_id} to database for user {user_id}")
            return db_vector_store
        except Exception as e:
            logger.error(f"Failed to save vector store {vector_store_id} to database: {e}")
            await db_session.rollback()
            raise


@lru_cache(maxsize=1)
def get_openai_vector_store() -> OpenAIVectorStore:
    """Return a lazily-created singleton ``OpenAIVectorStore``."""
    return OpenAIVectorStore()
