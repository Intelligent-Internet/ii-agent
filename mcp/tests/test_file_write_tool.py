"""Comprehensive tests for FileWriteTool."""

import pytest
import tempfile
import os
import shutil
import stat
from pathlib import Path
from unittest.mock import Mock, patch, mock_open

# Add src to path for imports
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from tools.file_system.file_write_tool import FileWriteTool
from core.workspace import WorkspaceManager


class TestFileWriteTool:
    """Test class for FileWriteTool functionality."""

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
    def file_write_tool(self, workspace_manager):
        """Create a FileWriteTool instance."""
        return FileWriteTool(workspace_manager)

    def test_tool_initialization(self, file_write_tool):
        """Test that the tool initializes correctly."""
        assert file_write_tool.name == "Write"
        assert "Writes a file to the local filesystem" in file_write_tool.description
        assert file_write_tool.workspace_manager is not None

    # Success scenarios
    def test_create_new_file_simple(self, file_write_tool, temp_workspace):
        """Test creating a new file with simple content."""
        test_file = temp_workspace / "new_file.txt"
        content = "Hello, World!\nThis is a new file."
        
        result = file_write_tool.run_impl(
            file_path=str(test_file),
            content=content
        )
        
        assert "Successfully created and wrote to new file" in result
        assert test_file.exists()
        assert test_file.read_text(encoding='utf-8') == content

    def test_create_new_file_with_nested_directories(self, file_write_tool, temp_workspace):
        """Test creating a new file in nested directories that don't exist."""
        test_file = temp_workspace / "subdir" / "nested" / "deep" / "new_file.txt"
        content = "File in deeply nested directory"
        
        result = file_write_tool.run_impl(
            file_path=str(test_file),
            content=content
        )
        
        assert "Successfully created and wrote to new file" in result
        assert test_file.exists()
        assert test_file.read_text(encoding='utf-8') == content
        assert test_file.parent.exists()

    def test_overwrite_existing_file(self, file_write_tool, temp_workspace):
        """Test overwriting an existing file."""
        test_file = temp_workspace / "existing_file.txt"
        original_content = "Original content"
        new_content = "New content that replaces the original"
        
        # Create existing file
        test_file.write_text(original_content, encoding='utf-8')
        assert test_file.read_text(encoding='utf-8') == original_content
        
        result = file_write_tool.run_impl(
            file_path=str(test_file),
            content=new_content
        )
        
        assert "Successfully overwrote file" in result
        assert test_file.read_text(encoding='utf-8') == new_content

    def test_write_empty_content(self, file_write_tool, temp_workspace):
        """Test writing empty content to a file."""
        test_file = temp_workspace / "empty_file.txt"
        content = ""
        
        result = file_write_tool.run_impl(
            file_path=str(test_file),
            content=content
        )
        
        assert "Successfully created and wrote to new file" in result
        assert test_file.exists()
        assert test_file.read_text(encoding='utf-8') == ""

    def test_write_unicode_content(self, file_write_tool, temp_workspace):
        """Test writing Unicode content to a file."""
        test_file = temp_workspace / "unicode_file.txt"
        content = "Hello 世界! 🌍\nЗдравствуй мир!\n¡Hola mundo! 🎉"
        
        result = file_write_tool.run_impl(
            file_path=str(test_file),
            content=content
        )
        
        assert "Successfully created and wrote to new file" in result
        assert test_file.exists()
        assert test_file.read_text(encoding='utf-8') == content

    def test_write_large_content(self, file_write_tool, temp_workspace):
        """Test writing large content to a file."""
        test_file = temp_workspace / "large_file.txt"
        # Create content larger than typical buffer size
        content = "".join(f"Line {i}\n" for i in range(10000))
        
        result = file_write_tool.run_impl(
            file_path=str(test_file),
            content=content
        )
        
        assert "Successfully created and wrote to new file" in result
        assert test_file.exists()
        assert test_file.read_text(encoding='utf-8') == content

    def test_write_multiline_content(self, file_write_tool, temp_workspace):
        """Test writing multiline content with various line endings."""
        test_file = temp_workspace / "multiline_file.py"
        content = '''def hello_world():
    """A simple hello world function."""
    print("Hello, World!")
    return "success"

if __name__ == "__main__":
    result = hello_world()
    print(f"Result: {result}")
'''
        
        result = file_write_tool.run_impl(
            file_path=str(test_file),
            content=content
        )
        
        assert "Successfully created and wrote to new file" in result
        assert test_file.exists()
        assert test_file.read_text(encoding='utf-8') == content

    def test_write_special_characters(self, file_write_tool, temp_workspace):
        """Test writing content with special characters."""
        test_file = temp_workspace / "special_chars.txt"
        content = 'Special chars: !@#$%^&*()[]{}|\\:";\'<>?,.`~\n\t'
        
        result = file_write_tool.run_impl(
            file_path=str(test_file),
            content=content
        )
        
        assert "Successfully created and wrote to new file" in result
        assert test_file.exists()
        assert test_file.read_text(encoding='utf-8') == content

    # Error scenarios
    def test_error_relative_path(self, file_write_tool):
        """Test error when using relative path."""
        result = file_write_tool.run_impl(
            file_path="relative/path/file.txt",
            content="test content"
        )
        
        assert "Error: File path must be absolute" in result

    def test_error_path_outside_workspace(self, file_write_tool, temp_workspace):
        """Test error when path is outside workspace boundary."""
        # Create a path outside the workspace
        outside_path = Path(temp_workspace).parent / "outside_workspace" / "file.txt"
        
        result = file_write_tool.run_impl(
            file_path=str(outside_path),
            content="test content"
        )
        
        assert "Error: File path must be within the workspace directory" in result

    def test_error_path_is_directory(self, file_write_tool, temp_workspace):
        """Test error when trying to write to an existing directory."""
        # Create a directory
        test_dir = temp_workspace / "test_directory"
        test_dir.mkdir()
        
        result = file_write_tool.run_impl(
            file_path=str(test_dir),
            content="test content"
        )
        
        assert "Error: Path is a directory, not a file" in result

    @pytest.mark.skipif(os.name == 'nt', reason="Permission testing complex on Windows")
    def test_error_permission_denied(self, file_write_tool, temp_workspace):
        """Test error when permission is denied."""
        # Create a directory with no write permissions
        no_write_dir = temp_workspace / "no_write"
        no_write_dir.mkdir()
        no_write_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)  # Read and execute only
        
        test_file = no_write_dir / "file.txt"
        
        result = file_write_tool.run_impl(
            file_path=str(test_file),
            content="test content"
        )
        
        assert "Error: Permission denied when writing to file" in result
        
        # Cleanup: restore permissions for directory cleanup
        no_write_dir.chmod(stat.S_IRWXU)

    def test_error_invalid_path_characters(self, file_write_tool, temp_workspace):
        """Test handling of invalid path characters (OS-specific)."""
        if os.name == 'nt':  # Windows
            invalid_chars = '<>:"|?*'
            for char in invalid_chars:
                result = file_write_tool.run_impl(
                    file_path=str(temp_workspace / f"invalid{char}file.txt"),
                    content="test content"
                )
                # Should handle gracefully without crashing
                assert "Error:" in result

    # Edge cases
    def test_write_to_root_of_workspace(self, file_write_tool, temp_workspace):
        """Test writing directly to workspace root."""
        test_file = temp_workspace / "root_file.txt"
        content = "File at workspace root"
        
        result = file_write_tool.run_impl(
            file_path=str(test_file),
            content=content
        )
        
        assert "Successfully created and wrote to new file" in result
        assert test_file.exists()

    def test_overwrite_multiple_times(self, file_write_tool, temp_workspace):
        """Test overwriting the same file multiple times."""
        test_file = temp_workspace / "multi_overwrite.txt"
        
        # First write
        result1 = file_write_tool.run_impl(
            file_path=str(test_file),
            content="First content"
        )
        assert "Successfully created and wrote to new file" in result1
        assert test_file.read_text(encoding='utf-8') == "First content"
        
        # Second write (overwrite)
        result2 = file_write_tool.run_impl(
            file_path=str(test_file),
            content="Second content"
        )
        assert "Successfully overwrote file" in result2
        assert test_file.read_text(encoding='utf-8') == "Second content"
        
        # Third write (overwrite again)
        result3 = file_write_tool.run_impl(
            file_path=str(test_file),
            content="Third content"
        )
        assert "Successfully overwrote file" in result3
        assert test_file.read_text(encoding='utf-8') == "Third content"

    def test_write_with_long_filename(self, file_write_tool, temp_workspace):
        """Test writing file with very long filename."""
        # Create a long but valid filename
        long_name = "a" * 200 + ".txt"
        test_file = temp_workspace / long_name
        content = "File with long name"
        
        result = file_write_tool.run_impl(
            file_path=str(test_file),
            content=content
        )
        
        # May succeed or fail depending on filesystem limits
        # Just ensure it doesn't crash
        assert "Error:" in result or "Successfully" in result

    def test_concurrent_directory_creation(self, file_write_tool, temp_workspace):
        """Test that directory creation works when multiple levels don't exist."""
        test_file = temp_workspace / "a" / "b" / "c" / "d" / "e" / "file.txt"
        content = "Deep file"
        
        result = file_write_tool.run_impl(
            file_path=str(test_file),
            content=content
        )
        
        assert "Successfully created and wrote to new file" in result
        assert test_file.exists()
        assert test_file.read_text(encoding='utf-8') == content

    # Mock testing for specific error conditions
    @patch('pathlib.Path.write_text')
    def test_os_error_handling(self, mock_write_text, file_write_tool, temp_workspace):
        """Test handling of OS errors during write."""
        mock_write_text.side_effect = OSError("Disk full")
        
        test_file = temp_workspace / "test.txt"
        
        result = file_write_tool.run_impl(
            file_path=str(test_file),
            content="test content"
        )
        
        assert "Error: OS error when writing to file" in result
        assert "Disk full" in result

    @patch('pathlib.Path.write_text')
    def test_unexpected_error_handling(self, mock_write_text, file_write_tool, temp_workspace):
        """Test handling of unexpected errors."""
        mock_write_text.side_effect = ValueError("Unexpected error")
        
        test_file = temp_workspace / "test.txt"
        
        result = file_write_tool.run_impl(
            file_path=str(test_file),
            content="test content"
        )
        
        assert "Error: Unexpected error when writing to file" in result
        assert "Unexpected error" in result

    @patch('pathlib.Path.mkdir')
    def test_directory_creation_error(self, mock_mkdir, file_write_tool, temp_workspace):
        """Test handling of directory creation errors."""
        mock_mkdir.side_effect = OSError("Cannot create directory")
        
        test_file = temp_workspace / "new_dir" / "test.txt"
        
        result = file_write_tool.run_impl(
            file_path=str(test_file),
            content="test content"
        )
        
        assert "Error:" in result


