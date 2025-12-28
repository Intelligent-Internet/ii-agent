"""Unit tests for ii_tool.tools.file_system.file_read_tool module.

This module tests the file reading tool:
- File type detection (_detect_file_type, _is_binary_file)
- PDF reading (_read_pdf_file)
- Image reading (_read_image_file)
- Text content truncation (_truncate_text_content)
- FileReadTool class and execute method
"""

import base64
import os
import pytest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, MagicMock, AsyncMock

from ii_tool.tools.file_system.file_read_tool import (
    _is_binary_file,
    _detect_file_type,
    _truncate_text_content,
    _read_image_file,
    UnreadableImageError,
    FileReadTool,
    MAX_FILE_READ_LINES,
    MAX_LINE_LENGTH,
    SUPPORTED_IMAGE_EXTENSIONS,
)
from ii_tool.core.workspace import WorkspaceManager
from ii_tool.tools.base import ToolResult, ImageContent


# =============================================================================
# _is_binary_file Tests
# =============================================================================

class TestIsBinaryFile:
    """Tests for _is_binary_file detection function."""

    def test_text_file_is_not_binary(self):
        """Plain text files are detected as not binary."""
        with TemporaryDirectory() as tmpdir:
            text_file = Path(tmpdir) / "text.txt"
            text_file.write_text("Hello, this is plain text content.\nLine 2.")
            
            assert _is_binary_file(text_file) is False

    def test_file_with_null_bytes_is_binary(self):
        """Files containing null bytes are detected as binary."""
        with TemporaryDirectory() as tmpdir:
            binary_file = Path(tmpdir) / "binary.bin"
            binary_file.write_bytes(b"Some text\x00with null\x00bytes")
            
            assert _is_binary_file(binary_file) is True

    def test_empty_file_is_not_binary(self):
        """Empty files are not considered binary."""
        with TemporaryDirectory() as tmpdir:
            empty_file = Path(tmpdir) / "empty.txt"
            empty_file.write_bytes(b"")
            
            assert _is_binary_file(empty_file) is False

    def test_high_non_printable_ratio_is_binary(self):
        """Files with many non-printable chars are binary."""
        with TemporaryDirectory() as tmpdir:
            binary_file = Path(tmpdir) / "binary.dat"
            # >30% non-printable characters
            content = bytes([1, 2, 3, 4, 5, 6, 7, 8] * 100)
            binary_file.write_bytes(content)
            
            assert _is_binary_file(binary_file) is True

    def test_unicode_text_is_not_binary(self):
        """UTF-8 encoded text with special chars is not binary."""
        with TemporaryDirectory() as tmpdir:
            utf8_file = Path(tmpdir) / "unicode.txt"
            utf8_file.write_text("Héllo Wörld! 日本語 🚀", encoding="utf-8")
            
            assert _is_binary_file(utf8_file) is False

    def test_nonexistent_file_returns_false(self):
        """Nonexistent files return False (handled gracefully)."""
        result = _is_binary_file(Path("/nonexistent/file.txt"))
        assert result is False


# =============================================================================
# _detect_file_type Tests
# =============================================================================

