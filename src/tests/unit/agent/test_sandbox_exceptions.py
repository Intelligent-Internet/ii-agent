"""Unit tests for sandbox exception classes."""

from ii_agent.agents.sandboxes.exceptions import (
    SandboxAuthenticationError,
    SandboxCreationError,
    SandboxException,
    SandboxNotFoundException,
    SandboxNotInitializedError,
    SandboxOperationError,
    SandboxTimeoutException,
)
from ii_agent.core.exceptions import IIAgentError


class TestSandboxExceptionHierarchy:
    """All sandbox exceptions inherit from IIAgentError."""

    def test_base_inherits_from_ii_agent_error(self):
        assert issubclass(SandboxException, IIAgentError)

    def test_all_subclasses(self):
        for cls in (
            SandboxNotInitializedError,
            SandboxNotFoundException,
            SandboxAuthenticationError,
            SandboxTimeoutException,
            SandboxCreationError,
            SandboxOperationError,
        ):
            assert issubclass(cls, SandboxException)


class TestSandboxNotFoundException:
    def test_message_includes_id(self):
        exc = SandboxNotFoundException("sandbox-abc")
        assert "sandbox-abc" in str(exc)
        assert exc.sandbox_id == "sandbox-abc"


class TestSandboxAuthenticationError:
    def test_default_message(self):
        exc = SandboxAuthenticationError()
        assert "Authentication failed" in str(exc)

    def test_custom_message(self):
        exc = SandboxAuthenticationError("bad token")
        assert "bad token" in str(exc)


class TestSandboxTimeoutException:
    def test_message_includes_id_and_operation(self):
        exc = SandboxTimeoutException("sandbox-xyz", "startup check")
        assert "sandbox-xyz" in str(exc)
        assert "startup check" in str(exc)
        assert exc.sandbox_id == "sandbox-xyz"
        assert exc.operation == "startup check"
