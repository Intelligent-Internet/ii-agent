"""Sandbox module for agent system.

Provides sandbox management for isolated code execution environments.

Key components:
- Sandbox: Abstract interface for sandbox providers
- SandboxService: Orchestrates DB persistence + provider lifecycle
- E2BSandbox: E2B cloud sandbox provider implementation
"""

from ii_agent.agents.sandboxes.base import Sandbox
from ii_agent.agents.sandboxes.media_uploader import upload_media_to_sandbox
from ii_agent.agents.sandboxes.docker import DockerSandbox
from ii_agent.agents.sandboxes.docker_shell import DockerShell
from ii_agent.agents.sandboxes.e2b import E2BSandbox
from ii_agent.agents.sandboxes.shell import Shell
from ii_agent.agents.sandboxes.exceptions import (
    SandboxAuthenticationError,
    SandboxCreationError,
    SandboxException,
    SandboxNotFoundException,
    SandboxNotInitializedError,
    SandboxOperationError,
    SandboxTimeoutException,
)
from ii_agent.agents.sandboxes.models import AgentSandbox
from ii_agent.agents.sandboxes.repository import SandboxRepository
from ii_agent.agents.sandboxes.schemas import FileUpload, SandboxFileInfo, SandboxInfo
from ii_agent.agents.sandboxes.types import SandboxProviderType, SandboxStatus

__all__ = [
    # Interface
    "Sandbox",
    "Shell",
    # Provider implementations
    "E2BSandbox",
    "DockerSandbox",
    "DockerShell",
    # ORM
    "AgentSandbox",
    # Repository
    "SandboxRepository",
    # Schemas
    "SandboxInfo",
    "SandboxFileInfo",
    "FileUpload",
    # Types
    "SandboxStatus",
    "SandboxProviderType",
    # Exceptions
    "SandboxException",
    "SandboxAuthenticationError",
    "SandboxCreationError",
    "SandboxNotFoundException",
    "SandboxNotInitializedError",
    "SandboxOperationError",
    "SandboxTimeoutException",
    # Utilities
    "upload_media_to_sandbox",
]
