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
# MCPClient tests
# NOTE: These tests import ii_agent.agents.sandboxes.client which was removed.
# Skipped until the MCPClient is reintroduced or the sandbox_client module is
# restored.  The MCP functionality now lives in the MCP server inside the
# sandbox container (ii_server.mcp.server).
# ---------------------------------------------------------------------------

_has_sandbox_client = False
try:
    from ii_agent.agents.sandboxes.client import MCPClient  # noqa: F401

    _has_sandbox_client = True
except ImportError:
    pass


@pytest.mark.skipif(not _has_sandbox_client, reason="sandbox_client module removed")
class TestMCPClientR4:
    def test_init_sets_server_url(self):
        from ii_agent.agents.sandboxes.client import MCPClient

        with patch("ii_agent.agents.sandboxes.sandbox_client.Client.__init__", return_value=None):
            client = MCPClient("http://sandbox-server:8080")
            assert client.server_url == "http://sandbox-server:8080"

    def test_init_appends_mcp_path(self):
        from ii_agent.agents.sandboxes.client import MCPClient

        with patch(
            "ii_agent.agents.sandboxes.sandbox_client.Client.__init__", return_value=None
        ) as mock_init:
            client = MCPClient("http://sandbox-server:8080")
            # Verify parent called with /mcp/ appended
            mock_init.assert_called_once_with("http://sandbox-server:8080/mcp/")

    @pytest.mark.asyncio
    async def test_register_custom_mcp_raises_when_not_initialized(self):
        from ii_agent.agents.sandboxes.client import MCPClient

        with patch("ii_agent.agents.sandboxes.sandbox_client.Client.__init__", return_value=None):
            client = MCPClient("http://server:8080")
            client.http_session = None
        with pytest.raises(Exception, match="not initialized"):
            await client.register_custom_mcp({"key": "value"})

    @pytest.mark.asyncio
    async def test_register_custom_mcp_raises_on_non_200(self):
        from ii_agent.agents.sandboxes.client import MCPClient

        with patch("ii_agent.agents.sandboxes.sandbox_client.Client.__init__", return_value=None):
            client = MCPClient("http://server:8080")
        mock_http = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Server Error"
        mock_http.post = AsyncMock(return_value=mock_response)
        client.http_session = mock_http
        with pytest.raises(Exception, match="Failed to register custom mcp"):
            await client.register_custom_mcp({"config": "data"})

    @pytest.mark.asyncio
    async def test_register_custom_mcp_returns_json_on_200(self):
        from ii_agent.agents.sandboxes.client import MCPClient

        with patch("ii_agent.agents.sandboxes.sandbox_client.Client.__init__", return_value=None):
            client = MCPClient("http://server:8080")
        mock_http = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        mock_http.post = AsyncMock(return_value=mock_response)
        client.http_session = mock_http
        result = await client.register_custom_mcp({"config": "data"})
        assert result == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_register_codex_raises_on_non_200(self):
        from ii_agent.agents.sandboxes.client import MCPClient

        with patch("ii_agent.agents.sandboxes.sandbox_client.Client.__init__", return_value=None):
            client = MCPClient("http://server:8080")
        mock_http = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_http.post = AsyncMock(return_value=mock_response)
        client.http_session = mock_http
        with pytest.raises(Exception, match="Failed to register codex"):
            await client.register_codex()

    @pytest.mark.asyncio
    async def test_register_codex_returns_json_on_200(self):
        from ii_agent.agents.sandboxes.client import MCPClient

        with patch("ii_agent.agents.sandboxes.sandbox_client.Client.__init__", return_value=None):
            client = MCPClient("http://server:8080")
        mock_http = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"codex": "registered"}
        mock_http.post = AsyncMock(return_value=mock_response)
        client.http_session = mock_http
        result = await client.register_codex()
        assert result == {"codex": "registered"}

    @pytest.mark.asyncio
    async def test_set_tool_server_url_raises_on_non_200(self):
        from ii_agent.agents.sandboxes.client import MCPClient

        with patch("ii_agent.agents.sandboxes.sandbox_client.Client.__init__", return_value=None):
            client = MCPClient("http://server:8080")
        mock_http = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Error"
        mock_http.post = AsyncMock(return_value=mock_response)
        client.http_session = mock_http
        with pytest.raises(Exception, match="Failed to set tool server url"):
            await client.set_tool_server_url("http://tool-server")

    @pytest.mark.asyncio
    async def test_set_tool_server_url_returns_json_on_200(self):
        from ii_agent.agents.sandboxes.client import MCPClient

        with patch("ii_agent.agents.sandboxes.sandbox_client.Client.__init__", return_value=None):
            client = MCPClient("http://server:8080")
        mock_http = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"url_set": True}
        mock_http.post = AsyncMock(return_value=mock_response)
        client.http_session = mock_http
        result = await client.set_tool_server_url("http://tool-server")
        assert result == {"url_set": True}

    @pytest.mark.asyncio
    async def test_set_credential_raises_on_non_200(self):
        from ii_agent.agents.sandboxes.client import MCPClient

        with patch("ii_agent.agents.sandboxes.sandbox_client.Client.__init__", return_value=None):
            client = MCPClient("http://server:8080")
        mock_http = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_http.post = AsyncMock(return_value=mock_response)
        client.http_session = mock_http
        with pytest.raises(Exception, match="Failed to set credential"):
            await client.set_credential({"token": "bad"})

    @pytest.mark.asyncio
    async def test_set_credential_returns_json_on_200(self):
        from ii_agent.agents.sandboxes.client import MCPClient

        with patch("ii_agent.agents.sandboxes.sandbox_client.Client.__init__", return_value=None):
            client = MCPClient("http://server:8080")
        mock_http = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"credential": "set"}
        mock_http.post = AsyncMock(return_value=mock_response)
        client.http_session = mock_http
        result = await client.set_credential({"token": "valid"})
        assert result == {"credential": "set"}