class TestDetectFileType:
    """Tests for _detect_file_type function."""

    def test_detects_text_by_extension(self):
        """Common text extensions are detected correctly."""
        with TemporaryDirectory() as tmpdir:
            for ext in ['.txt', '.py', '.js', '.md', '.json', '.html', '.css']:
                test_file = Path(tmpdir) / f"file{ext}"
                test_file.write_text("content")
                
                assert _detect_file_type(test_file) == 'text', f"Failed for {ext}"

    def test_detects_pdf(self):
        """PDF files are detected by extension."""
        with TemporaryDirectory() as tmpdir:
            pdf_file = Path(tmpdir) / "document.pdf"
            pdf_file.write_bytes(b"%PDF-1.4 fake pdf content")
            
            assert _detect_file_type(pdf_file) == 'pdf'

    def test_detects_images(self):
        """Image files are detected by extension."""
        with TemporaryDirectory() as tmpdir:
            for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']:
                img_file = Path(tmpdir) / f"image{ext}"
                img_file.write_bytes(b"fake image data")
                
                assert _detect_file_type(img_file) == 'image', f"Failed for {ext}"

    def test_svg_is_text(self):
        """SVG files are treated as text (XML-based)."""
        with TemporaryDirectory() as tmpdir:
            svg_file = Path(tmpdir) / "icon.svg"
            svg_file.write_text('<svg xmlns="http://www.w3.org/2000/svg"></svg>')
            
            assert _detect_file_type(svg_file) == 'text'

    def test_detects_binary_by_extension(self):
        """Known binary extensions are detected."""
        with TemporaryDirectory() as tmpdir:
            for ext in ['.exe', '.zip', '.tar', '.dll', '.so']:
                bin_file = Path(tmpdir) / f"file{ext}"
                bin_file.write_bytes(b"binary content")
                
                assert _detect_file_type(bin_file) == 'binary', f"Failed for {ext}"

    def test_unknown_extension_uses_content_detection(self):
        """Unknown extensions fall back to content-based detection."""
        with TemporaryDirectory() as tmpdir:
            # Text content with unknown extension
            text_file = Path(tmpdir) / "file.xyz"
            text_file.write_text("This is plain text content")
            
            assert _detect_file_type(text_file) == 'text'

    def test_unknown_extension_binary_content(self):
        """Unknown extension with binary content detected as binary."""
        with TemporaryDirectory() as tmpdir:
            binary_file = Path(tmpdir) / "file.xyz"
            binary_file.write_bytes(b"\x00\x01\x02\x03\x04\x05" * 100)
            
            assert _detect_file_type(binary_file) == 'binary'


# =============================================================================
# _truncate_text_content Tests
# =============================================================================

class TestTruncateTextContent:
    """Tests for _truncate_text_content function."""

    def test_empty_string_produces_single_empty_line(self):
        """Empty string results in single line with line number.
        
        Note: The implementation treats '' as having 1 empty line,
        not as a truly empty file. Line 1 will be empty.
        """
        result = _truncate_text_content("")
        # Empty string splits to [''], which has 1 element
        assert "1\t" in result

    def test_formats_with_line_numbers(self):
        """Output includes line numbers."""
        content = "line 1\nline 2\nline 3"
        result = _truncate_text_content(content)
        
        assert "1\t" in result
        assert "2\t" in result
        assert "3\t" in result

    def test_respects_offset_parameter(self):
        """Offset parameter starts reading from specified line."""
        content = "line 1\nline 2\nline 3\nline 4\nline 5"
        result = _truncate_text_content(content, offset=3)
        
        # Should start from line 3
        assert "line 3" in result
        assert "line 4" in result
        # Line 1 should not be in content (but may be in header)
        lines = result.split('\n')
        content_lines = [l for l in lines if '\tline' in l]
        assert not any('line 1' in l for l in content_lines)

    def test_respects_limit_parameter(self):
        """Limit parameter restricts number of lines."""
        content = "\n".join([f"line {i}" for i in range(1, 101)])
        result = _truncate_text_content(content, limit=5)
        
        # Should only have 5 lines of actual content
        lines = result.split('\n')
        content_lines = [l for l in lines if '\tline' in l]
        assert len(content_lines) == 5

    def test_offset_and_limit_combined(self):
        """Offset and limit work together."""
        content = "\n".join([f"line {i}" for i in range(1, 21)])
        result = _truncate_text_content(content, offset=5, limit=3)
        
        # Should show lines 5, 6, 7
        assert "line 5" in result
        assert "line 6" in result
        assert "line 7" in result

    def test_truncates_long_lines(self):
        """Lines longer than MAX_LINE_LENGTH are truncated."""
        long_line = "x" * (MAX_LINE_LENGTH + 100)
        content = f"short line\n{long_line}\nanother short"
        result = _truncate_text_content(content)
        
        assert "[truncated]" in result

    def test_truncation_message_when_exceeds_max_lines(self):
        """Shows truncation message when file exceeds MAX_FILE_READ_LINES."""
        # Create content with more than MAX_FILE_READ_LINES
        content = "\n".join([f"line {i}" for i in range(1, MAX_FILE_READ_LINES + 100)])
        result = _truncate_text_content(content)
        
        assert "truncated" in result.lower()
        assert str(MAX_FILE_READ_LINES + 99) in result  # total lines

    def test_preserves_content_integrity(self):
        """Content is preserved correctly within limits."""
        content = "first\nsecond\nthird"
        result = _truncate_text_content(content)
        
        assert "first" in result
        assert "second" in result
        assert "third" in result


# =============================================================================
# _read_image_file Tests
# =============================================================================

