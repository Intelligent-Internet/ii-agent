"""Tests for tools utilities."""

import pytest
import base64
from unittest.mock import patch, mock_open

from ii_agent.tools.utils import encode_image


class TestEncodeImage:
    """Test cases for encode_image function."""

    def test_encode_image_with_real_file(self, tmp_path):
        """Test encoding a real image file."""
        # Create a test image file with some binary data
        test_image = tmp_path / "test.png"
        image_data = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        )
        test_image.write_bytes(image_data)

        result = encode_image(str(test_image))

        # Should return base64 encoded string
        assert isinstance(result, str)
        # Decode and verify it matches original data
        decoded = base64.b64decode(result)
        assert decoded == image_data

    def test_encode_image_with_path_object(self, tmp_path):
        """Test encoding with Path object input."""
        test_image = tmp_path / "test.jpg"
        image_data = b"\xff\xd8\xff\xe0\x00\x10JFIF"  # JPEG header
        test_image.write_bytes(image_data)

        # Pass Path object instead of string
        result = encode_image(test_image)

        assert isinstance(result, str)
        decoded = base64.b64decode(result)
        assert decoded == image_data

    def test_encode_image_empty_file(self, tmp_path):
        """Test encoding an empty file."""
        test_image = tmp_path / "empty.png"
        test_image.write_bytes(b"")

        result = encode_image(str(test_image))

        assert result == ""  # Empty file should result in empty base64 string

    def test_encode_image_nonexistent_file(self):
        """Test encoding a non-existent file."""
        with pytest.raises(FileNotFoundError):
            encode_image("/nonexistent/path/image.png")

    def test_encode_image_with_mock_file(self):
        """Test encoding with mocked file operations."""
        test_data = b"fake image data"

        with patch("builtins.open", mock_open(read_data=test_data)):
            result = encode_image("/mock/path/image.png")

        expected = base64.b64encode(test_data).decode("utf-8")
        assert result == expected

    def test_encode_image_large_file(self, tmp_path):
        """Test encoding a larger file."""
        test_image = tmp_path / "large.png"
        # Create larger test data
        large_data = b"x" * 10000
        test_image.write_bytes(large_data)

        result = encode_image(str(test_image))

        assert isinstance(result, str)
        decoded = base64.b64decode(result)
        assert decoded == large_data
        assert len(result) > 10000  # Base64 encoded should be larger

    def test_encode_image_binary_data(self, tmp_path):
        """Test encoding with various binary data patterns."""
        test_image = tmp_path / "binary.png"
        # Mix of different bytes
        binary_data = bytes(range(256))
        test_image.write_bytes(binary_data)

        result = encode_image(str(test_image))

        assert isinstance(result, str)
        decoded = base64.b64decode(result)
        assert decoded == binary_data

    def test_encode_image_permission_error(self):
        """Test handling of permission errors."""
        with patch("builtins.open", side_effect=PermissionError("Access denied")):
            with pytest.raises(PermissionError):
                encode_image("/protected/image.png")

    def test_encode_image_io_error(self):
        """Test handling of I/O errors."""
        with patch("builtins.open", side_effect=IOError("I/O error")):
            with pytest.raises(IOError):
                encode_image("/problematic/image.png")

    def test_encode_image_unicode_path(self, tmp_path):
        """Test encoding with unicode characters in path."""
        # Create file with unicode characters in name
        test_image = tmp_path / "测试图片.png"
        image_data = b"unicode path test data"
        test_image.write_bytes(image_data)

        result = encode_image(str(test_image))

        assert isinstance(result, str)
        decoded = base64.b64decode(result)
        assert decoded == image_data

    def test_encode_image_relative_path(self, tmp_path):
        """Test encoding with relative path."""
        test_image = tmp_path / "relative.png"
        image_data = b"relative path test"
        test_image.write_bytes(image_data)

        # Change to temp directory and use relative path
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = encode_image("relative.png")

            assert isinstance(result, str)
            decoded = base64.b64decode(result)
            assert decoded == image_data
        finally:
            os.chdir(original_cwd)

    def test_encode_image_return_type(self, tmp_path):
        """Test that return type is always string."""
        test_image = tmp_path / "type_test.png"
        test_image.write_bytes(b"type test data")

        result = encode_image(str(test_image))

        assert type(result) is str
        assert isinstance(result, str)

    def test_encode_image_base64_validity(self, tmp_path):
        """Test that returned string is valid base64."""
        test_image = tmp_path / "valid_b64.png"
        test_image.write_bytes(b"base64 validity test")

        result = encode_image(str(test_image))

        # Should not raise exception when decoding
        try:
            decoded = base64.b64decode(result)
            # Should be able to encode back to same result
            re_encoded = base64.b64encode(decoded).decode("utf-8")
            assert re_encoded == result
        except Exception as e:
            pytest.fail(f"Invalid base64 string returned: {e}")

    def test_encode_image_different_extensions(self, tmp_path):
        """Test encoding files with different extensions."""
        extensions = [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"]
        test_data = b"extension test data"

        for ext in extensions:
            test_image = tmp_path / f"test{ext}"
            test_image.write_bytes(test_data)

            result = encode_image(str(test_image))

            assert isinstance(result, str)
            decoded = base64.b64decode(result)
            assert decoded == test_data

    def test_encode_image_with_spaces_in_path(self, tmp_path):
        """Test encoding file with spaces in path."""
        test_image = tmp_path / "test with spaces.png"
        image_data = b"spaces in path test"
        test_image.write_bytes(image_data)

        result = encode_image(str(test_image))

        assert isinstance(result, str)
        decoded = base64.b64decode(result)
        assert decoded == image_data

    def test_encode_image_uses_path_read_bytes(self, tmp_path):
        # Create a temporary file with test data
        test_file = tmp_path / "test.png"
        test_data = b"mock data"
        test_file.write_bytes(test_data)

        result = encode_image(str(test_file))
        expected = base64.b64encode(test_data).decode("utf-8")
        assert result == expected
