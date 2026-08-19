"""Sandbox exceptions for v2 agent system."""

from ii_agent.core.exceptions import IIAgentError


class SandboxException(IIAgentError):
    """Base exception for sandbox-related errors."""

    status_code = 500


class SandboxNotInitializedError(SandboxException):
    """Raised when attempting to use a sandbox that hasn't been initialized."""

    def __init__(self, sandbox_id: str = "unknown"):
        self.sandbox_id = sandbox_id
        super().__init__(f"Sandbox not initialized: {sandbox_id}")


class SandboxNotFoundException(SandboxException):
    """Raised when a sandbox cannot be found."""

    def __init__(self, sandbox_id: str):
        self.sandbox_id = sandbox_id
        super().__init__(f"Sandbox not found: {sandbox_id}")


class SandboxAuthenticationError(SandboxException):
    """Raised when authentication with the sandbox provider fails."""

    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message)


class SandboxTimeoutException(SandboxException):
    """Raised when a sandbox operation times out."""

    def __init__(self, sandbox_id: str, operation: str = "unknown"):
        self.sandbox_id = sandbox_id
        self.operation = operation
        super().__init__(f"Sandbox {sandbox_id} timed out during {operation}")


class SandboxCreationError(SandboxException):
    """Raised when sandbox creation fails."""

    def __init__(self, message: str):
        super().__init__(f"Failed to create sandbox: {message}")


class SandboxOperationError(SandboxException):
    """Raised when a sandbox operation fails."""

    def __init__(self, operation: str, message: str):
        self.operation = operation
        super().__init__(f"Sandbox operation '{operation}' failed: {message}")
