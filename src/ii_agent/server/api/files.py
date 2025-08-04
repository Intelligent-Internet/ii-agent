"""File storage API endpoints."""

import mimetypes
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional
from io import BytesIO

from ii_agent.db.manager import get_db
from ii_agent.db.models import User, Session as SessionModel
from ii_agent.server.auth.middleware import get_current_user
from ii_agent.server.storage.models import (
    FileUploadResponse,
    FileInfo,
    FileList,
    FileShareRequest,
    FileShareResponse,
    StorageStats,
)
from ii_agent.server.storage.gcs_provider import GCSStorageProvider


router = APIRouter(prefix="/files", tags=["File Storage"])


async def get_storage_provider() -> GCSStorageProvider:
    """Dependency to get storage provider instance."""
    return GCSStorageProvider()


@router.post(
    "/upload", response_model=FileUploadResponse, status_code=status.HTTP_201_CREATED
)
async def upload_file(
    file: UploadFile = File(...),
    session_id: str = Query(..., description="Session ID to associate the file with"),
    make_public: bool = Query(False, description="Make file publicly accessible"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    storage: GCSStorageProvider = Depends(get_storage_provider),
):
    """Upload a file to cloud storage."""

    # Verify session ownership
    session = (
        db.query(SessionModel)
        .filter(SessionModel.id == session_id, SessionModel.user_id == current_user.id)
        .first()
    )

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or access denied",
        )

    # Read file content
    file_content = await file.read()

    # Determine content type
    content_type = (
        file.content_type
        or mimetypes.guess_type(file.filename)[0]
        or "application/octet-stream"
    )

    # Prepare metadata
    metadata = {
        "public": make_public,
        "original_filename": file.filename,
        "uploaded_by": current_user.id,
        "session_id": session_id,
    }

    # Upload to storage
    upload_response = await storage.upload_file(
        user_id=current_user.id,
        session_id=session_id,
        file_name=file.filename,
        file_content=file_content,
        content_type=content_type,
        metadata=metadata,
    )

    # TODO: Store file metadata in database for tracking

    return upload_response


@router.get("/", response_model=FileList)
async def list_files(
    session_id: Optional[str] = Query(None, description="Filter by session ID"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    storage: GCSStorageProvider = Depends(get_storage_provider),
):
    """List user's files."""

    # Build prefix for user's files
    prefix = f"users/{current_user.id}/"
    if session_id:
        # Verify session ownership
        session = (
            db.query(SessionModel)
            .filter(
                SessionModel.id == session_id, SessionModel.user_id == current_user.id
            )
            .first()
        )

        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found or access denied",
            )

        prefix += f"sessions/{session_id}/"

    # Get files from storage
    storage_files = await storage.list_files(prefix=prefix, max_results=per_page * 2)

    # Convert to API models
    files = []
    for storage_file in storage_files:
        # Extract file ID from path
        file_path_parts = storage_file["name"].split("/")
        file_id = file_path_parts[-1].split("-")[0]  # Extract UUID part

        # Extract session ID from path
        file_session_id = file_path_parts[3] if len(file_path_parts) > 3 else ""

        files.append(
            FileInfo(
                file_id=file_id,
                file_name=storage_file["metadata"].get(
                    "original_filename", file_path_parts[-1]
                ),
                file_size=storage_file["size"],
                content_type=storage_file["content_type"],
                storage_url=f"gs://{storage.bucket_name}/{storage_file['name']}",
                public_url=f"https://storage.googleapis.com/{storage.bucket_name}/{storage_file['name']}"
                if storage_file["metadata"].get("public")
                else None,
                session_id=file_session_id,
                user_id=current_user.id,
                uploaded_at=storage_file["created"].isoformat(),
                metadata=storage_file["metadata"],
            )
        )

    # Apply pagination
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated_files = files[start_idx:end_idx]

    return FileList(
        files=paginated_files, total=len(files), page=page, per_page=per_page
    )


