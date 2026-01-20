"""Unit tests for the LocalStorage class (ii_agent backend storage).

This module contains tests for the local filesystem storage provider,
including file operations, path validation, and URL generation.
"""

import io
import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from ii_agent.storage.local import LocalStorage


class TestLocalStorageInit:
    """Tests for LocalStorage initialization."""

    def test_init_creates_base_directory(self):
        """Test that initialization creates the base directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = os.path.join(tmpdir, "storage")
            storage = LocalStorage(base_path=base_path)

            assert os.path.exists(base_path)
            assert storage.base_path == os.path.abspath(base_path)

    def test_init_with_custom_urls(self):
        """Test initialization with custom URL bases."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(
                base_path=tmpdir,
                serve_url_base="http://localhost:8000/files",
                internal_url_base="http://backend:8000/files",
            )

            assert storage.serve_url_base == "http://localhost:8000/files"
            assert storage.internal_url_base == "http://backend:8000/files"

    def test_init_internal_url_defaults_to_serve_url(self):
        """Test that internal URL defaults to serve URL if not provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(
                base_path=tmpdir,
                serve_url_base="/custom-files",
            )

            assert storage.internal_url_base == "/custom-files"


class TestLocalStoragePathValidation:
    """Tests for path validation and security."""

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

    def test_get_full_path_rejects_double_dot(self):
        """Test that paths with .. are rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(base_path=tmpdir)

            with pytest.raises(ValueError, match="Path traversal detected"):
                storage._get_full_path("subdir/../../../etc/passwd")


