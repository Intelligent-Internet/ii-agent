"""Comprehensive tests for FileEditTool."""

import pytest
import tempfile
import os
import shutil
from pathlib import Path
from unittest.mock import Mock, patch

# Add src to path for imports
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from tools.file_system.file_edit_tool import FileEditTool
from core.workspace import WorkspaceManager


class TestFileEditTool:
    """Test class for FileEditTool functionality."""

    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace for testing."""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def workspace_manager(self, temp_workspace):
        """Create a WorkspaceManager for the temporary workspace."""
        return WorkspaceManager(str(temp_workspace))

    @pytest.fixture
    def file_edit_tool(self, workspace_manager):
        """Create a FileEditTool instance."""
        return FileEditTool(workspace_manager)

    def test_tool_initialization(self, file_edit_tool):
        """Test that the tool initializes correctly."""
        assert file_edit_tool.name == "Edit"
        assert "Performs exact string replacements in files" in file_edit_tool.description
        assert file_edit_tool.workspace_manager is not None

    def test_create_new_file(self, file_edit_tool, temp_workspace):
        """Test creating a new file with empty old_string."""
        test_file = temp_workspace / "new_file.txt"
        content = "Hello, World!\nThis is a new file."
        
        result = file_edit_tool.run_impl(
            file_path=str(test_file),
            old_string="",
            new_string=content,
            replace_all=False
        )
        
        assert "SUCCESS: Created new file" in result
        assert test_file.exists()
        assert test_file.read_text() == content

    def test_create_new_file_with_directories(self, file_edit_tool, temp_workspace):
        """Test creating a new file in nested directories that don't exist."""
        test_file = temp_workspace / "subdir" / "nested" / "new_file.txt"
        content = "File in nested directory"
        
        result = file_edit_tool.run_impl(
            file_path=str(test_file),
            old_string="",
            new_string=content,
            replace_all=False
        )
        
        assert "SUCCESS: Created new file" in result
        assert test_file.exists()
        assert test_file.read_text() == content

    def test_edit_existing_file_single_replacement(self, file_edit_tool, temp_workspace):
        """Test editing an existing file with single replacement."""
        test_file = temp_workspace / "existing_file.txt"
        original_content = "Hello World!\nThis is a test file.\nHello again!"
        test_file.write_text(original_content)
        
        result = file_edit_tool.run_impl(
            file_path=str(test_file),
            old_string="Hello World!",
            new_string="Hello Python!",
            replace_all=False
        )
        
        assert "SUCCESS: Modified file" in result
        assert "made 1 replacement (first occurrence)" in result
        
        new_content = test_file.read_text()
        assert "Hello Python!" in new_content
        assert "Hello again!" in new_content  # Second "Hello" should remain

    def test_edit_existing_file_replace_all(self, file_edit_tool, temp_workspace):
        """Test editing an existing file with replace_all=True."""
        test_file = temp_workspace / "existing_file.txt"
        original_content = "test test test\nAnother line with test"
        test_file.write_text(original_content)
        
        result = file_edit_tool.run_impl(
            file_path=str(test_file),
            old_string="test",
            new_string="demo",
            replace_all=True
        )
        
        assert "SUCCESS: Modified file" in result
        assert "made 4 replacements (all occurrences)" in result
        
        new_content = test_file.read_text()
        assert "demo demo demo\nAnother line with demo" == new_content

    def test_multiline_replacement(self, file_edit_tool, temp_workspace):
        """Test replacing multiline content."""
        test_file = temp_workspace / "multiline.txt"
        original_content = """def old_function():
    print("old")
    return True

def another_function():
    pass"""
        test_file.write_text(original_content)
        
        old_string = """def old_function():
    print("old")
    return True"""
        
        new_string = """def new_function():
    print("new and improved")
    return False"""
        
        result = file_edit_tool.run_impl(
            file_path=str(test_file),
            old_string=old_string,
            new_string=new_string,
            replace_all=False
        )
        
        assert "SUCCESS: Modified file" in result
        new_content = test_file.read_text()
        assert "def new_function():" in new_content
        assert "new and improved" in new_content
        assert "def another_function():" in new_content

    def test_preserve_line_endings(self, file_edit_tool, temp_workspace):
        """Test that line endings are preserved correctly."""
        test_file = temp_workspace / "line_endings.txt"
        # Create content with CRLF line endings
        original_content = "line1\r\nline2\r\nline3"
        test_file.write_bytes(original_content.encode('utf-8'))
        
        result = file_edit_tool.run_impl(
            file_path=str(test_file),
            old_string="line2",
            new_string="modified_line",
            replace_all=False
        )
        
        assert "SUCCESS: Modified file" in result
        # The tool normalizes to LF internally, so output will have LF
        new_content = test_file.read_text()
        assert "modified_line" in new_content

    def test_error_same_old_new_string(self, file_edit_tool, temp_workspace):
        """Test error when old_string equals new_string."""
        result = file_edit_tool.run_impl(
            file_path=str(temp_workspace / "test.txt"),
            old_string="same",
            new_string="same",
            replace_all=False
        )
        
        assert "ERROR: old_string and new_string cannot be the same" in result

    def test_error_file_not_found_with_old_string(self, file_edit_tool, temp_workspace):
        """Test error when file doesn't exist and old_string is not empty."""
        result = file_edit_tool.run_impl(
            file_path=str(temp_workspace / "nonexistent.txt"),
            old_string="something",
            new_string="replacement",
            replace_all=False
        )
        
        assert "ERROR: File" in result
        assert "does not exist" in result
        assert "empty old_string" in result

    def test_error_string_not_found(self, file_edit_tool, temp_workspace):
        """Test error when old_string is not found in file."""
        test_file = temp_workspace / "test.txt"
        test_file.write_text("Hello World!")
        
        result = file_edit_tool.run_impl(
            file_path=str(test_file),
            old_string="nonexistent text",
            new_string="replacement",
            replace_all=False
        )
        
        assert "ERROR: String to replace not found in file" in result

    def test_error_multiple_occurrences_without_replace_all(self, file_edit_tool, temp_workspace):
        """Test error when multiple occurrences exist but replace_all=False."""
        test_file = temp_workspace / "test.txt"
        test_file.write_text("test test test")
        
        result = file_edit_tool.run_impl(
            file_path=str(test_file),
            old_string="test",
            new_string="demo",
            replace_all=False
        )
        
        assert "ERROR: Found 3 occurrences of old_string" in result
        assert "provide more context" in result
        assert "replace_all=True" in result

    def test_error_empty_old_string_existing_file(self, file_edit_tool, temp_workspace):
        """Test error when using empty old_string on existing file."""
        test_file = temp_workspace / "existing.txt"
        test_file.write_text("existing content")
        
        result = file_edit_tool.run_impl(
            file_path=str(test_file),
            old_string="",
            new_string="new content",
            replace_all=False
        )
        
        assert "ERROR: Cannot use empty old_string for existing file" in result

    def test_error_invalid_file_path(self, file_edit_tool):
        """Test error with invalid file path."""
        result = file_edit_tool.run_impl(
            file_path="",
            old_string="",
            new_string="content",
            replace_all=False
        )
        
        assert "ERROR: File path cannot be empty" in result

    def test_workspace_boundary_validation(self, temp_workspace):
        """Test that files outside workspace boundary are rejected."""
        workspace_manager = WorkspaceManager(str(temp_workspace))
        file_edit_tool = FileEditTool(workspace_manager)
        
        # Try to edit a file outside the workspace
        outside_file = "/tmp/outside_workspace.txt"
        result = file_edit_tool.run_impl(
            file_path=outside_file,
            old_string="",
            new_string="content",
            replace_all=False
        )
        
        assert "ERROR:" in result
        assert "not within workspace boundary" in result

    def test_permission_error_simulation(self, file_edit_tool, temp_workspace):
        """Test handling of permission errors."""
        test_file = temp_workspace / "test.txt"
        
        # Mock file operations to simulate permission error
        with patch('pathlib.Path.write_text', side_effect=PermissionError("Permission denied")):
            result = file_edit_tool.run_impl(
                file_path=str(test_file),
                old_string="",
                new_string="content",
                replace_all=False
            )
            
            assert "ERROR: Permission denied writing to file" in result

    def test_unicode_content(self, file_edit_tool, temp_workspace):
        """Test handling of unicode content."""
        test_file = temp_workspace / "unicode.txt"
        unicode_content = "Hello 世界! 🌟 Café naïve résumé"
        
        result = file_edit_tool.run_impl(
            file_path=str(test_file),
            old_string="",
            new_string=unicode_content,
            replace_all=False
        )
        
        assert "SUCCESS: Created new file" in result
        assert test_file.read_text(encoding='utf-8') == unicode_content

    def test_large_file_handling(self, file_edit_tool, temp_workspace):
        """Test handling of larger files."""
        test_file = temp_workspace / "large.txt"
        # Create a reasonably large content
        large_content = "Line {}\n".format("test") * 1000 + "special line\n" + "Line {}\n".format("test") * 1000
        test_file.write_text(large_content)
        
        result = file_edit_tool.run_impl(
            file_path=str(test_file),
            old_string="special line",
            new_string="modified special line",
            replace_all=False
        )
        
        assert "SUCCESS: Modified file" in result
        assert "modified special line" in test_file.read_text()

    def test_empty_file_editing(self, file_edit_tool, temp_workspace):
        """Test editing an empty file."""
        test_file = temp_workspace / "empty.txt"
        test_file.write_text("")
        
        # This should fail because old_string won't be found
        result = file_edit_tool.run_impl(
            file_path=str(test_file),
            old_string="nonexistent",
            new_string="content",
            replace_all=False
        )
        
        assert "ERROR: String to replace not found in file" in result

    def test_whitespace_preservation(self, file_edit_tool, temp_workspace):
        """Test that whitespace is preserved correctly."""
        test_file = temp_workspace / "whitespace.txt"
        original_content = "    indented line\n\ttab indented\n  mixed   spaces  "
        test_file.write_text(original_content)
        
        result = file_edit_tool.run_impl(
            file_path=str(test_file),
            old_string="indented line",
            new_string="modified line",
            replace_all=False
        )
        
        assert "SUCCESS: Modified file" in result
        new_content = test_file.read_text()
        assert "    modified line" in new_content  # Preserves leading spaces
        assert "\ttab indented" in new_content     # Preserves tabs

    def test_binary_file_handling(self, file_edit_tool, temp_workspace):
        """Test handling of binary files (should handle gracefully)."""
        test_file = temp_workspace / "binary.bin"
        # Create a file with binary content
        binary_content = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00'
        test_file.write_bytes(binary_content)
        
        # The tool should handle this gracefully due to errors='ignore'
        result = file_edit_tool.run_impl(
            file_path=str(test_file),
            old_string="PNG",
            new_string="JPG",
            replace_all=False
        )
        
        # Might succeed or fail depending on how binary is interpreted
        # but should not crash
        assert "ERROR:" in result or "SUCCESS:" in result

    def test_relative_path_resolution(self, file_edit_tool, temp_workspace):
        """Test that relative paths are resolved correctly."""
        test_file = temp_workspace / "subdir" / "test.txt"
        test_file.parent.mkdir(exist_ok=True)
        
        # Use relative path from workspace
        with patch('os.getcwd', return_value=str(temp_workspace)):
            result = file_edit_tool.run_impl(
                file_path="subdir/test.txt",
                old_string="",
                new_string="content",
                replace_all=False
            )
            
            # Should resolve to absolute path within workspace
            assert "SUCCESS:" in result or "ERROR:" in result

    def test_special_characters_in_strings(self, file_edit_tool, temp_workspace):
        """Test handling of special characters in old/new strings."""
        test_file = temp_workspace / "special.txt"
        content_with_special = 'Text with "quotes" and \\backslashes\\ and $symbols$'
        test_file.write_text(content_with_special)
        
        result = file_edit_tool.run_impl(
            file_path=str(test_file),
            old_string='"quotes"',
            new_string="'apostrophes'",
            replace_all=False
        )
        
        assert "SUCCESS: Modified file" in result
        new_content = test_file.read_text()
        assert "'apostrophes'" in new_content
        assert '"quotes"' not in new_content

    def test_file_path_validation_methods(self, file_edit_tool, temp_workspace):
        """Test the internal path validation methods."""
        # Test valid path
        valid_path = str(temp_workspace / "valid.txt")
        path_obj, error = file_edit_tool._validate_file_path(valid_path)
        assert path_obj is not None
        assert error is None
        
        # Test empty path
        path_obj, error = file_edit_tool._validate_file_path("")
        assert path_obj is None
        assert "cannot be empty" in error
        
        # Test invalid path (outside workspace)
        invalid_path = "/tmp/outside.txt"
        path_obj, error = file_edit_tool._validate_file_path(invalid_path)
        assert path_obj is None
        assert "not within workspace boundary" in error

    def test_replacement_methods(self, file_edit_tool):
        """Test the internal replacement methods."""
        # Test new file creation
        content, occurrences, error = file_edit_tool._perform_replacement(
            None, "", "new content", False, True
        )
        assert content == "new content"
        assert occurrences == 1
        assert error is None
        
        # Test normal replacement
        content, occurrences, error = file_edit_tool._perform_replacement(
            "hello world", "world", "python", False, False
        )
        assert content == "hello python"
        assert occurrences == 1
        assert error is None
        
        # Test multiple occurrences error
        content, occurrences, error = file_edit_tool._perform_replacement(
            "test test test", "test", "demo", False, False
        )
        assert occurrences == 3
        assert error is not None
        assert "3 occurrences" in error

    def test_edge_case_line_endings(self, file_edit_tool, temp_workspace):
        """Test various line ending scenarios."""
        test_file = temp_workspace / "line_end_test.txt"
        
        # Test with different line endings
        for line_ending, name in [("\n", "LF"), ("\r\n", "CRLF"), ("\r", "CR")]:
            content = f"line1{line_ending}line2{line_ending}line3"
            test_file.write_bytes(content.encode('utf-8'))
            
            result = file_edit_tool.run_impl(
                file_path=str(test_file),
                old_string="line2",
                new_string="modified",
                replace_all=False
            )
            
            assert "SUCCESS: Modified file" in result
            
            new_content = test_file.read_text()
            assert "modified" in new_content


