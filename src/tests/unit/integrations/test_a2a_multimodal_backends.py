"""Unit tests for ClaudeCodeBackend and CopilotBackend multimodal image handling."""

from __future__ import annotations

import base64
import logging
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

a2a_types = pytest.importorskip("a2a.types", reason="a2a-sdk not installed")

from a2a.types import (  # noqa: E402
    FilePart,
    FileWithBytes,
    FileWithUri,
    Part,
    TextPart,
)

from ii_agent.integrations.a2a.claude_code_backend import (  # noqa: E402
    ClaudeCodeBackend,
    ClaudeCodeConfig,
    _cleanup_temp_files,
    _extract_image_paths_from_parts,
)
from ii_agent.integrations.a2a.codex_backend import CodexBackend, CodexConfig  # noqa: E402
from ii_agent.integrations.a2a.copilot_backend import (  # noqa: E402
    CopilotBackend,
    CopilotConfig,
    _parts_to_attachments,
)


class TestExtractImagePathsFromParts:
    def test_none_parts_returns_empty(self):
        paths, temps = _extract_image_paths_from_parts(None)
        assert paths == []
        assert temps == []

    def test_empty_list_returns_empty(self):
        paths, temps = _extract_image_paths_from_parts([])
        assert paths == []
        assert temps == []

    def test_text_part_ignored(self):
        parts = [Part(root=TextPart(text="hello"))]
        paths, temps = _extract_image_paths_from_parts(parts)
        assert paths == []
        assert temps == []

    def test_file_uri_with_file_scheme(self):
        parts = [
            Part(
                root=FilePart(
                    file=FileWithUri(name="img", uri="file:///tmp/test.png", mime_type="image/png")
                )
            )
        ]
        paths, temps = _extract_image_paths_from_parts(parts)
        assert paths == ["/tmp/test.png"]
        assert temps == []

    def test_file_with_bytes_creates_temp_file(self):
        raw = b"fake-png-data"
        b64 = base64.b64encode(raw).decode()
        parts = [
            Part(root=FilePart(file=FileWithBytes(name="img", bytes=b64, mime_type="image/png")))
        ]
        paths, temps = _extract_image_paths_from_parts(parts)
        assert len(paths) == 1
        assert len(temps) == 1
        assert paths[0] == temps[0]
        # Verify temp file was written correctly
        with open(temps[0], "rb") as f:
            assert f.read() == raw
        assert temps[0].endswith(".png")
        # Cleanup
        _cleanup_temp_files(temps)
        assert not os.path.exists(temps[0])

    def test_jpeg_extension(self):
        b64 = base64.b64encode(b"data").decode()
        parts = [
            Part(root=FilePart(file=FileWithBytes(name="img", bytes=b64, mime_type="image/jpeg")))
        ]
        paths, temps = _extract_image_paths_from_parts(parts)
        assert temps[0].endswith(".jpg")
        _cleanup_temp_files(temps)

    def test_webp_extension(self):
        b64 = base64.b64encode(b"data").decode()
        parts = [
            Part(root=FilePart(file=FileWithBytes(name="img", bytes=b64, mime_type="image/webp")))
        ]
        paths, temps = _extract_image_paths_from_parts(parts)
        assert temps[0].endswith(".webp")
        _cleanup_temp_files(temps)

    def test_non_image_file_skipped(self):
        parts = [
            Part(
                root=FilePart(
                    file=FileWithUri(
                        name="doc", uri="file:///tmp/doc.pdf", mime_type="application/pdf"
                    )
                )
            )
        ]
        paths, temps = _extract_image_paths_from_parts(parts)
        assert paths == []
        assert temps == []

    def test_remote_url_skipped(self):
        parts = [
            Part(
                root=FilePart(
                    file=FileWithUri(
                        name="img", uri="https://example.com/img.png", mime_type="image/png"
                    )
                )
            )
        ]
        paths, temps = _extract_image_paths_from_parts(parts)
        assert paths == []
        assert temps == []

    def test_multiple_images_mixed(self):
        b64 = base64.b64encode(b"bytes").decode()
        parts = [
            Part(root=TextPart(text="describe these")),
            Part(
                root=FilePart(
                    file=FileWithUri(name="img1", uri="file:///tmp/a.png", mime_type="image/png")
                )
            ),
            Part(root=FilePart(file=FileWithBytes(name="img2", bytes=b64, mime_type="image/gif"))),
        ]
        paths, temps = _extract_image_paths_from_parts(parts)
        assert len(paths) == 2
        assert paths[0] == "/tmp/a.png"
        assert len(temps) == 1
        assert temps[0].endswith(".gif")
        _cleanup_temp_files(temps)