@router.get("/{file_id}/download")
async def download_file(
    file_id: str,
    current_user: User = Depends(get_current_user),
    storage: GCSStorageProvider = Depends(get_storage_provider),
):
    """Download a file."""

    # Find file path (simplified - in real implementation, store in database)
    # For now, we'll need to list files to find the right one
    prefix = f"users/{current_user.id}/"
    storage_files = await storage.list_files(prefix=prefix, max_results=1000)

    target_file = None
    for storage_file in storage_files:
        if storage_file["name"].split("/")[-1].startswith(file_id):
            target_file = storage_file
            break

    if not target_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File not found"
        )

    # Download file content
    file_content = await storage.download_file(target_file["name"])

    if file_content is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File content not found"
        )

    # Get original filename from metadata
    original_filename = target_file["metadata"].get(
        "original_filename", f"{file_id}.bin"
    )

    return StreamingResponse(
        BytesIO(file_content),
        media_type=target_file["content_type"],
        headers={"Content-Disposition": f"attachment; filename={original_filename}"},
    )


@router.delete("/{file_id}")
async def delete_file(
    file_id: str,
    current_user: User = Depends(get_current_user),
    storage: GCSStorageProvider = Depends(get_storage_provider),
):
    """Delete a file."""

    # Find file path (simplified - in real implementation, store in database)
    prefix = f"users/{current_user.id}/"
    storage_files = await storage.list_files(prefix=prefix, max_results=1000)

    target_file = None
    for storage_file in storage_files:
        if storage_file["name"].split("/")[-1].startswith(file_id):
            target_file = storage_file
            break

    if not target_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File not found"
        )

    # Delete file
    success = await storage.delete_file(target_file["name"])

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete file",
        )

    return {"message": "File deleted successfully"}


@router.post("/{file_id}/share", response_model=FileShareResponse)
async def share_file(
    file_id: str,
    share_request: FileShareRequest,
    current_user: User = Depends(get_current_user),
    storage: GCSStorageProvider = Depends(get_storage_provider),
):
    """Generate a shareable link for a file."""

    # Find file path
    prefix = f"users/{current_user.id}/"
    storage_files = await storage.list_files(prefix=prefix, max_results=1000)

    target_file = None
    for storage_file in storage_files:
        if storage_file["name"].split("/")[-1].startswith(file_id):
            target_file = storage_file
            break

    if not target_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File not found"
        )

    # Generate signed URL
    method = "GET" if share_request.allow_download else "HEAD"
    signed_url = await storage.generate_signed_url(
        file_path=target_file["name"],
        expiration_hours=share_request.expiration_hours,
        method=method,
    )

    if not signed_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate share URL",
        )

    from datetime import datetime, timedelta, timezone

    expires_at = datetime.now(timezone.utc) + timedelta(
        hours=share_request.expiration_hours
    )

    return FileShareResponse(
        file_id=file_id,
        share_url=signed_url,
        expires_at=expires_at.isoformat(),
        allow_download=share_request.allow_download,
    )


@router.get("/stats", response_model=StorageStats)
async def get_storage_stats(
    current_user: User = Depends(get_current_user),
    storage: GCSStorageProvider = Depends(get_storage_provider),
):
    """Get storage usage statistics for the current user."""

    # Get user's files
    prefix = f"users/{current_user.id}/"
    storage_files = await storage.list_files(prefix=prefix, max_results=10000)

    # Calculate stats
    total_files = len(storage_files)
    total_size_bytes = sum(file["size"] for file in storage_files)
    total_size_mb = total_size_bytes / (1024 * 1024)

    # Count files by type
    files_by_type = {}
    for file in storage_files:
        content_type = file["content_type"]
        type_category = "other"

        if content_type.startswith("image/"):
            type_category = "image"
        elif content_type.startswith("video/"):
            type_category = "video"
        elif content_type.startswith("audio/"):
            type_category = "audio"
        elif content_type in ["application/pdf", "application/msword", "text/plain"]:
            type_category = "document"

        files_by_type[type_category] = files_by_type.get(type_category, 0) + 1

    # Calculate storage usage percentage (assuming 1GB limit for free tier)
    storage_limit_bytes = 1024 * 1024 * 1024  # 1GB
    storage_used_percent = (total_size_bytes / storage_limit_bytes) * 100

    return StorageStats(
        total_files=total_files,
        total_size_bytes=total_size_bytes,
        total_size_mb=round(total_size_mb, 2),
        files_by_type=files_by_type,
        storage_used_percent=round(storage_used_percent, 2),
        storage_limit_bytes=storage_limit_bytes,
    )
