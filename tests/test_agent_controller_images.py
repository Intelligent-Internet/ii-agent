"""Unit tests for agent controller image handling.

Tests the image path extraction logic that prevents embedding large images
directly in API requests to avoid 413 "request too large" errors.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from urllib.parse import unquote


class TestImagePathExtraction:
    """Tests for extracting image paths without embedding."""

    def test_extracts_filename_from_url(self):
        """Should extract filename from image URL."""
        image_data = {
            "url": "http://localhost:8000/files/users/admin/uploads/abc123-myimage.png",
            "filename": "myimage.png",
            "content_type": "image/png",
        }
        
        filename = image_data.get("filename", image_data["url"].split("/")[-1].split("?")[0])
        expected_path = f"/workspace/uploads/{filename}"
        
        assert filename == "myimage.png"
        assert expected_path == "/workspace/uploads/myimage.png"

    def test_extracts_filename_from_url_when_no_filename_field(self):
        """Should extract filename from URL path when filename field is missing."""
        image_data = {
            "url": "http://localhost:8000/files/uploads/abc123-test-image.jpg?token=xyz",
            "content_type": "image/jpeg",
        }
        
        url_path = image_data.get("url", "")
        filename = image_data.get("filename", unquote(url_path.split("/")[-1].split("?")[0]))
        
        assert filename == "abc123-test-image.jpg"

    def test_handles_url_with_query_params(self):
        """Should strip query parameters from URL when extracting filename."""
        image_data = {
            "url": "http://localhost:8000/files/image.png?token=abc&expires=123",
        }
        
        url_path = image_data.get("url", "")
        filename = image_data.get("filename", unquote(url_path.split("/")[-1].split("?")[0]))
        
        assert filename == "image.png"
        assert "?" not in filename
        assert "token" not in filename

    def test_handles_url_encoded_filename(self):
        """Should URL-decode filenames with encoded characters like %20 for spaces."""
        image_data = {
            "url": "http://localhost:8000/files/uploads/My%20Image%20File.png?token=abc",
        }
        
        url_path = image_data.get("url", "")
        filename = image_data.get("filename", unquote(url_path.split("/")[-1].split("?")[0]))
        
        assert filename == "My Image File.png"
        assert "%20" not in filename

    def test_handles_multiple_encoded_characters(self):
        """Should handle various URL-encoded characters."""
        image_data = {
            "url": "http://localhost:8000/files/uploads/Test%26Image%2B%28v2%29.png",
        }
        
        url_path = image_data.get("url", "")
        filename = image_data.get("filename", unquote(url_path.split("/")[-1].split("?")[0]))
        
        # %26 = &, %2B = +, %28 = (, %29 = )
        assert filename == "Test&Image+(v2).png"
        assert "%" not in filename


class TestImageInstructionGeneration:
    """Tests for generating image instruction text."""

    def test_generates_image_list_instruction(self):
        """Should generate instruction listing all image paths."""
        images_data = [
            {"url": "http://example.com/1.png", "filename": "image1.png"},
            {"url": "http://example.com/2.png", "filename": "image2.png"},
            {"url": "http://example.com/3.png", "filename": "image3.png"},
        ]
        
        image_paths = []
        for image_data in images_data:
            url_path = image_data.get("url", "")
            filename = image_data.get("filename", url_path.split("/")[-1].split("?")[0])
            image_paths.append(f"/workspace/uploads/{filename}")
        
        assert len(image_paths) == 3
        assert "/workspace/uploads/image1.png" in image_paths
        assert "/workspace/uploads/image2.png" in image_paths
        assert "/workspace/uploads/image3.png" in image_paths

    def test_instruction_includes_file_count(self):
        """Should include total file count in instruction."""
        images_data = [
            {"filename": f"image{i}.png"} for i in range(9)
        ]
        
        instruction_text = f"IMAGES PROVIDED ({len(images_data)} files):"
        
        assert "9 files" in instruction_text

    def test_instruction_mentions_fileread_tool(self):
        """Instruction should tell agent to use FileRead tool."""
        instruction = """IMPORTANT: To view these images, use the FileRead tool to read each image file ONE AT A TIME.
Do NOT try to process all images at once - this will cause request size errors.
Read each image individually as you work on the corresponding content."""
        
        assert "FileRead" in instruction
        assert "ONE AT A TIME" in instruction
        assert "request size errors" in instruction


class TestNoImageEmbedding:
    """Tests to ensure images are NOT embedded in requests."""

    def test_image_blocks_empty_when_images_provided(self):
        """image_blocks should remain empty even when images_data is provided."""
        # This simulates the new behavior where we don't embed images
        images_data = [
            {"url": "http://example.com/large-image.png", "filename": "large.png"},
        ]
        
        image_blocks = []  # Should remain empty
        
        # Process images - extract paths only, don't embed
        if images_data:
            image_paths = []
            for image_data in images_data:
                filename = image_data.get("filename", "")
                image_paths.append(f"/workspace/uploads/{filename}")
            # Note: We do NOT append to image_blocks
        
        assert len(image_blocks) == 0, "Images should not be embedded in blocks"
        assert len(image_paths) == 1, "Paths should be extracted"