class TestFileWriteToolIntegration:
    """Integration tests for FileWriteTool with realistic scenarios."""

    @pytest.fixture
    def real_workspace(self):
        """Create a realistic temporary workspace with some structure."""
        temp_dir = Path(tempfile.mkdtemp())
        
        # Create some realistic directory structure
        (temp_dir / "src").mkdir()
        (temp_dir / "tests").mkdir()
        (temp_dir / "docs").mkdir()
        (temp_dir / "config").mkdir()
        
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.mark.integration
    def test_realistic_code_file_creation(self, real_workspace):
        """Test creating realistic code files."""
        workspace_manager = WorkspaceManager(str(real_workspace))
        tool = FileWriteTool(workspace_manager)
        
        # Create a Python module
        python_file = real_workspace / "src" / "utils.py"
        python_content = '''"""Utility functions for the application."""

import os
import sys
from typing import List, Optional


def get_file_extension(filename: str) -> str:
    """Get the file extension from a filename."""
    return os.path.splitext(filename)[1]


def validate_path(path: str) -> bool:
    """Validate that a path is safe to use."""
    return os.path.exists(path) and os.path.isfile(path)


class FileProcessor:
    """Process files in various ways."""
    
    def __init__(self, base_path: str):
        self.base_path = base_path
    
    def process_files(self, patterns: List[str]) -> Optional[List[str]]:
        """Process files matching given patterns."""
        results = []
        for pattern in patterns:
            # Implementation here
            results.append(f"Processed: {pattern}")
        return results
'''
        
        result = tool.run_impl(
            file_path=str(python_file),
            content=python_content
        )
        
        assert "Successfully created and wrote to new file" in result
        assert python_file.exists()
        # Verify it's valid Python by compiling
        compile(python_content, str(python_file), 'exec')

    @pytest.mark.integration
    def test_realistic_config_file_creation(self, real_workspace):
        """Test creating realistic configuration files."""
        workspace_manager = WorkspaceManager(str(real_workspace))
        tool = FileWriteTool(workspace_manager)
        
        # Create a JSON config file
        config_file = real_workspace / "config" / "settings.json"
        config_content = '''{
  "app_name": "Test Application",
  "version": "1.0.0",
  "database": {
    "host": "localhost",
    "port": 5432,
    "name": "testdb"
  },
  "features": {
    "logging": true,
    "debug_mode": false,
    "max_connections": 100
  },
  "paths": {
    "data_dir": "/var/data",
    "log_dir": "/var/log",
    "temp_dir": "/tmp"
  }
}'''
        
        result = tool.run_impl(
            file_path=str(config_file),
            content=config_content
        )
        
        assert "Successfully created and wrote to new file" in result
        assert config_file.exists()
        
        # Verify it's valid JSON
        import json
        json.loads(config_content)

    @pytest.mark.integration
    def test_realistic_documentation_creation(self, real_workspace):
        """Test creating realistic documentation files."""
        workspace_manager = WorkspaceManager(str(real_workspace))
        tool = FileWriteTool(workspace_manager)
        
        # Create a README file
        readme_file = real_workspace / "README.md"
        readme_content = '''# Test Project

A comprehensive test project for demonstrating file operations.

## Features

- File writing capabilities
- Path validation
- Error handling
- Unicode support

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```python
from src.utils import FileProcessor

processor = FileProcessor("/path/to/files")
results = processor.process_files(["*.txt", "*.py"])
print(results)
```

## Testing

Run tests with:

```bash
pytest tests/
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests
5. Submit a pull request

## License

MIT License - see LICENSE file for details.
'''
        
        result = tool.run_impl(
            file_path=str(readme_file),
            content=readme_content
        )
        
        assert "Successfully created and wrote to new file" in result
        assert readme_file.exists()
        assert "# Test Project" in readme_file.read_text(encoding='utf-8') 