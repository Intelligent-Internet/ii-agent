"""Sandbox management Pydantic models."""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List


class SandboxCreate(BaseModel):
    """Model for creating a new sandbox."""

    template: str = Field(default="base", description="Sandbox template")
    cpu_limit: int = Field(
        default=1000, ge=100, le=4000, description="CPU limit in millicores"
    )
    memory_limit: int = Field(
        default=512, ge=128, le=8192, description="Memory limit in MB"
    )
    disk_limit: int = Field(
        default=1024, ge=256, le=10240, description="Disk limit in MB"
    )
    network_enabled: bool = Field(default=True, description="Enable network access")
    metadata: Optional[Dict[str, Any]] = None


class SandboxUpdate(BaseModel):
    """Model for updating a sandbox."""

    cpu_limit: Optional[int] = Field(None, ge=100, le=4000)
    memory_limit: Optional[int] = Field(None, ge=128, le=8192)
    disk_limit: Optional[int] = Field(None, ge=256, le=10240)
    network_enabled: Optional[bool] = None
    metadata: Optional[Dict[str, Any]] = None


class SandboxInfo(BaseModel):
    """Model for sandbox information."""

    id: str
    provider: str
    sandbox_id: str
    user_id: str
    template: str
    status: str
    cpu_limit: int
    memory_limit: int
    disk_limit: int
    network_enabled: bool
    metadata: Optional[Dict[str, Any]] = None
    created_at: str
    started_at: Optional[str] = None
    stopped_at: Optional[str] = None
    last_activity_at: Optional[str] = None


class SandboxList(BaseModel):
    """Model for sandbox list response."""

    sandboxes: List[SandboxInfo]
    total: int
    page: int
    per_page: int


class SandboxStats(BaseModel):
    """Model for sandbox statistics."""

    total_sandboxes: int
    running_sandboxes: int
    stopped_sandboxes: int
    error_sandboxes: int
    total_cpu_usage: int
    total_memory_usage: int
    total_disk_usage: int


class SandboxCommand(BaseModel):
    """Model for executing commands in sandbox."""

    command: str = Field(..., description="Command to execute")
    timeout: int = Field(default=30, ge=1, le=300, description="Timeout in seconds")
    working_directory: Optional[str] = Field(None, description="Working directory")


class SandboxCommandResult(BaseModel):
    """Model for sandbox command execution result."""

    exit_code: int
    stdout: str
    stderr: str
    execution_time: float
    timeout: bool = False


class SandboxFile(BaseModel):
    """Model for sandbox file operations."""

    path: str = Field(..., description="File path in sandbox")
    content: Optional[str] = Field(
        None, description="File content for write operations"
    )
    encoding: str = Field(default="utf-8", description="File encoding")


class SandboxFileInfo(BaseModel):
    """Model for sandbox file information."""

    path: str
    size: int
    is_directory: bool
    created_at: str
    modified_at: str
    permissions: str


class SandboxTemplate(BaseModel):
    """Model for sandbox template information."""

    id: str
    name: str
    description: str
    version: str
    base_image: str
    supported_languages: List[str]
    default_cpu: int
    default_memory: int
    default_disk: int
