"""File storage Pydantic models."""

from pydantic import BaseModel, Field
from typing import Optional, List


class FileUploadRequest(BaseModel):
    """Model for file upload request."""

    session_id: str
    file_name: str
    file_content: bytes = Field(..., description="Base64 encoded file content")
    content_type: Optional[str] = "application/octet-stream"
    metadata: Optional[dict] = None


class FileUploadResponse(BaseModel):
    """Model for file upload response."""

    file_id: str
    file_name: str
    file_size: int
    content_type: str
    storage_url: str
    public_url: Optional[str] = None
    uploaded_at: str


class FileInfo(BaseModel):
    """Model for file information."""

    file_id: str
    file_name: str
    file_size: int
    content_type: str
    storage_url: str
    public_url: Optional[str] = None
    session_id: str
    user_id: str
    uploaded_at: str
    metadata: Optional[dict] = None


class FileList(BaseModel):
    """Model for file list response."""

    files: List[FileInfo]
    total: int
    page: int
    per_page: int


class FileShareRequest(BaseModel):
    """Model for file sharing request."""

    file_id: str
    expiration_hours: int = Field(default=24, ge=1, le=168)  # 1 hour to 1 week
    allow_download: bool = True


class FileShareResponse(BaseModel):
    """Model for file sharing response."""

    file_id: str
    share_url: str
    expires_at: str
    allow_download: bool


class StorageStats(BaseModel):
    """Model for storage statistics."""

    total_files: int
    total_size_bytes: int
    total_size_mb: float
    files_by_type: dict
    storage_used_percent: float
    storage_limit_bytes: int
