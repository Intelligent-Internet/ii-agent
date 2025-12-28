"""Unit tests for ii_tool.tools.file_system.utils module.

This module tests file system utility functions:
- encode_image: Base64 encoding of local and remote images
- find_similar_file: Finding files with different extensions
"""

import base64
import os
import pytest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, MagicMock

from ii_tool.tools.file_system.utils import encode_image, find_similar_file


# =============================================================================
# encode_image Tests - Local Files
# =============================================================================

class TestEncodeImageLocal:
    """Tests for encode_image with local files."""

    def test_encodes_local_file(self):
        """encode_image returns base64 encoded content for local files."""
        with TemporaryDirectory() as tmpdir:
            # Create a test file with known content
            test_file = Path(tmpdir) / "test.txt"
            test_content = b"Hello, World!"
            test_file.write_bytes(test_content)
            
            result = encode_image(str(test_file))
            
            # Decode and verify
            decoded = base64.b64decode(result)
            assert decoded == test_content

    def test_encodes_binary_file(self):
        """encode_image handles binary data correctly."""
        with TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "binary.bin"
            # Binary content with null bytes
            binary_content = bytes([0, 1, 2, 255, 254, 253, 0, 128])
            test_file.write_bytes(binary_content)
            
            result = encode_image(str(test_file))
            
            decoded = base64.b64decode(result)
            assert decoded == binary_content

    def test_encodes_empty_file(self):
        """encode_image handles empty files."""
        with TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "empty.txt"
            test_file.write_bytes(b"")
            
            result = encode_image(str(test_file))
            
            decoded = base64.b64decode(result)
            assert decoded == b""

    def test_returns_string(self):
        """encode_image returns a string, not bytes."""
        with TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_bytes(b"test")
            
            result = encode_image(str(test_file))
            
            assert isinstance(result, str)

    def test_nonexistent_file_raises(self):
        """encode_image raises for nonexistent files."""
        with pytest.raises(FileNotFoundError):
            encode_image("/nonexistent/path/file.txt")


# =============================================================================
# encode_image Tests - Remote Files (HTTP)
# =============================================================================

class TestEncodeImageRemote:
    """Tests for encode_image with HTTP URLs."""

    def test_fetches_remote_image(self):
        """encode_image fetches and encodes remote images."""
        mock_content = b"fake image content"
        
        with patch('ii_tool.tools.file_system.utils.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.content = mock_content
            mock_get.return_value = mock_response
            
            result = encode_image("http://example.com/image.png")
            
            decoded = base64.b64decode(result)
            assert decoded == mock_content

    def test_uses_user_agent(self):
        """encode_image sets a browser User-Agent header."""
        with patch('ii_tool.tools.file_system.utils.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.content = b"content"
            mock_get.return_value = mock_response
            
            encode_image("http://example.com/image.png")
            
            # Check User-Agent was set
            call_kwargs = mock_get.call_args[1]
            assert "User-Agent" in call_kwargs.get("headers", {})

    def test_https_url(self):
        """encode_image works with HTTPS URLs."""
        with patch('ii_tool.tools.file_system.utils.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.content = b"secure content"
            mock_get.return_value = mock_response
            
            result = encode_image("https://secure.example.com/image.jpg")
            
            decoded = base64.b64decode(result)
            assert decoded == b"secure content"

    def test_http_error_propagates(self):
        """encode_image propagates HTTP errors."""
        import requests
        
        with patch('ii_tool.tools.file_system.utils.requests.get') as mock_get:
            mock_get.side_effect = requests.exceptions.HTTPError("404 Not Found")
            
            with pytest.raises(requests.exceptions.HTTPError):
                encode_image("http://example.com/missing.png")


# =============================================================================
# find_similar_file Tests
# =============================================================================

class TestFindSimilarFile:
    """Tests for find_similar_file function."""

    def test_finds_similar_extension(self):
        """find_similar_file finds files with same base name but different extension."""
        with TemporaryDirectory() as tmpdir:
            # Create test.txt and test.md
            Path(tmpdir, "test.txt").write_text("txt content")
            Path(tmpdir, "test.md").write_text("md content")
            
            # Look for similar to test.txt
            result = find_similar_file(os.path.join(tmpdir, "test.txt"))
            
            # Should find test.md
            assert result is not None
            assert result.endswith("test.md")

    def test_returns_none_when_no_similar(self):
        """find_similar_file returns None when no similar files exist."""
        with TemporaryDirectory() as tmpdir:
            # Create only test.txt
            Path(tmpdir, "test.txt").write_text("content")
            
            result = find_similar_file(os.path.join(tmpdir, "test.txt"))
            
            assert result is None

    def test_does_not_return_same_file(self):
        """find_similar_file does not return the original file."""
        with TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir, "only.txt")
            test_file.write_text("content")
            
            result = find_similar_file(str(test_file))
            
            # Should not return the same file
            assert result is None or result != str(test_file)

    def test_returns_none_for_nonexistent_file(self):
        """find_similar_file returns None for nonexistent files."""
        result = find_similar_file("/nonexistent/path/file.txt")
        assert result is None

    def test_handles_file_without_extension(self):
        """find_similar_file handles files without extensions."""
        with TemporaryDirectory() as tmpdir:
            Path(tmpdir, "Makefile").write_text("make content")
            Path(tmpdir, "Makefile.bak").write_text("backup")
            
            result = find_similar_file(os.path.join(tmpdir, "Makefile"))
            
            # Should find Makefile.bak
            assert result is not None
            assert "Makefile.bak" in result

    def test_handles_multiple_similar_files(self):
        """find_similar_file returns one file when multiple exist."""
        with TemporaryDirectory() as tmpdir:
            Path(tmpdir, "doc.txt").write_text("txt")
            Path(tmpdir, "doc.md").write_text("md")
            Path(tmpdir, "doc.rst").write_text("rst")
            
            result = find_similar_file(os.path.join(tmpdir, "doc.txt"))
            
            # Should return one of the alternatives
            assert result is not None
            assert "doc." in result
            assert not result.endswith(".txt")

    def test_handles_exception_gracefully(self):
        """find_similar_file handles exceptions and returns None."""
        with patch('ii_tool.tools.file_system.utils.glob') as mock_glob:
            mock_glob.side_effect = PermissionError("Access denied")
            
            result = find_similar_file("/some/path/file.txt")
            
            assert result is None
