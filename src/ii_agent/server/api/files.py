"""File storage API endpoints."""

import io
import time
import uuid
import logging
from typing import AsyncIterator
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, and_
from urllib.parse import unquote
from ii_agent.db.models import User, FileUpload, Session
from ii_agent.storage import BaseStorage, GCS
from ii_agent.core.config.ii_agent_config import config
from ii_agent.server.api.deps import DBSession, CurrentUser
from ii_agent.server.shared import storage as shared_storage
import anyio

logger = logging.getLogger(__name__)

router = APIRouter(tags=["files"])


# TODO: move this to deps.py file
async def get_file_upload_storage() -> BaseStorage:
    """Dependency to get storage provider instance."""
    if config.storage_provider == "gcs":
        return GCS(
            config.file_upload_project_id,
            config.file_upload_bucket_name,
            config.custom_domain,
        )
    elif config.storage_provider == "local":
        # Use the shared storage instance for local provider
        return shared_storage

    raise HTTPException(status_code=500, detail=f"Storage provider '{config.storage_provider}' not supported")


async def get_avatar_storage() -> BaseStorage:
    """Dependency to get avatar storage provider instance."""
    if config.storage_provider == "gcs":
        return GCS(
            config.avatar_project_id, config.avatar_bucket_name, config.custom_domain
        )

    raise HTTPException(status_code=500, detail="Storage provider not supported")


# TODO: move this to utils.py file
def _get_blob_name(user_id: str, file_id: str, file_name: str) -> str:
    return f"users/{user_id}/uploads/{file_id}-{file_name}"


# TODO: move this to schemas.py file
class GenerateUploadUrlRequest(BaseModel):
    file_name: str
    content_type: str
    file_size: int


class GenerateUploadUrlResponse(BaseModel):
    id: str
    upload_url: str


class UploadCompleteRequest(BaseModel):
    id: str
    file_name: str
    file_size: int
    content_type: str


class UploadCompleteResponse(BaseModel):
    file_url: str


# TODO: move this to services layer
@router.post("/chat/generate-upload-url")
async def generate_upload_url(
    upload_request: GenerateUploadUrlRequest,
    current_user: CurrentUser,
    storage: BaseStorage = Depends(get_file_upload_storage),
):
    """Generate a signed URL for uploading a file to the object storage."""

    user_id = current_user.id
    file_name = upload_request.file_name
    content_type = upload_request.content_type
    file_size = upload_request.file_size

    # File size validation using config
    if file_size > config.file_upload_size_limit:
        raise HTTPException(
            status_code=413,
            detail=f"File size {file_size} bytes exceeds maximum allowed size of {config.file_upload_size_limit} bytes",
        )

    file_id = str(uuid.uuid4())
    # Decode URL-encoded chars in file_name for storage path
    # This ensures consistency with upload-complete which also decodes
    decoded_file_name = unquote(file_name)
    blob_name = _get_blob_name(user_id, file_id, decoded_file_name)

    # generate the signed URL
    # Use internal=False because this URL is returned to the browser, not used server-to-server
    signed_url = storage.get_upload_signed_url(blob_name, content_type, internal=False)

    # Debug logging
    logger.info(f"Generated upload URL for user {user_id}: {signed_url}")

    return GenerateUploadUrlResponse(
        id=file_id,
        upload_url=signed_url,
    )


@router.post("/chat/upload-complete")
async def upload_complete(
    upload_complete_request: UploadCompleteRequest,
    db: DBSession,
    current_user: CurrentUser,
    storage: BaseStorage = Depends(get_file_upload_storage),
):
    """Generate a signed URL for downloading a file from the object storage."""
    user_id = current_user.id
    file_id = upload_complete_request.id
    file_name = upload_complete_request.file_name
    file_size = upload_complete_request.file_size
    content_type = upload_complete_request.content_type

    # Decode URL-encoded chars in file_name to match what was stored
    decoded_file_name = unquote(file_name)
    blob_name = _get_blob_name(user_id, file_id, decoded_file_name)

    # Check if the file exists in storage
    if not storage.is_exists(blob_name):
        raise HTTPException(status_code=404, detail="File not found in storage")

    # create the file upload record
    # Store the decoded file_name so sandbox gets consistent naming
    file_upload_record = FileUpload(
        id=file_id,
        user_id=user_id,
        file_name=decoded_file_name,
        file_size=file_size,
        storage_path=blob_name,
        content_type=content_type,
    )
    db.add(file_upload_record)
    await db.commit()
    await db.refresh(file_upload_record)

    # Generate the signed download URL
    signed_url = storage.get_download_signed_url(blob_name)

    return UploadCompleteResponse(
        file_url=signed_url,
    )


@router.put("/files/upload/{path:path}")
async def upload_file_local(
    path: str,
    request: "Request",
    token: str = None,
    expires: str = None,
    content_type: str = None,
):
    """Upload endpoint for local storage. Validates token and stores the file.

    Accepts raw file body (not multipart/form-data) as sent by XMLHttpRequest.send(file).
    """
    logger.info(f"Received upload request for path: {path}, token: {token[:8] if token else None}...")
    # Validate token and expiration
    if not token or not expires:
        raise HTTPException(status_code=401, detail="Missing authentication parameters")

    try:
        expiry_time = int(expires)
        if time.time() > expiry_time:
            raise HTTPException(status_code=401, detail="Upload URL has expired")
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid expiration time")

    # Validate token - the path from FastAPI is already URL-decoded
    import hashlib
    expected_token = hashlib.sha256(f"{path}:{expires}:local-secret".encode()).hexdigest()[:16]
    logger.info(f"Token validation: received={token}, expected={expected_token}, path_for_hash={path}")
    if token != expected_token:
        raise HTTPException(status_code=401, detail="Invalid upload token")

    # Store the file using shared_storage
    from ii_agent.server.shared import storage as shared_storage

    # Read raw file content from request body
    content = await request.body()

    # Write to storage - signature is write(content, path, content_type)
    await anyio.to_thread.run_sync(
        shared_storage.write,
        io.BytesIO(content),
        path,
        content_type
    )

    logger.info(f"Successfully uploaded file to path: {path}, size: {len(content)} bytes")
    return JSONResponse({"status": "success", "path": path})