class TestReadImageFile:
    """Tests for _read_image_file function."""

    def test_reads_png_image(self):
        """PNG images are read and base64 encoded."""
        with TemporaryDirectory() as tmpdir:
            # Create a minimal valid PNG
            png_file = Path(tmpdir) / "test.png"
            # PNG magic bytes + minimal header
            png_data = bytes([
                0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # PNG signature
                0x00, 0x00, 0x00, 0x0D,  # IHDR chunk length
                0x49, 0x48, 0x44, 0x52,  # "IHDR"
                0x00, 0x00, 0x00, 0x01,  # width: 1
                0x00, 0x00, 0x00, 0x01,  # height: 1
                0x08, 0x02,              # bit depth: 8, color type: 2 (RGB)
                0x00, 0x00, 0x00,        # compression, filter, interlace
                0x90, 0x77, 0x53, 0xDE,  # CRC
            ])
            png_file.write_bytes(png_data)
            
            result = _read_image_file(png_file)
            
            assert isinstance(result, list)
            assert len(result) == 1
            assert isinstance(result[0], ImageContent)
            assert result[0].type == "image"
            assert "png" in result[0].mime_type

    def test_reads_jpeg_image(self):
        """JPEG images are read correctly."""
        with TemporaryDirectory() as tmpdir:
            jpeg_file = Path(tmpdir) / "test.jpg"
            # JPEG magic bytes
            jpeg_data = bytes([0xFF, 0xD8, 0xFF, 0xE0]) + b"fake jpeg content"
            jpeg_file.write_bytes(jpeg_data)
            
            result = _read_image_file(jpeg_file)
            
            assert isinstance(result, list)
            assert len(result) == 1
            assert "jpeg" in result[0].mime_type or "jpg" in result[0].mime_type

    def test_returns_base64_data(self):
        """Image data is base64 encoded."""
        with TemporaryDirectory() as tmpdir:
            img_file = Path(tmpdir) / "test.gif"
            # GIF magic bytes
            gif_data = b"GIF89a" + bytes([0x01, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00])
            img_file.write_bytes(gif_data)
            
            result = _read_image_file(img_file)
            
            # Verify it's valid base64
            decoded = base64.b64decode(result[0].data)
            assert decoded.startswith(b"GIF89a")

    def test_unknown_format_falls_back_to_mimetype(self):
        """Unknown image formats fall back to mimetypes guess."""
        with TemporaryDirectory() as tmpdir:
            fake_img = Path(tmpdir) / "fake.xyz"
            fake_img.write_bytes(b"not an image")
            
            # Doesn't raise - falls back to mimetypes
            result = _read_image_file(fake_img)
            
            assert isinstance(result, list)
            assert len(result) == 1
            # mime_type is guessed from extension


# =============================================================================
# FileReadTool Tests
# =============================================================================

