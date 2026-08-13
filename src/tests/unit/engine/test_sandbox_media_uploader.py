"""Tests for SandboxMediaUploader — TDD RED phase.

Tests the standalone media uploader that downloads files/images from URLs
and uploads them to a sandbox, decoupled from the Agent class.
"""

from __future__ import annotations

from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.files.media import File, Image
from ii_agent.agents.sandboxes.schemas import FileUpload


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sandbox(upload_path: str = "/uploads") -> MagicMock:
    """Create a mock Sandbox with write_files and create_directory."""
    sandbox = MagicMock()
    sandbox.upload_path = upload_path
    sandbox.create_directory = AsyncMock()
    sandbox.write_files = AsyncMock()
    return sandbox


def _make_file(
    file_id: str = "f1", url: str = "https://example.com/file.txt", filename: str = "file.txt"
) -> File:
    return File(id=file_id, url=url, filename=filename)


def _make_image(url: str = "https://example.com/img.png", mime_type: str = "image/png") -> Image:
    return Image(url=url, mime_type=mime_type)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_files_only():
    """Files are downloaded, uploaded to sandbox, and returned with sandbox paths."""
    from ii_agent.agents.sandboxes.media_uploader import upload_media_to_sandbox

    sandbox = _make_sandbox()
    files = [_make_file("f1", "https://example.com/a.txt", "a.txt")]

    with patch("ii_agent.agents.sandboxes.media_uploader.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_resp = MagicMock()
        mock_resp.content = b"file-content"
        mock_resp.raise_for_status = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_resp)

        sandbox_files, sandbox_images = await upload_media_to_sandbox(
            sandbox=sandbox, files=files, images=[], upload_path="/uploads"
        )

    assert len(sandbox_files) == 1
    assert sandbox_files[0].filepath == "/uploads/a.txt"
    assert sandbox_images == []
    sandbox.write_files.assert_awaited_once()
    uploads: List[FileUpload] = sandbox.write_files.await_args[0][0]
    assert len(uploads) == 1
    assert uploads[0].path == "/uploads/a.txt"
    assert uploads[0].content == b"file-content"


@pytest.mark.asyncio
async def test_upload_images_only():
    """Images are downloaded, uploaded, and returned with sandbox paths."""
    from ii_agent.agents.sandboxes.media_uploader import upload_media_to_sandbox

    sandbox = _make_sandbox()
    images = [_make_image("https://example.com/img.png", "image/png")]

    with patch("ii_agent.agents.sandboxes.media_uploader.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_resp = MagicMock()
        mock_resp.content = b"png-bytes"
        mock_resp.raise_for_status = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_resp)

        sandbox_files, sandbox_images = await upload_media_to_sandbox(
            sandbox=sandbox, files=[], images=images, upload_path="/uploads"
        )

    assert sandbox_files == []
    assert len(sandbox_images) == 1
    # Images now carry raw bytes (content) instead of sandbox filepath,
    # ensuring both A2A adapter and native model fallback can access them.
    assert sandbox_images[0].content == b"png-bytes"
    assert sandbox_images[0].filepath is None
    assert sandbox_images[0].url is None
    sandbox.write_files.assert_awaited_once()


@pytest.mark.asyncio
async def test_upload_mixed_files_and_images():
    """Both files and images are uploaded in a single batch."""
    from ii_agent.agents.sandboxes.media_uploader import upload_media_to_sandbox

    sandbox = _make_sandbox()
    files = [_make_file("f1", "https://example.com/doc.pdf", "doc.pdf")]
    images = [_make_image("https://example.com/photo.jpg", "image/jpeg")]

    with patch("ii_agent.agents.sandboxes.media_uploader.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_resp = MagicMock()
        mock_resp.content = b"data"
        mock_resp.raise_for_status = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_resp)

        sandbox_files, sandbox_images = await upload_media_to_sandbox(
            sandbox=sandbox, files=files, images=images, upload_path="/uploads"
        )

    assert len(sandbox_files) == 1
    assert len(sandbox_images) == 1
    sandbox.write_files.assert_awaited_once()
    uploads: List[FileUpload] = sandbox.write_files.await_args[0][0]
    assert len(uploads) == 2