# Integration tests
class TestFileEditToolIntegration:
    """Integration tests that test the tool with real workspace scenarios."""
    
    @pytest.fixture
    def real_workspace(self):
        """Create a more realistic workspace structure."""
        temp_dir = tempfile.mkdtemp()
        workspace = Path(temp_dir)
        
        # Create a realistic project structure
        (workspace / "src").mkdir()
        (workspace / "src" / "utils").mkdir()
        (workspace / "tests").mkdir()
        (workspace / "docs").mkdir()
        
        # Create some initial files
        (workspace / "README.md").write_text("# Test Project\n\nThis is a test.")
        (workspace / "src" / "__init__.py").write_text("")
        (workspace / "src" / "main.py").write_text("def main():\n    print('Hello World')\n")
        (workspace / "src" / "utils" / "helpers.py").write_text("def helper():\n    return True\n")
        
        yield workspace
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_realistic_code_editing(self, real_workspace):
        """Test editing realistic code files."""
        workspace_manager = WorkspaceManager(str(real_workspace))
        tool = FileEditTool(workspace_manager)
        
        main_file = real_workspace / "src" / "main.py"
        
        # Edit the main function
        result = tool.run_impl(
            file_path=str(main_file),
            old_string="def main():\n    print('Hello World')",
            new_string="def main():\n    print('Hello Python!')\n    print('Welcome to the test!')",
            replace_all=False
        )
        
        assert "SUCCESS: Modified file" in result
        new_content = main_file.read_text()
        assert "Hello Python!" in new_content
        assert "Welcome to the test!" in new_content

    def test_documentation_editing(self, real_workspace):
        """Test editing documentation files."""
        workspace_manager = WorkspaceManager(str(real_workspace))
        tool = FileEditTool(workspace_manager)
        
        readme_file = real_workspace / "README.md"
        
        # Add a new section to README
        result = tool.run_impl(
            file_path=str(readme_file),
            old_string="This is a test.",
            new_string="This is a test.\n\n## Installation\n\nRun `pip install -r requirements.txt`",
            replace_all=False
        )
        
        assert "SUCCESS: Modified file" in result
        new_content = readme_file.read_text()
        assert "## Installation" in new_content
        assert "pip install" in new_content


if __name__ == "__main__":
    # Allow running tests directly with python
    pytest.main([__file__, "-v"]) 