@router.get("/files/{path:path}")
async def serve_file(
    path: str,
    token: str = None,
    expires: str = None,
):
    """Serve a file from local storage with token validation.

    This endpoint serves files that were uploaded via the upload endpoint.
    Used by sandbox-server to download files for processing.
    """
    logger.info(f"Received download request for path: {path}, token: {token[:8] if token else None}...")

    # Validate token and expiration
    if not token or not expires:
        raise HTTPException(status_code=401, detail="Missing authentication parameters")

    try:
        expiry_time = int(expires)
        if time.time() > expiry_time:
            raise HTTPException(status_code=401, detail="Download URL has expired")
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid expiration time")

    # Validate token - the path from FastAPI is already URL-decoded
    import hashlib
    expected_token = hashlib.sha256(f"{path}:{expires}:local-secret".encode()).hexdigest()[:16]
    logger.info(f"Download token validation: received={token}, expected={expected_token}, path_for_hash={path}")
    if token != expected_token:
        raise HTTPException(status_code=401, detail="Invalid download token")

    # Check if file exists
    if not shared_storage.is_exists(path):
        raise HTTPException(status_code=404, detail="File not found")

    # Get content type from metadata if available
    content_type = "application/octet-stream"
    full_path = shared_storage._get_full_path(path)
    meta_path = full_path + ".meta"
    import os
    if os.path.exists(meta_path):
        with open(meta_path, "r") as f:
            content_type = f.read().strip()

    # Stream file content
    async def file_stream() -> AsyncIterator[bytes]:
        file_obj = await anyio.to_thread.run_sync(shared_storage.read, path)
        try:
            chunk_size = 64 * 1024  # 64KB chunks
            while True:
                chunk = await anyio.to_thread.run_sync(file_obj.read, chunk_size)
                if not chunk:
                    break
                yield chunk
        finally:
            await anyio.to_thread.run_sync(file_obj.close)

    return StreamingResponse(
        file_stream(),
        media_type=content_type,
        headers={
            "Content-Disposition": f"inline; filename=\"{path.split('/')[-1]}\"",
        }
    )


@router.get("/chat/{session_id}/files/{file_id}")
async def download_file(
    session_id: str,
    file_id: str,
    db: DBSession,
    current_user: CurrentUser,
):
    """Download a file from a session with async streaming."""

    # Verify session belongs to user
    session_result = await db.execute(
        select(Session).where(
            and_(
                Session.id == session_id,
                Session.user_id == str(current_user.id)
            )
        )
    )
    session = session_result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or access denied")

    # Get file upload record
    file_result = await db.execute(
        select(FileUpload).where(
            and_(
                FileUpload.id == file_id,
                FileUpload.session_id == session.id
            )
        )
    )
    file_upload = file_result.scalar_one_or_none()
    if not file_upload:
        raise HTTPException(status_code=404, detail="File not found in session")

    # Verify file exists in storage
    storage_path = file_upload.storage_path

    async def file_stream() -> AsyncIterator[bytes]:
        """Async generator to stream file content."""
        # Read file from storage in a thread to avoid blocking
        file_obj = await anyio.to_thread.run_sync(shared_storage.read, storage_path)

        try:
            # Stream in chunks (64KB chunks)
            chunk_size = 64 * 1024
            while True:
                chunk = await anyio.to_thread.run_sync(file_obj.read, chunk_size)
                if not chunk:
                    break
                yield chunk
        finally:
            # Close file handle
            await anyio.to_thread.run_sync(file_obj.close)

    return StreamingResponse(
        file_stream(),
        media_type=file_upload.content_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{file_upload.file_name}"',
            "Content-Length": str(file_upload.file_size),
        }
    )

@router.post("/avatar")
async def upload_avatar(
    db: DBSession,
    current_user: CurrentUser,
    file: UploadFile = File(...),
    storage: BaseStorage = Depends(get_avatar_storage),
):
    """Upload or update an avatar image for the user."""
    user_id = current_user.id
    file_extension = file.filename.split(".")[-1]
    destination_blob_name = f"users/{user_id}/profile/avatar.{file_extension}"

    storage.write(
        content=file.file,
        path=destination_blob_name,
    )

    # update the user's avatar
    current_user.avatar = destination_blob_name
    await db.commit()
    await db.refresh(current_user)

    return JSONResponse(
        status_code=200,
        content={
            "message": "Avatar uploaded successfully",
            "url": storage.get_public_url(destination_blob_name),
        },
    )


@router.get("/avatar")
async def get_avatar(
    current_user: CurrentUser,
    storage: BaseStorage = Depends(get_avatar_storage),
):
    """Get the avatar image for the user."""
    avatar_blob_name = current_user.avatar

    if not avatar_blob_name:
        raise HTTPException(status_code=404, detail="No avatar image found")

    return JSONResponse(
        status_code=200, content={"url": storage.get_public_url(avatar_blob_name)}
    )
