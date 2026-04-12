"""Unified service layer for files domain.

Merges the old FileService and AssetService into a single service.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator, Optional

from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.core.config.settings import Settings
from ii_agent.core.storage.path_resolver import path_resolver
from ii_agent.core.storage.service import StorageService
from ii_agent.files.exceptions import (
    FileAccessDeniedError,
    FileSizeLimitExceededError,
    FileUploadNotFoundError,
)
from ii_agent.files.models import AssetSource, AssetType, FileAsset, UploadStatus
from ii_agent.files.repository import FileRepository
from ii_agent.files.schemas import (
    FileDataResponse,
    GenerateDownloadUrlsResponse,
    GenerateUploadUrlResponse,
    MediaLibraryItem,
    MediaLibraryResponse,
    PublishResponse,
    UploadCompleteResponse,
)
from ii_agent.files.media import File as MediaFile, Image as MediaImage
from ii_agent.sessions.exceptions import SessionNotFoundError
from ii_agent.sessions.repository import SessionRepository

# Constants
SEVEN_DAY_SECONDS = 7 * 24 * 3600
# Re-generate signed URL 2 hours before it actually expires so clients
# always receive a URL that is usable for a reasonable window.
SIGNED_URL_BUFFER_SECONDS = 2 * 3600


class FileService:
    """Unified service for managing file assets."""

    def __init__(
        self,
        *,
        file_repo: FileRepository,
        session_repo: SessionRepository,
        storage: StorageService,
        config: Settings,
    ) -> None:
        self._config = config
        self._file_repo = file_repo
        self._session_repo = session_repo
        self._storage = storage

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_signed_url_valid(asset: FileAsset) -> bool:
        """Check if the cached signed URL is still usable."""
        if not asset.signed_url or not asset.signed_url_expires_at:
            return False
        now = datetime.now(timezone.utc)
        expires = asset.signed_url_expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return (expires - now).total_seconds() > SIGNED_URL_BUFFER_SECONDS

    async def _get_file_url(
        self,
        asset: FileAsset,
        db: AsyncSession | None = None,
    ) -> str | None:
        """Return a usable URL for the asset, using the cached signed URL when valid."""
        storage_path = asset.storage_path
        if not storage_path:
            return None
        if storage_path.startswith(("http://", "https://")):
            return storage_path

        # Use cached signed URL if still valid
        if self._is_signed_url_valid(asset):
            return asset.signed_url

        # Generate a fresh signed URL using configured TTL
        ttl_seconds = self._config.storage.signed_url_ttl_seconds
        signed_url = await self._storage.signed_url(storage_path, expiry_seconds=ttl_seconds)
        if signed_url and db is not None:
            asset.signed_url = signed_url
            asset.signed_url_expires_at = datetime.now(timezone.utc) + timedelta(
                seconds=ttl_seconds
            )
            await db.flush()
        return signed_url

    async def _to_file_data(
        self, asset: FileAsset, db: AsyncSession | None = None
    ) -> FileDataResponse:
        """Convert a FileAsset model to FileDataResponse."""
        return FileDataResponse(
            id=asset.id,
            name=asset.file_name,
            size=asset.file_size,
            content_type=asset.content_type,
            storage_path=asset.storage_path,
            url=await self._get_file_url(asset, db),
            asset_type=asset.asset_type,
            source=asset.source,
            upload_status=asset.upload_status,
            is_public=asset.is_public,
            sandbox_path=asset.sandbox_path,
            created_at=asset.created_at,
        )

    # ==================== File CRUD ====================

    async def get_file_by_id(self, db: AsyncSession, file_id: uuid.UUID) -> FileDataResponse:
        """Get file by ID and return FileDataResponse."""
        asset = await self._file_repo.get_by_id(db, file_id)
        if not asset:
            raise FileUploadNotFoundError(file_id)
        return await self._to_file_data(asset, db)

    async def get_files_by_session_id(
        self, db: AsyncSession, session_id: uuid.UUID
    ) -> list[FileDataResponse]:
        """Get all files linked to a session."""
        assets = await self._file_repo.get_by_session_id(db, session_id)
        return [await self._to_file_data(a, db) for a in assets]

    async def link_file_to_session(
        self, db: AsyncSession, file_id: uuid.UUID, session_id: uuid.UUID
    ) -> bool:
        """Link a file to a session via SessionAsset."""
        asset = await self._file_repo.get_by_id(db, file_id)
        if not asset:
            return False
        await self._file_repo.link_to_session(db, file_id, session_id)
        return True

    async def create_file_record(
        self,
        db: AsyncSession,
        *,
        file_id: uuid.UUID,
        file_name: str,
        file_size: int,
        storage_path: str,
        content_type: str,
        session_id: uuid.UUID,
    ) -> FileAsset:
        """Create a file record, resolving user_id from session_id.

        Convenience method for callers that don't have user_id available.
        Also links the file to the session via SessionAsset.
        """
        session = await self._session_repo.get_by_id(db, session_id)
        if not session:
            raise SessionNotFoundError(f"Session {session_id} not found")

        asset = await self._file_repo.create_asset(
            db,
            file_id=file_id,
            user_id=session.user_id,
            file_name=file_name,
            storage_path=storage_path,
            content_type=content_type,
            file_size=file_size,
            asset_type=AssetType.from_content_type(content_type),
            source=AssetSource.GENERATED,
            upload_status=UploadStatus.COMPLETE,
        )
        await self._file_repo.link_to_session(db, file_id, session_id)
        return asset

    async def write_file_from_url(
        self,
        db: AsyncSession,
        *,
        url: str,
        file_name: str,
        file_size: int,
        content_type: str,
        session_id: uuid.UUID,
        user_id: Optional[uuid.UUID] = None,
    ) -> FileDataResponse:
        """Write file from URL to storage and create database record."""
        if not user_id:
            session = await self._session_repo.get_by_id(db, session_id)
            if not session:
                raise SessionNotFoundError(f"Session {session_id} not found")
            user_id = session.user_id

        file_id = uuid.uuid4()
        ext = os.path.splitext(file_name)[1].lstrip(".") or "bin"
        asset_type = AssetType.from_content_type(content_type)
        storage_path = path_resolver.user_file(str(user_id), asset_type, str(file_id), ext)

        asset = await self._file_repo.create_asset(
            db,
            file_id=file_id,
            user_id=user_id,
            file_name=file_name,
            storage_path=storage_path,
            content_type=content_type,
            file_size=file_size,
            asset_type=asset_type,
            source=AssetSource.GENERATED,
        )
        await self._file_repo.link_to_session(db, file_id, session_id)
        await self._storage.write_from_url(url, storage_path, content_type)

        return await self._to_file_data(asset, db)

    # ==================== URL Resolution ====================

    async def resolve_signed_urls(
        self,
        db: AsyncSession,
        file_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, str]:
        """Return a mapping of file_id → fresh signed URL for the given IDs.

        Skips IDs that don't exist or have no storage path.
        Caches the newly generated URLs on the FileAsset rows.
        """
        if not file_ids:
            return {}

        assets = await self._file_repo.get_by_ids(db, file_ids)
        result: dict[uuid.UUID, str] = {}
        for asset in assets:
            url = await self._get_file_url(asset, db)
            if url:
                result[asset.id] = url
        return result

    async def resolve_signed_url_by_path(
        self,
        db: AsyncSession,
        storage_path: str,
    ) -> str | None:
        """Return a fresh signed URL for an asset identified by its storage path.

        Looks up the FileAsset row, then uses the standard caching logic in
        ``_get_file_url`` so the signed URL is persisted back to the DB.
        Falls back to a direct storage call if no matching asset exists.
        """
        if not storage_path:
            return None
        if storage_path.startswith(("http://", "https://")):
            return storage_path

        asset = await self._file_repo.get_by_storage_path(db, storage_path)
        if asset:
            return await self._get_file_url(asset, db)

        # No asset row — generate without caching
        return await self._storage.signed_url(
            storage_path,
            expiry_seconds=self._config.storage.signed_url_ttl_seconds,
        )

    # ==================== Agent File Helpers ====================

    async def get_files_by_ids_and_update_session(
        self,
        db: AsyncSession,
        *,
        file_ids: list[uuid.UUID],
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        expiration_seconds: int = SEVEN_DAY_SECONDS,
    ) -> list[FileDataResponse]:
        """Fetch files by IDs, link them to the session, and return with signed URLs."""
        results: list[FileDataResponse] = []
        for file_id in file_ids:
            asset = await self._file_repo.get_by_id(db, file_id)
            if not asset:
                continue
            await self._file_repo.link_to_session(db, file_id, session_id)
            results.append(await self._to_file_data(asset, db))
        return results

    async def prepare_agent_files(
        self,
        db: AsyncSession,
        *,
        file_ids: list[uuid.UUID],
        user_id: uuid.UUID,
        session_id: uuid.UUID,
    ) -> tuple[list[MediaImage], list[MediaFile]]:
        """Fetch files by IDs and separate into images and generic files.

        Returns ``(images, files)`` with typed media objects.
        """
        files_data = await self.get_files_by_ids_and_update_session(
            db, file_ids=file_ids, user_id=user_id, session_id=session_id
        )

        images: list[MediaImage] = []
        files: list[MediaFile] = []

        for file_data in files_data:
            if not file_data.url:
                continue

            files.append(
                MediaFile(
                    id=str(file_data.id),
                    url=file_data.url,
                    filename=file_data.name,
                )
            )

            # Detect images via centralized AssetType detection
            detected = AssetType.from_content_type(file_data.content_type)
            mime_type = file_data.content_type
            if not detected.is_image and file_data.name:
                ext = file_data.name.rsplit(".", 1)[-1].lower() if "." in file_data.name else ""
                detected = AssetType.from_ext(ext)
                if detected.is_image and (not mime_type or mime_type == "application/octet-stream"):
                    mime_type = f"image/{ext}" if ext != "jpg" else "image/jpeg"

            if detected.is_image:
                images.append(MediaImage(url=file_data.url, mime_type=mime_type))

        return images, files

    # ==================== Upload/Download ====================

    async def generate_upload_url(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        file_name: str,
        content_type: str,
        file_size: int,
    ) -> GenerateUploadUrlResponse:
        """Generate a signed URL for uploading a file.

        Creates a PENDING asset record so the upload can be tracked.
        """
        max_file_size = self._config.storage.file_upload_size_limit
        if file_size > max_file_size:
            raise FileSizeLimitExceededError(file_size, max_file_size)

        file_id = uuid.uuid4()
        ext = os.path.splitext(file_name)[1].lstrip(".") or "bin"
        asset_type = AssetType.from_content_type(content_type)
        blob_name = path_resolver.user_file(str(user_id), asset_type, str(file_id), ext)

        # When serve_base_url is set, route uploads through the backend proxy
        # instead of directly to the storage provider (which may be internal).
        serve_base = self._config.storage.serve_base_url
        if serve_base:
            upload_url = f"{serve_base.rstrip('/')}/storage/upload/{file_id}"
        else:
            upload_url = await self._storage.signed_upload_url(blob_name, content_type)

        await self._file_repo.create_asset(
            db,
            file_id=file_id,
            user_id=user_id,
            file_name=file_name,
            storage_path=blob_name,
            content_type=content_type,
            file_size=file_size,
            asset_type=asset_type,
            source=AssetSource.USER_UPLOAD,
            upload_status=UploadStatus.PENDING,
        )

        return GenerateUploadUrlResponse(id=str(file_id), upload_url=upload_url)

    async def complete_upload(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        file_id: uuid.UUID,
        file_name: str,
        file_size: int,
        content_type: str,
        session_id: Optional[uuid.UUID],
    ) -> UploadCompleteResponse:
        """Complete file upload: verify in storage, mark COMPLETE, return URL."""
        asset = await self._file_repo.get_by_id_and_user(db, file_id, user_id)

        if not asset:
            raise FileUploadNotFoundError(file_id)

        # Verify file exists in storage
        if not await self._storage.exists(asset.storage_path):
            await self._file_repo.mark_failed(db, file_id)
            raise FileUploadNotFoundError(file_id)

        # Mark complete and update metadata
        await self._file_repo.mark_complete(db, file_id)

        # Link to session if provided
        if session_id:
            await self._file_repo.link_to_session(db, file_id, session_id)

        signed_url = await self._storage.signed_url(asset.storage_path)
        return UploadCompleteResponse(file_url=signed_url)

    async def get_file_stream(
        self, db: AsyncSession, file_id: uuid.UUID, *, user_id: uuid.UUID
    ) -> StreamingResponse:
        """Get a streaming response for file download, validating user ownership."""
        asset = await self._file_repo.get_by_id_and_user(db, file_id, user_id)
        if not asset:
            raise FileAccessDeniedError(file_id)
        return await self._create_file_stream_response(asset)

    async def get_public_file_stream(
        self, db: AsyncSession, session_id: uuid.UUID, file_id: uuid.UUID
    ) -> StreamingResponse:
        """Get a streaming response for a public session file download."""
        asset = await self._file_repo.get_by_session_and_id(db, session_id, file_id)
        if not asset:
            raise FileUploadNotFoundError(file_id)
        return await self._create_file_stream_response(asset)

    async def _create_file_stream_response(self, asset: FileAsset) -> StreamingResponse:
        """Create a streaming response for file download."""
        # Detect HEIC by content_type or file extension before reading
        content_type = asset.content_type or "application/octet-stream"
        is_heic = content_type in ("image/heic", "image/heif")
        if not is_heic and asset.file_name:
            ext = asset.file_name.rsplit(".", 1)[-1].lower() if "." in asset.file_name else ""
            is_heic = ext in ("heic", "heif")

        if is_heic:
            return await self._create_heic_converted_response(asset)

        file_obj = await self._storage.read(asset.storage_path)

        async def file_stream() -> AsyncIterator[bytes]:
            try:
                chunk_size = 64 * 1024
                while True:
                    chunk = file_obj.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk
            finally:
                file_obj.close()

        return StreamingResponse(
            file_stream(),
            media_type=content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{asset.file_name}"',
                "Content-Length": str(asset.file_size or 0),
            },
        )

    async def _create_heic_converted_response(self, asset: FileAsset) -> StreamingResponse:
        """Read a HEIC file, convert to JPEG, and return as a response."""
        import anyio
        from ii_agent.agents.utils.heic import convert_heic_to_jpeg
        from ii_agent.core.logger import logger
        from fastapi.responses import Response

        # Read the entire file (required for HEIC conversion)
        file_obj = await self._storage.read(asset.storage_path)
        try:
            heic_bytes = file_obj.read()
        finally:
            file_obj.close()

        try:
            jpeg_bytes, _ = await anyio.to_thread.run_sync(convert_heic_to_jpeg, heic_bytes)
        except Exception:
            logger.warning(
                f"HEIC conversion failed for {asset.file_name}, "
                "serving original with image/heic content-type"
            )
            return Response(
                content=heic_bytes,
                media_type="image/heic",
                headers={
                    "Content-Disposition": f'attachment; filename="{asset.file_name}"',
                },
            )

        base_name = asset.file_name.rsplit(".", 1)[0] if "." in asset.file_name else asset.file_name
        jpeg_name = f"{base_name}.jpg"

        return Response(
            content=jpeg_bytes,
            media_type="image/jpeg",
            headers={
                "Content-Disposition": f'inline; filename="{jpeg_name}"',
            },
        )

    # ==================== Download URLs (batch) ====================

    async def generate_download_urls(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        storage_paths: list[str],
    ) -> GenerateDownloadUrlsResponse:
        """Generate signed download URLs for a list of storage paths owned by user."""
        normalized_paths = [path.lstrip("/") for path in storage_paths]

        assets = await self._file_repo.get_by_user_and_paths(db, user_id, normalized_paths)
        asset_map = {a.storage_path: a for a in assets}

        files_to_sign: list[FileAsset] = []
        index_map: list[int] = []
        file_ids: list[uuid.UUID | None] = [None] * len(normalized_paths)
        missing_paths: list[str] = []

        for idx, path in enumerate(normalized_paths):
            asset = asset_map.get(path)
            if asset:
                files_to_sign.append(asset)
                index_map.append(idx)
                file_ids[idx] = asset.id
            else:
                missing_paths.append(path)

        signed_subset = await self._get_download_signed_urls_batch(files_to_sign, force_signed=True)
        signed_urls: list[str | None] = [None] * len(normalized_paths)

        for idx, url in zip(index_map, signed_subset):
            signed_urls[idx] = url

        return GenerateDownloadUrlsResponse(
            signed_urls=signed_urls,
            missing_paths=missing_paths,
            file_ids=file_ids,
        )

    # ==================== Media Library ====================

    async def get_media_library(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        limit: int,
        offset: int,
        config_media_bucket: str | None = None,
        config_upload_bucket: str | None = None,
    ) -> MediaLibraryResponse:
        """Return all image uploads for a user across all sessions."""
        total = await self._file_repo.count_user_images(db, user_id)
        assets = await self._file_repo.get_user_images(db, user_id, limit=limit, offset=offset)

        signed_urls = await self._get_download_signed_urls_batch(assets)

        items: list[MediaLibraryItem] = []
        for asset, signed_url in zip(assets, signed_urls):
            if not signed_url:
                continue
            items.append(
                MediaLibraryItem(
                    id=asset.id,
                    name=asset.file_name,
                    url=signed_url,
                    source="generated" if asset.source == AssetSource.GENERATED else "upload",
                    created_at=asset.created_at,
                )
            )

        return MediaLibraryResponse(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
            has_more=offset + len(assets) < total,
        )

    # ==================== Avatar ====================

    async def upload_avatar(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        file_content,
        file_extension: str,
    ) -> str:
        """Upload or update an avatar image. Returns storage path."""
        file_id = str(uuid.uuid4())
        blob_name = path_resolver.user_avatar(str(user_id), file_id, file_extension)
        await self._storage.write(path=blob_name, content=file_content)
        return blob_name

    def get_avatar_url(self, avatar_blob_name: str) -> str:
        """Get the public URL for an avatar."""
        return self._storage.public_url(avatar_blob_name)

    # ==================== Publish ====================

    async def publish(
        self,
        db: AsyncSession,
        *,
        file_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> PublishResponse:
        """Move an asset from private to public storage path."""
        asset = await self._file_repo.get_by_id_and_user(db, file_id, user_id)
        if not asset:
            raise FileUploadNotFoundError(file_id)

        ext = os.path.splitext(asset.file_name)[1].lstrip(".") or "bin"
        public_path = f"shared/{asset.id}.{ext}"
        await self._storage.copy(asset.storage_path, public_path)
        public_url = self._storage.public_url(public_path)

        asset.is_public = True
        asset.storage_path = public_path
        await db.flush()
        return PublishResponse(public_url=public_url)

    # ==================== GDPR Delete ====================

    async def delete_asset(self, db: AsyncSession, file_id: uuid.UUID) -> None:
        """Remove a file from storage and the database."""
        asset = await self._file_repo.get_by_id(db, file_id)
        if asset:
            await self._storage.delete(asset.storage_path)
            await self._file_repo.delete_asset(db, file_id)

    async def delete_user_data(self, db: AsyncSession, user_id: uuid.UUID) -> None:
        """GDPR: delete all files for a user from storage and the DB."""
        from sqlalchemy import select

        result = await db.execute(select(FileAsset).where(FileAsset.user_id == user_id))
        assets = list(result.scalars().all())
        for asset in assets:
            await self._storage.delete(asset.storage_path)
        await self._file_repo.delete_user_assets(db, user_id)

    # ==================== Internal Helpers ====================

    async def _get_download_signed_urls_batch(
        self,
        assets: list[FileAsset],
        *,
        force_signed: bool = False,
    ) -> list[str | None]:
        """Fetch usable URLs efficiently using batch operations."""
        if not assets:
            return []

        results: list[str | None] = [None] * len(assets)
        paths_to_sign: list[tuple[int, str]] = []

        for idx, asset in enumerate(assets):
            storage_path = asset.storage_path
            if not storage_path:
                results[idx] = None
            elif storage_path.startswith(("http://", "https://")):
                results[idx] = storage_path
            else:
                paths_to_sign.append((idx, storage_path))

        if not paths_to_sign:
            return results

        paths = [path for _, path in paths_to_sign]

        try:
            signed_urls = await self._storage.signed_urls_batch(paths)

            for (idx, storage_path), signed_url in zip(paths_to_sign, signed_urls):
                if signed_url:
                    results[idx] = signed_url
                elif not force_signed:
                    try:
                        results[idx] = self._storage.public_url(storage_path)
                    except Exception:
                        results[idx] = None

        except Exception:
            for idx, path in paths_to_sign:
                try:
                    results[idx] = await self._storage.signed_url(path)
                except Exception:
                    if not force_signed:
                        try:
                            results[idx] = self._storage.public_url(path)
                        except Exception:
                            results[idx] = None
                    else:
                        results[idx] = None

        return results