class TestCleanupTempFiles:
    def test_removes_existing_files(self):
        fd, path = tempfile.mkstemp()
        os.close(fd)
        assert os.path.exists(path)
        _cleanup_temp_files([path])
        assert not os.path.exists(path)

    def test_ignores_missing_files(self):
        # Should not raise
        _cleanup_temp_files(["/tmp/nonexistent_a2a_test_file_xyz"])

    def test_empty_list(self):
        _cleanup_temp_files([])


# ---------------------------------------------------------------------------
# Copilot SDK attachment conversion
# ---------------------------------------------------------------------------


class TestPartsToAttachments:
    """Test _parts_to_attachments for Copilot SDK image forwarding."""

    def test_none_parts_returns_empty(self):
        attachments, temps = _parts_to_attachments(None)
        assert attachments == []
        assert temps == []

    def test_empty_list_returns_empty(self):
        attachments, temps = _parts_to_attachments([])
        assert attachments == []
        assert temps == []

    def test_text_part_ignored(self):
        parts = [Part(root=TextPart(text="hello"))]
        attachments, temps = _parts_to_attachments(parts)
        assert attachments == []
        assert temps == []

    def test_file_uri_with_file_scheme_produces_file_attachment(self):
        parts = [
            Part(
                root=FilePart(
                    file=FileWithUri(name="img", uri="file:///tmp/test.png", mime_type="image/png")
                )
            )
        ]
        attachments, temps = _parts_to_attachments(parts)
        assert len(attachments) == 1
        assert attachments[0] == {"type": "file", "path": "/tmp/test.png"}
        assert temps == []

    def test_file_with_bytes_produces_file_attachment(self):
        raw = b"fake-png-data"
        b64 = base64.b64encode(raw).decode()
        parts = [
            Part(root=FilePart(file=FileWithBytes(name="img", bytes=b64, mime_type="image/png")))
        ]
        attachments, temps = _parts_to_attachments(parts)
        assert len(attachments) == 1
        # SDK has no blob type; bytes are written to a temp file
        assert attachments[0]["type"] == "file"
        assert attachments[0]["path"].endswith(".png")
        assert len(temps) == 1  # temp file path tracked for cleanup
        # Verify the temp file contains the decoded data
        import os

        assert os.path.exists(temps[0])
        with open(temps[0], "rb") as f:
            assert f.read() == raw
        # Cleanup
        for p in temps:
            os.unlink(p)

    def test_remote_url_downloaded(self):
        """Remote HTTP URLs should be downloaded to temp files."""
        import unittest.mock as mock

        fake_response = mock.MagicMock()
        fake_response.content = b"fake-image-bytes"
        fake_response.raise_for_status = mock.MagicMock()

        parts = [
            Part(
                root=FilePart(
                    file=FileWithUri(
                        name="img", uri="https://example.com/img.png", mime_type="image/png"
                    )
                )
            )
        ]
        with mock.patch("httpx.get", return_value=fake_response) as mock_get:
            attachments, temps = _parts_to_attachments(parts)

        mock_get.assert_called_once_with(
            "https://example.com/img.png", timeout=30.0, follow_redirects=True
        )
        assert len(attachments) == 1
        assert attachments[0]["type"] == "file"
        assert attachments[0]["path"].endswith(".png")
        assert len(temps) == 1
        # Verify content was written
        with open(temps[0], "rb") as f:
            assert f.read() == b"fake-image-bytes"
        # Cleanup
        import os

        for p in temps:
            os.unlink(p)

    def test_remote_url_download_failure(self):
        """Failed remote URL download should be logged and skipped gracefully."""
        import unittest.mock as mock

        parts = [
            Part(
                root=FilePart(
                    file=FileWithUri(
                        name="img", uri="https://example.com/img.png", mime_type="image/png"
                    )
                )
            )
        ]
        with mock.patch("httpx.get", side_effect=Exception("connection refused")):
            attachments, temps = _parts_to_attachments(parts)

        assert attachments == []
        assert temps == []

    def test_non_image_file_skipped(self):
        parts = [
            Part(
                root=FilePart(
                    file=FileWithUri(
                        name="doc", uri="file:///tmp/doc.pdf", mime_type="application/pdf"
                    )
                )
            )
        ]
        attachments, temps = _parts_to_attachments(parts)
        assert attachments == []
        assert temps == []

    def test_multiple_images_mixed(self):
        b64 = base64.b64encode(b"bytes").decode()
        parts = [
            Part(root=TextPart(text="describe these")),
            Part(
                root=FilePart(
                    file=FileWithUri(name="img1", uri="file:///tmp/a.png", mime_type="image/png")
                )
            ),
            Part(root=FilePart(file=FileWithBytes(name="img2", bytes=b64, mime_type="image/gif"))),
        ]
        attachments, temps = _parts_to_attachments(parts)
        assert len(attachments) == 2
        assert attachments[0] == {"type": "file", "path": "/tmp/a.png"}
        # Second attachment is a temp file from bytes
        assert attachments[1]["type"] == "file"
        assert attachments[1]["path"].endswith(".gif")
        assert len(temps) == 1
        # Cleanup
        import os

        for p in temps:
            os.unlink(p)

    def test_jpeg_mime_accepted(self):
        b64 = base64.b64encode(b"data").decode()
        parts = [
            Part(root=FilePart(file=FileWithBytes(name="img", bytes=b64, mime_type="image/jpeg")))
        ]
        attachments, temps = _parts_to_attachments(parts)
        assert len(attachments) == 1
        assert attachments[0]["type"] == "file"
        assert attachments[0]["path"].endswith(".jpg")
        assert len(temps) == 1
        import os

        for p in temps:
            os.unlink(p)

    def test_webp_mime_accepted(self):
        b64 = base64.b64encode(b"data").decode()
        parts = [
            Part(root=FilePart(file=FileWithBytes(name="img", bytes=b64, mime_type="image/webp")))
        ]
        attachments, temps = _parts_to_attachments(parts)
        assert len(attachments) == 1
        assert attachments[0]["type"] == "file"
        assert attachments[0]["path"].endswith(".webp")
        assert len(temps) == 1
        import os

        for p in temps:
            os.unlink(p)