@pytest.mark.asyncio
async def test_no_media_returns_empty():
    """No files and no images returns empty lists without sandbox calls."""
    from ii_agent.agents.sandboxes.media_uploader import upload_media_to_sandbox

    sandbox = _make_sandbox()

    sandbox_files, sandbox_images = await upload_media_to_sandbox(
        sandbox=sandbox, files=[], images=[], upload_path="/uploads"
    )

    assert sandbox_files == []
    assert sandbox_images == []
    sandbox.write_files.assert_not_awaited()


@pytest.mark.asyncio
async def test_download_failure_skips_file():
    """A file that fails to download is skipped; others still upload."""
    from ii_agent.agents.sandboxes.media_uploader import upload_media_to_sandbox

    sandbox = _make_sandbox()
    files = [
        _make_file("f1", "https://example.com/good.txt", "good.txt"),
        _make_file("f2", "https://example.com/bad.txt", "bad.txt"),
    ]

    with patch("ii_agent.agents.sandboxes.media_uploader.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        good_resp = MagicMock()
        good_resp.content = b"good-data"
        good_resp.raise_for_status = MagicMock()

        bad_resp = MagicMock()
        bad_resp.raise_for_status = MagicMock(side_effect=Exception("404"))

        mock_client.get = AsyncMock(side_effect=[good_resp, bad_resp])

        sandbox_files, sandbox_images = await upload_media_to_sandbox(
            sandbox=sandbox, files=files, images=[], upload_path="/uploads"
        )

    assert len(sandbox_files) == 1
    assert sandbox_files[0].filepath == "/uploads/good.txt"


@pytest.mark.asyncio
async def test_write_files_failure_returns_empty_files():
    """If sandbox.write_files raises, files list is empty, images returned as-is."""
    from ii_agent.agents.sandboxes.media_uploader import upload_media_to_sandbox

    sandbox = _make_sandbox()
    sandbox.write_files = AsyncMock(side_effect=Exception("write failed"))
    files = [_make_file("f1", "https://example.com/a.txt", "a.txt")]
    images = [_make_image()]

    with patch("ii_agent.agents.sandboxes.media_uploader.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_resp = MagicMock()
        mock_resp.content = b"data"
        mock_resp.raise_for_status = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_resp)

        sandbox_files, sandbox_images = await upload_media_to_sandbox(
            sandbox=sandbox, files=files, images=images, upload_path="/uploads"
        )

    # On write failure: empty files, original images passed through
    assert sandbox_files == []
    assert len(sandbox_images) == 1


@pytest.mark.asyncio
async def test_file_without_url_is_skipped():
    """A File with no URL is silently skipped."""
    from ii_agent.agents.sandboxes.media_uploader import upload_media_to_sandbox

    sandbox = _make_sandbox()
    files = [File(id="no-url", filepath="/local/only")]

    sandbox_files, sandbox_images = await upload_media_to_sandbox(
        sandbox=sandbox, files=files, images=[], upload_path="/uploads"
    )

    assert sandbox_files == []
    sandbox.write_files.assert_not_awaited()


@pytest.mark.asyncio
async def test_image_extension_from_mime_type():
    """Image filename extension is derived from mime_type."""
    from ii_agent.agents.sandboxes.media_uploader import upload_media_to_sandbox

    sandbox = _make_sandbox()
    images = [_make_image("https://example.com/img", "image/webp")]

    with patch("ii_agent.agents.sandboxes.media_uploader.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_resp = MagicMock()
        mock_resp.content = b"webp-data"
        mock_resp.raise_for_status = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_resp)

        _, sandbox_images = await upload_media_to_sandbox(
            sandbox=sandbox, files=[], images=images, upload_path="/uploads"
        )

    uploads: List[FileUpload] = sandbox.write_files.await_args[0][0]
    assert uploads[0].path == "/uploads/image_0.webp"


@pytest.mark.asyncio
async def test_image_extension_from_format_fallback():
    """Image filename extension falls back to format when no mime_type."""
    from ii_agent.agents.sandboxes.media_uploader import upload_media_to_sandbox

    sandbox = _make_sandbox()
    images = [Image(url="https://example.com/img", format="gif")]

    with patch("ii_agent.agents.sandboxes.media_uploader.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_resp = MagicMock()
        mock_resp.content = b"gif-data"
        mock_resp.raise_for_status = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_resp)

        _, sandbox_images = await upload_media_to_sandbox(
            sandbox=sandbox, files=[], images=images, upload_path="/uploads"
        )

    uploads: List[FileUpload] = sandbox.write_files.await_args[0][0]
    assert uploads[0].path == "/uploads/image_0.gif"
