"""Unit tests for ii_tool LocalStorage class.

This module contains tests for the async local filesystem storage provider
used in tool integrations.
"""

import io
import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

from ii_tool.integrations.storage.local import LocalStorage

pytest_plugins = ('pytest_asyncio',)


class TestToolLocalStorageInit:
    """Tests for tool LocalStorage initialization."""

    def test_init_creates_base_directory(self):
        """Test that initialization creates the base directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = os.path.join(tmpdir, "tool_storage")
            storage = LocalStorage(base_path=base_path)

            assert os.path.exists(base_path)
            assert storage.base_path == os.path.abspath(base_path)


class TestToolLocalStoragePathValidation:
    """Tests for path validation and security in tool storage."""

    def test_get_full_path_normal(self):
        """Test that normal paths are resolved correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(base_path=tmpdir)

            full_path = storage._get_full_path("subdir/file.txt")

            assert full_path == os.path.join(tmpdir, "subdir", "file.txt")

    def test_get_full_path_strips_leading_slash(self):
        """Test that leading slashes are stripped from paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(base_path=tmpdir)

            full_path = storage._get_full_path("/subdir/file.txt")

            assert full_path == os.path.join(tmpdir, "subdir", "file.txt")

    def test_get_full_path_rejects_path_traversal(self):
        """Test that path traversal attempts are rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(base_path=tmpdir)

            with pytest.raises(ValueError, match="Path traversal detected"):
                storage._get_full_path("../../../etc/passwd")


class TestToolLocalStorageWrite:
    """Tests for async write operations."""

    @pytest.mark.asyncio
    async def test_write_creates_file(self):
        """Test that write creates a file with correct content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(base_path=tmpdir)
            content = io.BytesIO(b"test content")

            await storage.write(content, "test.txt")

            full_path = os.path.join(tmpdir, "test.txt")
            assert os.path.exists(full_path)
            with open(full_path, "rb") as f:
                assert f.read() == b"test content"

    @pytest.mark.asyncio
    async def test_write_creates_subdirectories(self):
        """Test that write creates necessary subdirectories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(base_path=tmpdir)
            content = io.BytesIO(b"nested content")

            await storage.write(content, "a/b/c/test.txt")

            full_path = os.path.join(tmpdir, "a", "b", "c", "test.txt")
            assert os.path.exists(full_path)

    @pytest.mark.asyncio
    async def test_write_with_content_type_creates_meta_file(self):
        """Test that content type is stored in a .meta file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(base_path=tmpdir)
            content = io.BytesIO(b"image data")

            await storage.write(content, "image.png", content_type="image/png")

            meta_path = os.path.join(tmpdir, "image.png.meta")
            assert os.path.exists(meta_path)
            with open(meta_path, "r") as f:
                assert f.read() == "image/png"


class TestToolLocalStorageWriteFromLocalPath:
    """Tests for write_from_local_path operation."""

    @pytest.mark.asyncio
    async def test_write_from_local_path_copies_file(self):
        """Test that write_from_local_path copies file correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(base_path=tmpdir)

            # Create source file
            source_dir = tempfile.mkdtemp()
            source_file = os.path.join(source_dir, "source.txt")
            with open(source_file, "wb") as f:
                f.write(b"source content")

            try:
                url = await storage.write_from_local_path(
                    source_file, "copied.txt", content_type="text/plain"
                )

                # Check file was copied
                dest_path = os.path.join(tmpdir, "copied.txt")
                assert os.path.exists(dest_path)
                with open(dest_path, "rb") as f:
                    assert f.read() == b"source content"

                # Check URL is returned
                assert "copied.txt" in url
            finally:
                import shutil
                shutil.rmtree(source_dir)


class TestToolLocalStoragePublicUrl:
    """Tests for get_public_url."""

    def test_get_public_url_returns_file_url(self):
        """Test that get_public_url returns file:// URL."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(base_path=tmpdir)

            url = storage.get_public_url("path/to/file.txt")

            assert url.startswith("file://")
            assert "path/to/file.txt" in url
