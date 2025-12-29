"""Data models for sandbox server API."""

from typing import Optional, Literal
from pydantic import BaseModel
from datetime import datetime


class CreateSandboxRequest(BaseModel):
    """Request to create a new sandbox."""

    user_id: str
    sandbox_template_id: Optional[str] = None


class CreateSandboxResponse(BaseModel):
    """Response from creating a sandbox."""

    success: bool = True
    sandbox_id: str
    provider_sandbox_id: str
    status: str
    message: Optional[str] = None


class ConnectSandboxRequest(BaseModel):
    """Request to connect or resume a sandbox."""

    sandbox_id: str


class ConnectSandboxResponse(BaseModel):
    """Response from connecting to a sandbox."""

    success: bool = True
    sandbox_id: str
    provider_sandbox_id: str
    status: str
    message: Optional[str] = None


class ScheduleTimeoutRequest(BaseModel):
    """Request to schedule a timeout for a sandbox."""

    sandbox_id: str
    timeout_seconds: int


class ScheduleTimeoutResponse(BaseModel):
    """Response from scheduling a timeout for a sandbox."""

    success: bool
    message: Optional[str] = None


class HealthCheckResponse(BaseModel):
    """Response from health check."""

    success: bool
    message: Optional[str] = None


class PauseSandboxRequest(BaseModel):
    """Request to pause a sandbox."""

    sandbox_id: str
    reason: Optional[str] = None


class PauseSandboxResponse(BaseModel):
    """Response from pausing a sandbox."""

    success: bool
    message: Optional[str] = None


class DeleteSandboxResponse(BaseModel):
    """Response from deleting a sandbox."""

    success: bool
    message: Optional[str] = None


class SandboxStatusResponse(BaseModel):
    """Response containing sandbox status."""

    success: bool = True
    sandbox_id: str
    status: str
    provider_sandbox_id: Optional[str] = None
    message: Optional[str] = None


class ExposePortRequest(BaseModel):
    """Request to expose a port from sandbox."""

    sandbox_id: str
    port: int
    external: bool = False


class ExposePortResponse(BaseModel):
    """Response with exposed port URL."""

    success: bool = True
    url: str
    message: Optional[str] = None


class FileOperationRequest(BaseModel):
    """Request for file operations."""

    sandbox_id: str
    file_path: str
    content: Optional[str | bytes] = None  # For write operations
    format: Literal["text", "bytes", "stream"] = "text"  # For download operations


class UploadFileFromUrlRequest(BaseModel):
    """Request to upload a file to sandbox by downloading from URL."""

    sandbox_id: str
    file_path: str
    url: str


class DownloadToPresignedUrlRequest(BaseModel):
    """Request to download a file from sandbox to a presigned URL."""

    sandbox_id: str
    format: Literal["text", "bytes"] = "text"
    sandbox_path: str
    presigned_url: str


class FileOperationResponse(BaseModel):
    """Response from file operations."""

    success: bool
    content: Optional[str | bytes] = None  # For read operations (non-streaming)
    message: Optional[str] = None


class RunCommandRequest(BaseModel):
    """Request to run a command in a sandbox."""

    sandbox_id: str
    command: str
    background: bool = False


class RunCommandResponse(BaseModel):
    """Response from running a command."""

    success: bool
    output: str
    message: Optional[str] = None


class SandboxInfo(BaseModel):
    """Information about a sandbox."""

    success: bool = True
    id: str
    provider: str
    user_id: str
    provider_sandbox_id: str
    status: str
    created_at: datetime
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None
    last_activity_at: Optional[datetime] = None
    message: Optional[str] = None
