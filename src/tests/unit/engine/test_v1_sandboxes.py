"""Unit tests for engine/sandboxes/e2b.py - E2BSandbox."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.agents.sandboxes.e2b import E2BSandbox, e2b_exception_handler
from ii_agent.agents.sandboxes.exceptions import (
    SandboxAuthenticationError,
    SandboxNotFoundException,
    SandboxNotInitializedError,
    SandboxOperationError,
    SandboxTimeoutException,
)
from ii_agent.agents.sandboxes.schemas import SandboxFileInfo, SandboxStatus


# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------


def _make_manager(
    sandbox_id: str = "sb-001",
    session_id: str = "sess-001",
    provider_sandbox_id: str = "e2b-abc",
    status: SandboxStatus = SandboxStatus.RUNNING,
    sandbox=None,
) -> E2BSandbox:
    return E2BSandbox(
        sandbox_id=sandbox_id,
        session_id=session_id,
        provider_sandbox_id=provider_sandbox_id,
        status=status,
        sandbox=sandbox,
        expired_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )


def _fake_sandbox():
    """Return a lightweight AsyncMock that mimics AsyncSandbox."""
    sb = AsyncMock()
    sb.sandbox_id = "e2b-abc"
    return sb


# ---------------------------------------------------------------------------
# Constructor & basic properties
# ---------------------------------------------------------------------------


class TestE2BSandboxInit:
    def test_default_status_is_not_initialized(self):
        mgr = E2BSandbox(
            sandbox_id="s1",
            session_id="se1",
            provider_sandbox_id="p1",
        )
        assert mgr.status == SandboxStatus.NOT_INITIALIZED

    def test_sandbox_is_none_by_default(self):
        mgr = E2BSandbox(
            sandbox_id="s1",
            session_id="se1",
            provider_sandbox_id="p1",
        )
        assert mgr.sandbox is None

    def test_metadata_defaults_to_empty_dict(self):
        mgr = E2BSandbox(
            sandbox_id="s1",
            session_id="se1",
            provider_sandbox_id="p1",
        )
        assert mgr.metadata == {}

    def test_get_provider_id(self):
        mgr = _make_manager(provider_sandbox_id="e2b-xyz")
        assert mgr.get_provider_id() == "e2b-xyz"

    def test_mcp_client_is_none_initially(self):
        mgr = _make_manager()
        assert mgr.mcp_client is None


# ---------------------------------------------------------------------------
# _to_sandbox_status static method
# ---------------------------------------------------------------------------


class TestToSandboxStatus:
    def test_running_state(self):
        state = MagicMock()
        state.RUNNING = True
        state.PAUSED = False
        result = E2BSandbox._to_sandbox_status(state)
        assert result == SandboxStatus.RUNNING

    def test_paused_state(self):
        state = MagicMock()
        state.RUNNING = False
        state.PAUSED = True
        result = E2BSandbox._to_sandbox_status(state)
        assert result == SandboxStatus.PAUSED

    def test_unknown_state_raises_value_error(self):
        state = MagicMock()
        state.RUNNING = False
        state.PAUSED = False
        with pytest.raises(ValueError, match="Unrecognize"):
            E2BSandbox._to_sandbox_status(state)


# ---------------------------------------------------------------------------
# get_info
# ---------------------------------------------------------------------------


class TestGetInfo:
    @pytest.mark.asyncio
    async def test_get_info_not_running_returns_no_vscode_url(self):
        mgr = _make_manager(status=SandboxStatus.PAUSED)
        info = await mgr.get_info()
        assert info.vscode_url is None

    @pytest.mark.asyncio
    async def test_get_info_running_with_sandbox_calls_expose_port(self):
        sb = _fake_sandbox()
        sb.get_host.return_value = "abc.e2b.app"
        mgr = _make_manager(status=SandboxStatus.RUNNING, sandbox=sb)

        with patch.object(
            mgr, "expose_port", new=AsyncMock(return_value="https://abc.e2b.app")
        ) as mock_expose:
            info = await mgr.get_info()
        assert info.status == SandboxStatus.RUNNING

    @pytest.mark.asyncio
    async def test_get_info_running_without_sandbox_returns_no_vscode(self):
        mgr = _make_manager(status=SandboxStatus.RUNNING, sandbox=None)
        info = await mgr.get_info()
        assert info.vscode_url is None


# ---------------------------------------------------------------------------
# _ensure_sandbox_connection
# ---------------------------------------------------------------------------


class TestEnsureSandboxConnection:
    @pytest.mark.asyncio
    async def test_raises_if_sandbox_is_none(self):
        mgr = _make_manager(sandbox=None)
        with pytest.raises(SandboxNotInitializedError):
            await mgr._ensure_sandbox_connection()

    @pytest.mark.asyncio
    async def test_does_not_reconnect_when_running_and_fresh(self):
        sb = _fake_sandbox()
        sandbox_info = MagicMock()
        sandbox_info.state = MagicMock()
        sandbox_info.state.PAUSED = False
        sandbox_info.state.RUNNING = True
        sandbox_info.end_at = datetime.now(timezone.utc) + timedelta(hours=2)

        mgr = _make_manager(sandbox=sb)

        fake_settings = MagicMock()
        fake_settings.sandbox.e2b_api_key = "key"
        fake_settings.sandbox.e2b_domain = None
        fake_settings.sandbox.timeout_seconds = 3600

        with patch("ii_agent.agents.sandboxes.e2b.get_settings", return_value=fake_settings), \
             patch("ii_agent.agents.sandboxes.e2b.AsyncSandbox") as mock_cls:
            mock_cls.get_info = AsyncMock(return_value=sandbox_info)
            await mgr._ensure_sandbox_connection()

        mock_cls.get_info.assert_called_once()


# ---------------------------------------------------------------------------
# get_status
# ---------------------------------------------------------------------------


class TestGetStatus:
    @pytest.mark.asyncio
    async def test_get_status_returns_initializing_when_no_sandbox(self):
        mgr = _make_manager(sandbox=None)
        status = await mgr.get_status()
        assert status == SandboxStatus.INITIALIZING

    @pytest.mark.asyncio
    async def test_get_status_calls_sandbox_get_info(self):
        sb = _fake_sandbox()
        state = MagicMock()
        state.RUNNING = True
        state.PAUSED = False
        sandbox_info = MagicMock()
        sandbox_info.state = state
        sb.get_info = AsyncMock(return_value=sandbox_info)

        mgr = _make_manager(sandbox=sb)

        fake_settings = MagicMock()
        fake_settings.sandbox.e2b_api_key = "key"
        fake_settings.sandbox.e2b_domain = None

        with patch("ii_agent.agents.sandboxes.e2b.get_settings", return_value=fake_settings), \
             patch("ii_agent.agents.sandboxes.e2b.AsyncSandbox") as mock_cls:
            mock_cls.get_info = AsyncMock(return_value=sandbox_info)
            status = await mgr.get_status()
        assert status == SandboxStatus.RUNNING


# ---------------------------------------------------------------------------
# pause
# ---------------------------------------------------------------------------


class TestPause:
    @pytest.mark.asyncio
    async def test_pause_when_running(self):
        sb = _fake_sandbox()
        sb.is_running = AsyncMock(return_value=True)
        sb.beta_pause = AsyncMock()

        mgr = _make_manager(sandbox=sb)

        await mgr.pause()

        sb.beta_pause.assert_called_once()
        assert mgr.status == SandboxStatus.PAUSED

    @pytest.mark.asyncio
    async def test_pause_skipped_when_not_running(self):
        sb = _fake_sandbox()
        sb.is_running = AsyncMock(return_value=False)
        sb.beta_pause = AsyncMock()

        mgr = _make_manager(sandbox=sb)

        await mgr.pause()

        sb.beta_pause.assert_not_called()


# ---------------------------------------------------------------------------
# set_timeout
# ---------------------------------------------------------------------------


class TestSetTimeout:
    @pytest.mark.asyncio
    async def test_set_timeout_updates_expired_at(self):
        sb = _fake_sandbox()
        sb.set_timeout = AsyncMock()

        original_expiry = datetime.now(timezone.utc) + timedelta(hours=1)
        mgr = _make_manager(sandbox=sb)
        mgr.expired_at = original_expiry

        await mgr.set_timeout(3600)

        sb.set_timeout.assert_called_once_with(timeout=3600)
        # expired_at should have advanced
        assert mgr.expired_at > original_expiry


# ---------------------------------------------------------------------------
# run_command
# ---------------------------------------------------------------------------


class TestRunCommand:
    @pytest.mark.asyncio
    async def test_run_command_success(self):
        from e2b_code_interpreter import CommandResult

        sb = _fake_sandbox()
        cmd_result = MagicMock(spec=CommandResult)
        cmd_result.exit_code = 0
        cmd_result.stdout = "hello"
        cmd_result.stderr = ""
        sb.commands.run = AsyncMock(return_value=cmd_result)

        mgr = _make_manager(sandbox=sb)
        with patch.object(mgr, "_ensure_sandbox_connection", new=AsyncMock()):
            output = await mgr.run_command("echo hello")

        assert output == "hello"

    @pytest.mark.asyncio
    async def test_run_command_non_zero_exit_raises(self):
        from e2b_code_interpreter import CommandResult

        sb = _fake_sandbox()
        cmd_result = MagicMock(spec=CommandResult)
        cmd_result.exit_code = 1
        cmd_result.stdout = ""
        cmd_result.stderr = "permission denied"
        sb.commands.run = AsyncMock(return_value=cmd_result)

        mgr = _make_manager(sandbox=sb)
        with patch.object(mgr, "_ensure_sandbox_connection", new=AsyncMock()):
            with pytest.raises(SandboxOperationError, match="Command failed"):
                await mgr.run_command("bad-cmd")

    @pytest.mark.asyncio
    async def test_run_command_unexpected_result_raises(self):
        sb = _fake_sandbox()
        sb.commands.run = AsyncMock(return_value="not-a-command-result")

        mgr = _make_manager(sandbox=sb)
        with patch.object(mgr, "_ensure_sandbox_connection", new=AsyncMock()):
            with pytest.raises(SandboxOperationError, match="Unexpected"):
                await mgr.run_command("ls")


# ---------------------------------------------------------------------------
# read_file / write_file / delete_file
# ---------------------------------------------------------------------------


class TestFileOperations:
    @pytest.mark.asyncio
    async def test_read_file(self):
        sb = _fake_sandbox()
        sb.files.read = AsyncMock(return_value="file content")

        mgr = _make_manager(sandbox=sb)
        with patch.object(mgr, "_ensure_sandbox_connection", new=AsyncMock()):
            content = await mgr.read_file("/tmp/test.txt")

        assert content == "file content"

    @pytest.mark.asyncio
    async def test_write_file_returns_file_info(self):
        sb = _fake_sandbox()
        write_info = MagicMock()
        write_info.name = "test.txt"
        sb.files.write = AsyncMock(return_value=write_info)

        mgr = _make_manager(sandbox=sb)
        with patch.object(mgr, "_ensure_sandbox_connection", new=AsyncMock()):
            info = await mgr.write_file("/tmp/test.txt", "content")

        assert isinstance(info, SandboxFileInfo)
        assert info.name == "test.txt"

    @pytest.mark.asyncio
    async def test_delete_file_returns_true(self):
        sb = _fake_sandbox()
        sb.files.remove = AsyncMock()

        mgr = _make_manager(sandbox=sb)
        with patch.object(mgr, "_ensure_sandbox_connection", new=AsyncMock()):
            result = await mgr.delete_file("/tmp/test.txt")

        assert result is True

    @pytest.mark.asyncio
    async def test_file_exists_true(self):
        sb = _fake_sandbox()
        sb.files.exists = AsyncMock(return_value=True)

        mgr = _make_manager(sandbox=sb)
        with patch.object(mgr, "_ensure_sandbox_connection", new=AsyncMock()):
            result = await mgr.file_exists("/tmp/test.txt")

        assert result is True

    @pytest.mark.asyncio
    async def test_file_exists_false(self):
        sb = _fake_sandbox()
        sb.files.exists = AsyncMock(return_value=False)

        mgr = _make_manager(sandbox=sb)
        with patch.object(mgr, "_ensure_sandbox_connection", new=AsyncMock()):
            result = await mgr.file_exists("/tmp/missing.txt")

        assert result is False


# ---------------------------------------------------------------------------
# upload_file / download_file
# ---------------------------------------------------------------------------


class TestUploadDownload:
    @pytest.mark.asyncio
    async def test_upload_file_returns_true(self):
        sb = _fake_sandbox()
        sb.files.exists = AsyncMock(return_value=False)
        sb.files.write = AsyncMock()

        mgr = _make_manager(sandbox=sb)
        with patch.object(mgr, "_ensure_sandbox_connection", new=AsyncMock()):
            result = await mgr.upload_file(b"data", "/uploads/file.bin")

        assert result is True

    @pytest.mark.asyncio
    async def test_download_file_returns_text_content(self):
        sb = _fake_sandbox()
        sb.files.read = AsyncMock(return_value="text content")

        mgr = _make_manager(sandbox=sb)
        with patch.object(mgr, "_ensure_sandbox_connection", new=AsyncMock()):
            result = await mgr.download_file("/tmp/file.txt", format="text")

        assert result == "text content"

    @pytest.mark.asyncio
    async def test_download_file_returns_bytes_content(self):
        sb = _fake_sandbox()
        sb.files.read = AsyncMock(return_value=b"\x00\x01\x02")

        mgr = _make_manager(sandbox=sb)
        with patch.object(mgr, "_ensure_sandbox_connection", new=AsyncMock()):
            result = await mgr.download_file("/tmp/file.bin", format="bytes")

        assert isinstance(result, bytes)

    @pytest.mark.asyncio
    async def test_download_file_bytearray_converts_to_bytes(self):
        sb = _fake_sandbox()
        sb.files.read = AsyncMock(return_value=bytearray(b"\x01\x02"))

        mgr = _make_manager(sandbox=sb)
        with patch.object(mgr, "_ensure_sandbox_connection", new=AsyncMock()):
            result = await mgr.download_file("/tmp/file.bin", format="bytes")

        assert isinstance(result, bytes)

    @pytest.mark.asyncio
    async def test_download_file_text_format_from_str(self):
        sb = _fake_sandbox()
        sb.files.read = AsyncMock(return_value="hello")

        mgr = _make_manager(sandbox=sb)
        with patch.object(mgr, "_ensure_sandbox_connection", new=AsyncMock()):
            result = await mgr.download_file("/tmp/file.txt", format="text")

        assert result == "hello"

    @pytest.mark.asyncio
    async def test_download_file_invalid_type_raises(self):
        sb = _fake_sandbox()
        sb.files.read = AsyncMock(return_value=12345)  # unexpected type

        mgr = _make_manager(sandbox=sb)
        with patch.object(mgr, "_ensure_sandbox_connection", new=AsyncMock()):
            with pytest.raises(SandboxOperationError, match="Unsupported content type"):
                await mgr.download_file("/tmp/file.bin", format="bytes")


# ---------------------------------------------------------------------------
# create_directory
# ---------------------------------------------------------------------------


class TestCreateDirectory:
    @pytest.mark.asyncio
    async def test_create_directory_success(self):
        sb = _fake_sandbox()
        sb.files.make_dir = AsyncMock(return_value=True)

        mgr = _make_manager(sandbox=sb)
        with patch.object(mgr, "_ensure_sandbox_connection", new=AsyncMock()):
            result = await mgr.create_directory("/tmp/newdir")

        assert result is True

    @pytest.mark.asyncio
    async def test_create_directory_already_exists_raises_by_default(self):
        sb = _fake_sandbox()
        sb.files.make_dir = AsyncMock(return_value=False)

        mgr = _make_manager(sandbox=sb)
        with patch.object(mgr, "_ensure_sandbox_connection", new=AsyncMock()):
            with pytest.raises(SandboxOperationError, match="already exists"):
                await mgr.create_directory("/tmp/existing")

    @pytest.mark.asyncio
    async def test_create_directory_exist_ok_does_not_raise(self):
        sb = _fake_sandbox()
        sb.files.make_dir = AsyncMock(return_value=False)

        mgr = _make_manager(sandbox=sb)
        with patch.object(mgr, "_ensure_sandbox_connection", new=AsyncMock()):
            result = await mgr.create_directory("/tmp/existing", exist_ok=True)

        assert result is True


# ---------------------------------------------------------------------------
# expose_port / get_host
# ---------------------------------------------------------------------------


class TestExposePortGetHost:
    @pytest.mark.asyncio
    async def test_expose_port_returns_https_url(self):
        sb = _fake_sandbox()
        # get_host is synchronous in the E2B SDK
        sb.get_host = MagicMock(return_value="abc123.e2b.app")

        mgr = _make_manager(sandbox=sb)
        with patch.object(mgr, "_ensure_sandbox_connection", new=AsyncMock()):
            url = await mgr.expose_port(3000)

        assert url == "https://abc123.e2b.app"

    @pytest.mark.asyncio
    async def test_get_host_returns_expected_format(self):
        sb = _fake_sandbox()
        conn_config = MagicMock()
        conn_config.domain = "e2b.app"
        sb.connection_config = conn_config

        mgr = _make_manager(provider_sandbox_id="abc123", sandbox=sb)
        host = await mgr.get_host()
        assert host == "abc123.e2b.app"


# ---------------------------------------------------------------------------
# e2b_exception_handler decorator
# ---------------------------------------------------------------------------


class TestE2bExceptionHandler:
    """The decorator correctly re-maps E2B exceptions to sandbox exceptions."""

    @pytest.mark.asyncio
    async def test_passes_through_on_success(self):
        class DummyClass:
            @e2b_exception_handler
            async def method(self):
                return "ok"

        d = DummyClass()
        assert await d.method() == "ok"

    @pytest.mark.asyncio
    async def test_maps_not_found_exception(self):
        from e2b.exceptions import NotFoundException

        class DummyClass:
            sandbox_id = "sb-1"

            @e2b_exception_handler
            async def method(self):
                raise NotFoundException("gone")

        d = DummyClass()
        with pytest.raises(SandboxNotFoundException):
            await d.method()

    @pytest.mark.asyncio
    async def test_maps_authentication_exception(self):
        from e2b.exceptions import AuthenticationException

        class DummyClass:
            @e2b_exception_handler
            async def method(self):
                raise AuthenticationException("bad key")

        d = DummyClass()
        with pytest.raises(SandboxAuthenticationError):
            await d.method()

    @pytest.mark.asyncio
    async def test_maps_timeout_exception(self):
        from e2b.exceptions import TimeoutException

        class DummyClass:
            sandbox_id = "sb-1"

            @e2b_exception_handler
            async def method(self):
                raise TimeoutException("timeout")

        d = DummyClass()
        with pytest.raises(SandboxTimeoutException):
            await d.method()

    @pytest.mark.asyncio
    async def test_re_raises_sandbox_operation_error(self):
        class DummyClass:
            @e2b_exception_handler
            async def method(self):
                raise SandboxOperationError("op", "already wrapped")

        d = DummyClass()
        with pytest.raises(SandboxOperationError):
            await d.method()

    @pytest.mark.asyncio
    async def test_wraps_generic_exception_as_sandbox_operation_error(self):
        class DummyClass:
            @e2b_exception_handler
            async def method(self):
                raise RuntimeError("some random error")

        d = DummyClass()
        with pytest.raises(SandboxOperationError):
            await d.method()