class TestLocalStorageWrite:
    """Tests for write operations."""

    def test_write_creates_file(self):
        """Test that write creates a file with correct content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(base_path=tmpdir)
            content = io.BytesIO(b"test content")

            storage.write(content, "test.txt")

            full_path = os.path.join(tmpdir, "test.txt")
            assert os.path.exists(full_path)
            with open(full_path, "rb") as f:
                assert f.read() == b"test content"

    def test_write_creates_subdirectories(self):
        """Test that write creates necessary subdirectories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(base_path=tmpdir)
            content = io.BytesIO(b"nested content")

            storage.write(content, "a/b/c/test.txt")

            full_path = os.path.join(tmpdir, "a", "b", "c", "test.txt")
            assert os.path.exists(full_path)

    def test_write_with_content_type_creates_meta_file(self):
        """Test that content type is stored in a .meta file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(base_path=tmpdir)
            content = io.BytesIO(b"image data")

            storage.write(content, "image.png", content_type="image/png")

            meta_path = os.path.join(tmpdir, "image.png.meta")
            assert os.path.exists(meta_path)
            with open(meta_path, "r") as f:
                assert f.read() == "image/png"


class TestLocalStorageRead:
    """Tests for read operations."""

    def test_read_returns_file_content(self):
        """Test that read returns file content as BytesIO."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(base_path=tmpdir)
            # Create a file manually
            test_path = os.path.join(tmpdir, "test.txt")
            with open(test_path, "wb") as f:
                f.write(b"file content")

            result = storage.read("test.txt")

            assert isinstance(result, io.BytesIO)
            assert result.read() == b"file content"

    def test_read_nonexistent_file_raises(self):
        """Test that reading a nonexistent file raises an error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(base_path=tmpdir)

            with pytest.raises(FileNotFoundError):
                storage.read("nonexistent.txt")


class TestLocalStorageExists:
    """Tests for existence checking."""

    def test_is_exists_returns_true_for_existing_file(self):
        """Test that is_exists returns True for existing files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(base_path=tmpdir)
            # Create a file
            test_path = os.path.join(tmpdir, "exists.txt")
            with open(test_path, "wb") as f:
                f.write(b"content")

            assert storage.is_exists("exists.txt") is True

    def test_is_exists_returns_false_for_missing_file(self):
        """Test that is_exists returns False for missing files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(base_path=tmpdir)

            assert storage.is_exists("missing.txt") is False


class TestLocalStorageFileSize:
    """Tests for file size operations."""

    def test_get_file_size_returns_correct_size(self):
        """Test that get_file_size returns correct file size."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(base_path=tmpdir)
            content = b"12345678901234567890"  # 20 bytes
            test_path = os.path.join(tmpdir, "sized.txt")
            with open(test_path, "wb") as f:
                f.write(content)

            size = storage.get_file_size("sized.txt")

            assert size == 20

    def test_get_file_size_nonexistent_raises(self):
        """Test that get_file_size raises for nonexistent files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(base_path=tmpdir)

            with pytest.raises(FileNotFoundError):
                storage.get_file_size("nonexistent.txt")


class TestLocalStorageUrls:
    """Tests for URL generation."""

    def test_get_public_url(self):
        """Test that get_public_url returns correct URL."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(
                base_path=tmpdir,
                serve_url_base="/files",
            )

            url = storage.get_public_url("path/to/file.txt")

            assert url == "/files/path/to/file.txt"

    def test_get_permanent_url_returns_signed_url_for_existing_file(self):
        """Test that get_permanent_url returns signed URL for existing files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(
                base_path=tmpdir,
                serve_url_base="http://localhost/files",
            )
            # Create a file first
            test_path = os.path.join(tmpdir, "file.txt")
            with open(test_path, "wb") as f:
                f.write(b"content")

            url = storage.get_permanent_url("file.txt")

            # Should return signed URL with token and expires
            assert url.startswith("http://localhost/files/file.txt")
            assert "token=" in url
            assert "expires=" in url

    def test_get_permanent_url_falls_back_to_public_for_missing_file(self):
        """Test that get_permanent_url falls back to public URL for missing files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(
                base_path=tmpdir,
                serve_url_base="http://localhost/files",
            )

            url = storage.get_permanent_url("nonexistent.txt")

            # Should fall back to public URL (no token/expires)
            assert url == "http://localhost/files/nonexistent.txt"

    def test_get_download_signed_url_returns_none_for_missing(self):
        """Test that get_download_signed_url returns None for missing files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(base_path=tmpdir)

            url = storage.get_download_signed_url("missing.txt")

            assert url is None

    def test_get_download_signed_url_includes_token(self):
        """Test that get_download_signed_url includes token and expiry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(
                base_path=tmpdir,
                serve_url_base="/files",
            )
            # Create a file
            test_path = os.path.join(tmpdir, "secure.txt")
            with open(test_path, "wb") as f:
                f.write(b"content")

            url = storage.get_download_signed_url("secure.txt")

            assert url is not None
            assert "token=" in url
            assert "expires=" in url
            assert url.startswith("/files/secure.txt")

    def test_get_download_signed_url_uses_internal_base(self):
        """Test that internal=True uses internal URL base."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(
                base_path=tmpdir,
                serve_url_base="http://localhost:8000/files",
                internal_url_base="http://backend:8000/files",
            )
            # Create a file
            test_path = os.path.join(tmpdir, "internal.txt")
            with open(test_path, "wb") as f:
                f.write(b"content")

            url = storage.get_download_signed_url("internal.txt", internal=True)

            assert url is not None
            assert url.startswith("http://backend:8000/files/internal.txt")

    def test_get_upload_signed_url_includes_params(self):
        """Test that get_upload_signed_url includes required params."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(
                base_path=tmpdir,
                serve_url_base="/files",
            )

            url = storage.get_upload_signed_url(
                "upload/path.txt",
                content_type="application/pdf",
                expiration_seconds=1800,
            )

            assert "/files/upload/upload/path.txt" in url
            assert "token=" in url
            assert "expires=" in url
            assert "content_type=" in url

    def test_get_upload_signed_url_internal_true_uses_internal_base(self):
        """Test that internal=True uses internal URL base for server-to-server uploads."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(
                base_path=tmpdir,
                serve_url_base="http://localhost:8000/files",
                internal_url_base="http://backend:8000/files",
            )

            url = storage.get_upload_signed_url(
                "upload/path.txt",
                content_type="text/plain",
                internal=True,
            )

            assert url.startswith("http://backend:8000/files/upload/")
            assert "token=" in url

    def test_get_upload_signed_url_internal_false_uses_serve_base(self):
        """Test that internal=False uses serve URL base for browser uploads."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(
                base_path=tmpdir,
                serve_url_base="http://localhost:8000/files",
                internal_url_base="http://backend:8000/files",
            )

            url = storage.get_upload_signed_url(
                "upload/path.txt",
                content_type="text/plain",
                internal=False,
            )

            assert url.startswith("http://localhost:8000/files/upload/")
            assert "token=" in url

    def test_get_upload_signed_url_defaults_to_internal_true(self):
        """Test that internal parameter defaults to True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(
                base_path=tmpdir,
                serve_url_base="http://localhost:8000/files",
                internal_url_base="http://backend:8000/files",
            )

            # Call without internal parameter - should default to internal=True
            url = storage.get_upload_signed_url(
                "upload/path.txt",
                content_type="text/plain",
            )

            assert url.startswith("http://backend:8000/files/upload/")


class TestLocalStorageUploadAndGet:
    """Tests for combined upload operations."""

    def test_upload_and_get_permanent_url(self):
        """Test that upload_and_get_permanent_url works correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(
                base_path=tmpdir,
                serve_url_base="/files",
            )
            content = io.BytesIO(b"uploaded content")

            url = storage.upload_and_get_permanent_url(
                content, "uploaded.txt", content_type="text/plain"
            )

            # Check URL starts with base path (may include token/expiry for signed URLs)
            assert url.startswith("/files/uploaded.txt")

            # Check file was created
            full_path = os.path.join(tmpdir, "uploaded.txt")
            assert os.path.exists(full_path)
            with open(full_path, "rb") as f:
                assert f.read() == b"uploaded content"
