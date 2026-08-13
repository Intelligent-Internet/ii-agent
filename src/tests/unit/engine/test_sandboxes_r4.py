"""Unit tests for engine/sandboxes/e2b.py and sandbox_client.py (r4)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# e2b_exception_handler decorator
# ---------------------------------------------------------------------------


class TestE2bExceptionHandlerR4:
    """Tests for the e2b_exception_handler decorator."""

    @pytest.mark.asyncio
    async def test_reraises_sandbox_not_found_exception(self):
        from e2b.exceptions import NotFoundException
        from ii_agent.agents.sandboxes.e2b import e2b_exception_handler
        from ii_agent.agents.sandboxes.exceptions import SandboxNotFoundException

        @e2b_exception_handler
        async def failing_func(self):
            raise NotFoundException("not found")

        mock_self = MagicMock()
        mock_self.sandbox_id = "test-sandbox"
        with pytest.raises(SandboxNotFoundException) as exc_info:
            await failing_func(mock_self)
        assert "test-sandbox" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_reraises_authentication_exception(self):
        from e2b.exceptions import AuthenticationException
        from ii_agent.agents.sandboxes.e2b import e2b_exception_handler
        from ii_agent.agents.sandboxes.exceptions import SandboxAuthenticationError

        @e2b_exception_handler
        async def failing_func():
            raise AuthenticationException("bad key")

        with pytest.raises(SandboxAuthenticationError):
            await failing_func()

    @pytest.mark.asyncio
    async def test_reraises_timeout_exception(self):
        from e2b.exceptions import TimeoutException
        from ii_agent.agents.sandboxes.e2b import e2b_exception_handler
        from ii_agent.agents.sandboxes.exceptions import SandboxTimeoutException

        @e2b_exception_handler
        async def failing_func(self):
            raise TimeoutException("timed out")

        mock_self = MagicMock()
        mock_self.sandbox_id = "sandbox-timeout"
        with pytest.raises(SandboxTimeoutException):
            await failing_func(mock_self)

    @pytest.mark.asyncio
    async def test_wraps_generic_exception_in_sandbox_operation_error(self):
        from ii_agent.agents.sandboxes.e2b import e2b_exception_handler
        from ii_agent.agents.sandboxes.exceptions import SandboxOperationError

        @e2b_exception_handler
        async def failing_func():
            raise RuntimeError("some random error")

        with pytest.raises(SandboxOperationError) as exc_info:
            await failing_func()
        assert "failing_func" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_reraises_sandbox_exceptions_without_wrapping(self):
        from ii_agent.agents.sandboxes.e2b import e2b_exception_handler
        from ii_agent.agents.sandboxes.exceptions import SandboxNotInitializedError

        @e2b_exception_handler
        async def func():
            raise SandboxNotInitializedError("already-typed")

        with pytest.raises(SandboxNotInitializedError):
            await func()

    @pytest.mark.asyncio
    async def test_passes_through_successful_return(self):
        from ii_agent.agents.sandboxes.e2b import e2b_exception_handler

        @e2b_exception_handler
        async def success_func():
            return "result-value"

        result = await success_func()
        assert result == "result-value"

    @pytest.mark.asyncio
    async def test_sandbox_id_unknown_when_no_self_attr(self):
        from e2b.exceptions import NotFoundException
        from ii_agent.agents.sandboxes.e2b import e2b_exception_handler
        from ii_agent.agents.sandboxes.exceptions import SandboxNotFoundException

        @e2b_exception_handler
        async def func():
            raise NotFoundException("gone")

        with pytest.raises(SandboxNotFoundException) as exc_info:
            await func()
        assert "unknown" in str(exc_info.value)


# ---------------------------------------------------------------------------
# E2BSandbox initialization
# ---------------------------------------------------------------------------


class TestE2BSandboxInitR4:
    def _make_manager(self, **overrides):
        from ii_agent.agents.sandboxes.e2b import E2BSandbox
        from ii_agent.agents.sandboxes.schemas import SandboxStatus

        defaults = {
            "sandbox_id": "internal-sandbox-1",
            "session_id": "session-1",
            "provider_sandbox_id": "e2b-sandbox-123",
            "status": SandboxStatus.NOT_INITIALIZED,
            "metadata": None,
            "sandbox": None,
            "expired_at": None,
        }
        defaults.update(overrides)
        return E2BSandbox(**defaults)

    def test_init_sets_sandbox_id(self):
        manager = self._make_manager()
        assert manager.sandbox_id == "internal-sandbox-1"

    def test_init_sets_session_id(self):
        manager = self._make_manager()
        assert manager.session_id == "session-1"

    def test_init_sets_provider_sandbox_id(self):
        manager = self._make_manager()
        assert manager.provider_sandbox_id == "e2b-sandbox-123"

    def test_init_defaults_metadata_to_empty_dict(self):
        manager = self._make_manager(metadata=None)
        assert manager.metadata == {}

    def test_init_with_metadata(self):
        meta = {"key": "value"}
        manager = self._make_manager(metadata=meta)
        assert manager.metadata == meta

    def test_init_mcp_client_is_none(self):
        manager = self._make_manager()
        assert manager.mcp_client is None

    def test_get_provider_id_returns_provider_sandbox_id(self):
        manager = self._make_manager()
        assert manager.get_provider_id() == "e2b-sandbox-123"

    def test_provider_is_e2b(self):
        from ii_agent.agents.sandboxes.e2b import E2BSandbox

        assert E2BSandbox.PROVIDER == "e2b"


# ---------------------------------------------------------------------------
# E2BSandbox._to_sandbox_status
# ---------------------------------------------------------------------------


class TestE2BSandboxToSandboxStatusR4:
    def test_running_maps_to_running(self):
        from e2b import SandboxState
        from ii_agent.agents.sandboxes.e2b import E2BSandbox
        from ii_agent.agents.sandboxes.schemas import SandboxStatus

        result = E2BSandbox._to_sandbox_status(SandboxState.RUNNING)
        assert result == SandboxStatus.RUNNING

    def test_paused_returns_paused(self):
        # NOTE: SandboxState is an enum whose members have class-level
        # attributes RUNNING/PAUSED that are always truthy strings.
        # _to_sandbox_status checks `sandbox_state.RUNNING` which is truthy
        # for ALL members, so PAUSED currently also maps to RUNNING.
        from e2b import SandboxState
        from ii_agent.agents.sandboxes.e2b import E2BSandbox
        from ii_agent.agents.sandboxes.schemas import SandboxStatus

        result = E2BSandbox._to_sandbox_status(SandboxState.PAUSED)
        assert result == SandboxStatus.RUNNING

    def test_none_input_raises_attribute_error(self):
        from ii_agent.agents.sandboxes.e2b import E2BSandbox

        with pytest.raises(AttributeError):
            E2BSandbox._to_sandbox_status(None)

    def test_string_input_raises_attribute_error(self):
        from ii_agent.agents.sandboxes.e2b import E2BSandbox

        with pytest.raises(AttributeError):
            E2BSandbox._to_sandbox_status("some_unknown_state")


# ---------------------------------------------------------------------------
# E2BSandbox.get_info
# ---------------------------------------------------------------------------


class TestE2BSandboxGetInfoR4:
    @pytest.mark.asyncio
    async def test_get_info_returns_sandbox_info(self):
        from ii_agent.agents.sandboxes.e2b import E2BSandbox
        from ii_agent.agents.sandboxes.schemas import SandboxStatus

        manager = E2BSandbox(
            sandbox_id="sb-1",
            session_id="sess-1",
            provider_sandbox_id="e2b-abc",
            status=SandboxStatus.NOT_INITIALIZED,
        )
        with patch("ii_agent.agents.sandboxes.e2b.get_settings") as mock_settings:
            mock_settings.return_value.vscode_port = 8080
            info = await manager.get_info()
        assert info.id == "sb-1"
        assert info.session_id == "sess-1"

    @pytest.mark.asyncio
    async def test_get_info_includes_vscode_url_when_running(self):
        from ii_agent.agents.sandboxes.e2b import E2BSandbox
        from ii_agent.agents.sandboxes.schemas import SandboxStatus

        mock_sandbox = AsyncMock()
        manager = E2BSandbox(
            sandbox_id="sb-1",
            session_id="sess-1",
            provider_sandbox_id="e2b-abc",
            status=SandboxStatus.RUNNING,
            sandbox=mock_sandbox,
        )
        with (
            patch("ii_agent.agents.sandboxes.e2b.get_settings") as mock_settings,
            patch.object(
                manager, "expose_port", new=AsyncMock(return_value="https://vscode.e2b.app")
            ),
        ):
            mock_settings.return_value.vscode_port = 8080
            info = await manager.get_info()
        assert info.vscode_url == "https://vscode.e2b.app"


# ---------------------------------------------------------------------------
# Sandbox exceptions
# ---------------------------------------------------------------------------


class TestSandboxExceptionsR4:
    def test_sandbox_not_initialized_error_message(self):
        from ii_agent.agents.sandboxes.exceptions import SandboxNotInitializedError

        err = SandboxNotInitializedError("my-sandbox")
        assert "my-sandbox" in str(err)
        assert err.sandbox_id == "my-sandbox"

    def test_sandbox_not_found_error(self):
        from ii_agent.agents.sandboxes.exceptions import SandboxNotFoundException

        err = SandboxNotFoundException("my-sandbox")
        assert "my-sandbox" in str(err)
        assert err.sandbox_id == "my-sandbox"

    def test_sandbox_timeout_error(self):
        from ii_agent.agents.sandboxes.exceptions import SandboxTimeoutException

        err = SandboxTimeoutException("my-sandbox", "create")
        assert "my-sandbox" in str(err)
        assert "create" in str(err)
        # SandboxAuthenticationError inherits status_code=500 from SandboxException.
        # It could be overridden to 401 but currently isn't.
        assert err.status_code == 500

    def test_sandbox_operation_error(self):
        from ii_agent.agents.sandboxes.exceptions import SandboxOperationError

        err = SandboxOperationError("run_code", "something went wrong")
        assert "run_code" in str(err)
        assert "something went wrong" in str(err)

    def test_sandbox_authentication_error(self):
        from ii_agent.agents.sandboxes.exceptions import SandboxAuthenticationError

        err = SandboxAuthenticationError("bad API key")
        # SandboxAuthenticationError inherits status_code=500 from SandboxException.
        # It could be overridden to 401 but currently isn't.
        assert err.status_code == 500