# ---------------------------------------------------------------------------
# Model steering: per-backend _build_cmd / session model override logic
# ---------------------------------------------------------------------------

# ─── ClaudeCodeBackend ──────────────────────────────────────────────


class TestClaudeCodeBackendModelSteering:
    def test_override_model_used_in_cmd(self):
        """Explicit model override must appear in the subprocess command."""
        cfg = ClaudeCodeConfig(api_key="key", model="claude-opus-4-20250514")
        backend = ClaudeCodeBackend(cfg)
        cmd = backend._build_cmd("hi", "ctx", model="claude-sonnet-4-20250514")
        idx = cmd.index("--model")
        assert cmd[idx + 1] == "claude-sonnet-4-20250514"

    def test_config_model_used_when_no_override(self):
        """When no override is provided, the config default appears in the command."""
        cfg = ClaudeCodeConfig(api_key="key", model="claude-opus-4-20250514")
        backend = ClaudeCodeBackend(cfg)
        cmd = backend._build_cmd("hi", "ctx")
        idx = cmd.index("--model")
        assert cmd[idx + 1] == "claude-opus-4-20250514"

    def test_empty_override_falls_back_to_config_model(self):
        """Empty string override must fall back to config model, not omit the flag."""
        cfg = ClaudeCodeConfig(api_key="key", model="claude-opus-4-20250514")
        backend = ClaudeCodeBackend(cfg)
        cmd = backend._build_cmd("hi", "ctx", model="")
        idx = cmd.index("--model")
        assert cmd[idx + 1] == "claude-opus-4-20250514"

    def test_model_flag_omitted_when_both_empty(self):
        """No --model flag when config model and override are both empty."""
        cfg = ClaudeCodeConfig(api_key="key", model="")
        backend = ClaudeCodeBackend(cfg)
        cmd = backend._build_cmd("hi", "ctx", model="")
        assert "--model" not in cmd