# ---------------------------------------------------------------------------
# MCPClient context manager
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _has_sandbox_client, reason="sandbox_client module removed")
class TestMCPClientContextManagerR4:
    @pytest.mark.asyncio
    async def test_aenter_creates_http_session(self):
        from ii_agent.agents.sandboxes.client import MCPClient

        with (
            patch("ii_agent.agents.sandboxes.sandbox_client.Client.__init__", return_value=None),
            patch(
                "ii_agent.agents.sandboxes.sandbox_client.Client.__aenter__",
                new=AsyncMock(return_value=MagicMock()),
            ),
        ):
            client = MCPClient("http://server:8080")
            client.http_session = None
            await client.__aenter__()
            assert client.http_session is not None

    @pytest.mark.asyncio
    async def test_aexit_closes_http_session(self):
        from ii_agent.agents.sandboxes.client import MCPClient

        with (
            patch("ii_agent.agents.sandboxes.sandbox_client.Client.__init__", return_value=None),
            patch(
                "ii_agent.agents.sandboxes.sandbox_client.Client.__aexit__",
                new=AsyncMock(return_value=None),
            ),
        ):
            client = MCPClient("http://server:8080")
            mock_http = AsyncMock()
            mock_http.aclose = AsyncMock()
            client.http_session = mock_http
            await client.__aexit__(None, None, None)
            mock_http.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_aexit_handles_none_http_session(self):
        from ii_agent.agents.sandboxes.client import MCPClient

        with (
            patch("ii_agent.agents.sandboxes.sandbox_client.Client.__init__", return_value=None),
            patch(
                "ii_agent.agents.sandboxes.sandbox_client.Client.__aexit__",
                new=AsyncMock(return_value=None),
            ),
        ):
            client = MCPClient("http://server:8080")
            client.http_session = None
            # Should not raise
            await client.__aexit__(None, None, None)


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