class TestFileReadTool:
    """Tests for FileReadTool class."""

    @pytest.fixture
    def workspace(self):
        """Create a temporary workspace."""
        with TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def tool(self, workspace):
        """Create a FileReadTool instance."""
        manager = WorkspaceManager(workspace)
        return FileReadTool(manager)

    def test_tool_attributes(self, tool):
        """FileReadTool has correct attributes."""
        assert tool.name == "Read"
        assert tool.display_name == "Read file"
        assert tool.read_only is True
        assert "file_path" in tool.input_schema["required"]

    @pytest.mark.asyncio
    async def test_read_text_file(self, tool, workspace):
        """Reading a text file returns content."""
        test_file = Path(workspace) / "test.txt"
        test_file.write_text("Hello, World!\nLine 2")
        
        result = await tool.execute({"file_path": str(test_file)})
        
        assert isinstance(result, ToolResult)
        assert result.is_error is False
        assert "Hello, World!" in result.llm_content
        assert "Line 2" in result.llm_content

    @pytest.mark.asyncio
    async def test_read_with_offset(self, tool, workspace):
        """Reading with offset skips initial lines."""
        test_file = Path(workspace) / "multiline.txt"
        test_file.write_text("line 1\nline 2\nline 3\nline 4")
        
        result = await tool.execute({
            "file_path": str(test_file),
            "offset": 2
        })
        
        assert result.is_error is False
        assert "line 2" in result.llm_content

    @pytest.mark.asyncio
    async def test_read_with_limit(self, tool, workspace):
        """Reading with limit restricts output."""
        test_file = Path(workspace) / "multiline.txt"
        test_file.write_text("\n".join([f"line {i}" for i in range(1, 101)]))
        
        result = await tool.execute({
            "file_path": str(test_file),
            "limit": 5
        })
        
        assert result.is_error is False

    @pytest.mark.asyncio
    async def test_invalid_offset_returns_error(self, tool, workspace):
        """Offset < 1 returns error."""
        test_file = Path(workspace) / "test.txt"
        test_file.write_text("content")
        
        result = await tool.execute({
            "file_path": str(test_file),
            "offset": 0
        })
        
        assert result.is_error is True
        assert "Offset" in result.llm_content

    @pytest.mark.asyncio
    async def test_invalid_limit_returns_error(self, tool, workspace):
        """Limit < 1 returns error."""
        test_file = Path(workspace) / "test.txt"
        test_file.write_text("content")
        
        result = await tool.execute({
            "file_path": str(test_file),
            "limit": 0
        })
        
        assert result.is_error is True
        assert "Limit" in result.llm_content

    @pytest.mark.asyncio
    async def test_nonexistent_file_returns_error(self, tool, workspace):
        """Nonexistent files return error."""
        result = await tool.execute({
            "file_path": os.path.join(workspace, "nonexistent.txt")
        })
        
        assert result.is_error is True
        assert "ERROR" in result.llm_content

    @pytest.mark.asyncio
    async def test_path_outside_workspace_returns_error(self, tool, workspace):
        """Paths outside workspace return error."""
        result = await tool.execute({
            "file_path": "/etc/passwd"
        })
        
        assert result.is_error is True

    @pytest.mark.asyncio
    async def test_binary_file_returns_error(self, tool, workspace):
        """Binary files return error."""
        binary_file = Path(workspace) / "binary.exe"
        binary_file.write_bytes(b"\x00\x01\x02\x03" * 100)
        
        result = await tool.execute({
            "file_path": str(binary_file)
        })
        
        assert result.is_error is True
        assert "binary" in result.llm_content.lower()

    @pytest.mark.asyncio
    async def test_read_image_returns_image_content(self, tool, workspace):
        """Reading supported images returns ImageContent."""
        png_file = Path(workspace) / "test.png"
        # Minimal PNG
        png_data = bytes([
            0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,
            0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,
            0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
            0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53, 0xDE,
        ])
        png_file.write_bytes(png_data)
        
        result = await tool.execute({"file_path": str(png_file)})
        
        assert result.is_error is False
        assert isinstance(result.llm_content, list)
        assert isinstance(result.llm_content[0], ImageContent)


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Edge case tests for file reading."""

    @pytest.fixture
    def workspace(self):
        with TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def tool(self, workspace):
        manager = WorkspaceManager(workspace)
        return FileReadTool(manager)

    @pytest.mark.asyncio
    async def test_empty_file(self, tool, workspace):
        """Empty files are handled gracefully.
        
        Note: Empty files return single line with line number 1.
        """
        empty_file = Path(workspace) / "empty.txt"
        empty_file.write_text("")
        
        result = await tool.execute({"file_path": str(empty_file)})
        
        assert result.is_error is False
        # Empty file shows as single empty line with line number
        assert "1\t" in result.llm_content

    @pytest.mark.asyncio
    async def test_file_with_special_characters(self, tool, workspace):
        """Files with special characters in name work."""
        special_file = Path(workspace) / "file with spaces.txt"
        special_file.write_text("content")
        
        result = await tool.execute({"file_path": str(special_file)})
        
        assert result.is_error is False

    @pytest.mark.asyncio
    async def test_unicode_content(self, tool, workspace):
        """Unicode content is handled correctly."""
        unicode_file = Path(workspace) / "unicode.txt"
        unicode_file.write_text("Hello 世界 🌍 Привет", encoding="utf-8")
        
        result = await tool.execute({"file_path": str(unicode_file)})
        
        assert result.is_error is False
        assert "世界" in result.llm_content
        assert "🌍" in result.llm_content

    @pytest.mark.asyncio
    async def test_deeply_nested_file(self, tool, workspace):
        """Files in deeply nested directories work."""
        nested_dir = Path(workspace) / "a" / "b" / "c" / "d"
        nested_dir.mkdir(parents=True)
        nested_file = nested_dir / "deep.txt"
        nested_file.write_text("deep content")
        
        result = await tool.execute({"file_path": str(nested_file)})
        
        assert result.is_error is False
        assert "deep content" in result.llm_content