# ─── CodexBackend ───────────────────────────────────────────────────


class TestCodexBackendModelSteering:
    def test_override_model_used_in_cmd(self):
        """Explicit model override must appear in the subprocess command."""
        cfg = CodexConfig(api_key="key", model="o4-mini")
        backend = CodexBackend(cfg)
        cmd = backend._build_cmd("hi", "ctx", model="gpt-4o")
        idx = cmd.index("--model")
        assert cmd[idx + 1] == "gpt-4o"

    def test_config_model_used_when_no_override(self):
        """When no override is provided, the config default appears in the command."""
        cfg = CodexConfig(api_key="key", model="o4-mini")
        backend = CodexBackend(cfg)
        cmd = backend._build_cmd("hi", "ctx")
        idx = cmd.index("--model")
        assert cmd[idx + 1] == "o4-mini"

    def test_empty_override_falls_back_to_config_model(self):
        """Empty string override must fall back to config model."""
        cfg = CodexConfig(api_key="key", model="o3")
        backend = CodexBackend(cfg)
        cmd = backend._build_cmd("hi", "ctx", model="")
        idx = cmd.index("--model")
        assert cmd[idx + 1] == "o3"

    def test_model_flag_omitted_when_both_empty(self):
        """No --model flag when config model and override are both empty."""
        cfg = CodexConfig(api_key="key", model="")
        backend = CodexBackend(cfg)
        cmd = backend._build_cmd("hi", "ctx", model="")
        assert "--model" not in cmd


# ─── CopilotBackend ─────────────────────────────────────────────────


class TestCopilotBackendModelSteering:
    def _make_backend(self, config_model: str = "") -> tuple[CopilotBackend, MagicMock]:
        cfg = CopilotConfig(model=config_model)
        backend = CopilotBackend(cfg)
        mock_client = MagicMock()
        mock_session = MagicMock()
        mock_client.create_session = AsyncMock(return_value=mock_session)
        return backend, mock_client

    @pytest.mark.asyncio
    async def test_override_model_forwarded_to_sdk(self):
        """Runtime model override must reach create_session(session_kwargs)."""
        backend, mock_client = self._make_backend(config_model="copilot-claude-3.5")
        with patch.object(backend, "_get_client", return_value=mock_client):
            await backend._get_or_create_session("ctx-1", model="gpt-4o")

        call_kwargs = mock_client.create_session.await_args.args[0]
        assert call_kwargs["model"] == "gpt-4o"

    @pytest.mark.asyncio
    async def test_config_model_used_when_no_override(self):
        """Config default must be used when override is empty."""
        backend, mock_client = self._make_backend(config_model="copilot-claude-3.5")
        with patch.object(backend, "_get_client", return_value=mock_client):
            await backend._get_or_create_session("ctx-1", model="")

        call_kwargs = mock_client.create_session.await_args.args[0]
        assert call_kwargs["model"] == "copilot-claude-3.5"

    @pytest.mark.asyncio
    async def test_model_omitted_when_both_empty(self):
        """No model key in session_kwargs when config and override are both empty."""
        backend, mock_client = self._make_backend(config_model="")
        with patch.object(backend, "_get_client", return_value=mock_client):
            await backend._get_or_create_session("ctx-1", model="")

        call_kwargs = mock_client.create_session.await_args.args[0]
        assert "model" not in call_kwargs

    @pytest.mark.asyncio
    async def test_override_logs_when_differs_from_config(self, caplog):
        """Logger.info must fire when the override differs from config default."""
        backend, mock_client = self._make_backend(config_model="copilot-claude-3.5")
        with patch.object(backend, "_get_client", return_value=mock_client):
            with caplog.at_level(logging.INFO, logger="ii_agent.integrations.a2a.copilot_backend"):
                await backend._get_or_create_session("ctx-log", model="gpt-4o")

        assert any("gpt-4o" in r.message for r in caplog.records)
