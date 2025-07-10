"""Comprehensive tests for FileReadTool."""

import pytest
import base64
from pathlib import Path


"""Test basic file reading functionality."""

def test_read_python_file(file_read_tool, sample_files):
    """Test reading a Python file."""
    file_path = str(sample_files['python'])
    result = file_read_tool.run_impl(file_path=file_path)
    
    assert isinstance(result, str)
    assert "#!/usr/bin/env python3" in result
    assert "class SampleClass:" in result
    assert "def __init__(self, name: str):" in result
    assert "def main():" in result
    # Check line numbers are present (cat -n format)
    assert "1\t#!/usr/bin/env python3" in result
    
def test_read_json_file(file_read_tool, sample_files):
    """Test reading a JSON configuration file."""
    file_path = str(sample_files['json'])
    result = file_read_tool.run_impl(file_path=file_path)
    
    assert isinstance(result, str)
    assert '"app_name": "test_application"' in result
    assert '"database":' in result
    assert '"features":' in result
    assert '"authentication"' in result
    # Check line numbers are present
    assert "\t{" in result  # Line number followed by tab then content
    
def test_read_yaml_file(file_read_tool, sample_files):
    """Test reading a YAML configuration file."""
    file_path = str(sample_files['yaml'])
    result = file_read_tool.run_impl(file_path=file_path)
    
    assert isinstance(result, str)
    assert "server:" in result
    assert "host: 0.0.0.0" in result
    assert "logging:" in result
    assert "cache:" in result
    
def test_read_javascript_file(file_read_tool, sample_files):
    """Test reading a JavaScript file."""
    file_path = str(sample_files['javascript'])
    result = file_read_tool.run_impl(file_path=file_path)
    
    assert isinstance(result, str)
    assert "/**" in result
    assert "const config = {" in result
    assert "class ApiClient {" in result
    assert "module.exports" in result
    
def test_read_markdown_file(file_read_tool, sample_files):
    """Test reading a Markdown file."""
    file_path = str(sample_files['markdown'])
    result = file_read_tool.run_impl(file_path=file_path)
    
    assert isinstance(result, str)
    assert "# Test Markdown File" in result
    assert "## Features" in result
    assert "- **Bold text**" in result
    assert "```python" in result


class TestFileReadToolLimits:
    """Test file reading with offset and limit parameters."""
    
    def test_read_with_limit(self, file_read_tool, sample_files):
        """Test reading file with limit parameter."""
        file_path = str(sample_files['python'])
        result = file_read_tool.run_impl(file_path=file_path, limit=5)
        
        assert isinstance(result, str)
        lines = result.split('\n')
        # Should have truncation message plus 5 content lines
        assert "File content truncated" in result
        assert "showing lines 1-5" in result
        
    def test_read_with_offset(self, file_read_tool, sample_files):
        """Test reading file with offset parameter."""
        file_path = str(sample_files['python'])
        result = file_read_tool.run_impl(file_path=file_path, offset=10, limit=5)
        
        assert isinstance(result, str)
        assert "showing lines 10-14" in result
        # Should not contain the first line
        assert "#!/usr/bin/env python3" not in result
        
    def test_read_large_file_truncation(self, file_read_tool, sample_files):
        """Test reading a large file that exceeds MAX_FILE_READ_LINES."""
        file_path = str(sample_files['large'])
        result = file_read_tool.run_impl(file_path=file_path)
        
        assert isinstance(result, str)
        assert "File content truncated" in result
        assert "showing lines 1-2000" in result
        assert "of 2500 total lines" in result
        
    def test_read_long_lines_truncation(self, file_read_tool, sample_files):
        """Test reading file with lines exceeding MAX_LINE_LENGTH."""
        file_path = str(sample_files['long_lines'])
        result = file_read_tool.run_impl(file_path=file_path)
        
        assert isinstance(result, str)
        assert "File content partially truncated" in result
        assert "exceeded maximum length" in result
        assert "... [truncated]" in result
        
    def test_read_empty_file(self, file_read_tool, sample_files):
        """Test reading an empty file."""
        file_path = str(sample_files['empty'])
        result = file_read_tool.run_impl(file_path=file_path)
        
        assert result == "[Empty file]"


class TestFileReadToolImages:
    """Test reading image files."""
    
    def test_read_image_file(self, file_read_tool, sample_files):
        """Test reading a PNG image file."""
        file_path = str(sample_files['image'])
        result = file_read_tool.run_impl(file_path=file_path)
        
        assert isinstance(result, dict)
        assert result['type'] == 'base64'
        assert result['media_type'] == 'image/png'
        assert 'data' in result
        assert isinstance(result['data'], str)
        # Verify it's valid base64
        try:
            base64.b64decode(result['data'])
        except Exception as e:
            pytest.fail(f"Invalid base64 data: {e}")


class TestFileReadToolBinary:
    """Test handling of binary files."""
    
    def test_read_binary_file(self, file_read_tool, sample_files):
        """Test reading a binary file should be rejected."""
        file_path = str(sample_files['binary'])
        result = file_read_tool.run_impl(file_path=file_path)
        
        assert isinstance(result, str)
        assert "Cannot display content of binary file" in result


class TestFileReadToolNested:
    """Test reading files in nested directories."""
    
    def test_read_nested_component_file(self, file_read_tool, nested_files):
        """Test reading a TypeScript component file in nested directory."""
        file_path = str(nested_files['component'])
        result = file_read_tool.run_impl(file_path=file_path)
        
        assert isinstance(result, str)
        assert "import React from 'react';" in result
        assert "interface ButtonProps {" in result
        assert "const Button: React.FC<ButtonProps>" in result
        assert "export default Button;" in result
        
    def test_read_nested_test_file(self, file_read_tool, nested_files):
        """Test reading a test file in nested directory."""
        file_path = str(nested_files['test'])
        result = file_read_tool.run_impl(file_path=file_path)
        
        assert isinstance(result, str)
        assert "import { render, screen, fireEvent }" in result
        assert "describe('Button Component'" in result
        assert "test('renders with correct label'" in result


class TestFileReadToolErrors:
    """Test error conditions."""
    
    def test_file_not_found(self, file_read_tool, temp_workspace):
        """Test reading a non-existent file."""
        non_existent = str(temp_workspace / 'does_not_exist.txt')
        result = file_read_tool.run_impl(file_path=non_existent)
        
        assert isinstance(result, str)
        assert "Error: File not found:" in result
        
    def test_read_directory(self, file_read_tool, temp_workspace):
        """Test attempting to read a directory."""
        result = file_read_tool.run_impl(file_path=str(temp_workspace))
        
        assert isinstance(result, str)
        assert "Error: Path is a directory, not a file:" in result
        
    def test_outside_workspace_boundary(self, file_read_tool):
        """Test reading file outside workspace boundary."""
        result = file_read_tool.run_impl(file_path='/etc/passwd')
        
        assert isinstance(result, str)
        assert "Error: File path must be within workspace:" in result
        
    def test_invalid_offset(self, file_read_tool, sample_files):
        """Test reading with invalid offset parameter."""
        file_path = str(sample_files['python'])
        result = file_read_tool.run_impl(file_path=file_path, offset=-1)
        
        assert isinstance(result, str)
        assert "Error: Offset must be a non-negative number" in result
        
    def test_invalid_limit(self, file_read_tool, sample_files):
        """Test reading with invalid limit parameter."""
        file_path = str(sample_files['python'])
        result = file_read_tool.run_impl(file_path=file_path, limit=0)
        
        assert isinstance(result, str)
        assert "Error: Limit must be a positive number" in result
        
    def test_invalid_limit_negative(self, file_read_tool, sample_files):
        """Test reading with negative limit parameter."""
        file_path = str(sample_files['python'])
        result = file_read_tool.run_impl(file_path=file_path, limit=-5)
        
        assert isinstance(result, str)
        assert "Error: Limit must be a positive number" in result


class TestFileReadToolEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_offset_beyond_file_end(self, file_read_tool, sample_files):
        """Test reading with offset beyond file length."""
        file_path = str(sample_files['python'])
        result = file_read_tool.run_impl(file_path=file_path, offset=10000)
        
        assert isinstance(result, str)
        # Should handle gracefully and return empty content when offset is beyond file end
        assert result == ""
        
    def test_limit_larger_than_file(self, file_read_tool, sample_files):
        """Test reading with limit larger than file length."""
        file_path = str(sample_files['python'])
        result = file_read_tool.run_impl(file_path=file_path, limit=10000)
        
        assert isinstance(result, str)
        # Should read entire file without truncation message
        assert "File content truncated" not in result
        assert "#!/usr/bin/env python3" in result
        
    def test_offset_one(self, file_read_tool, sample_files):
        """Test reading from offset 1 (first line)."""
        file_path = str(sample_files['python'])
        result = file_read_tool.run_impl(file_path=file_path, offset=1, limit=3)
        
        assert isinstance(result, str)
        assert "showing lines 1-3" in result
        assert "#!/usr/bin/env python3" in result
        
    def test_single_line_file(self, file_read_tool, temp_workspace):
        """Test reading a single line file."""
        single_line_file = temp_workspace / 'single_line.txt'
        single_line_file.write_text('This is a single line file.')
        
        result = file_read_tool.run_impl(file_path=str(single_line_file))
        
        assert isinstance(result, str)
        assert "This is a single line file." in result
        assert "1\tThis is a single line file." in result
        
    def test_file_with_unicode_content(self, file_read_tool, temp_workspace):
        """Test reading file with Unicode characters."""
        unicode_file = temp_workspace / 'unicode.txt'
        unicode_content = "Hello 世界! 🌍\nPython is awesome! 🐍\nUnicode test: àáâãäå"
        unicode_file.write_text(unicode_content, encoding='utf-8')
        
        result = file_read_tool.run_impl(file_path=str(unicode_file))
        
        assert isinstance(result, str)
        assert "Hello 世界! 🌍" in result
        assert "Python is awesome! 🐍" in result
        assert "Unicode test: àáâãäå" in result
        
    def test_file_with_only_whitespace(self, file_read_tool, temp_workspace):
        """Test reading file containing only whitespace."""
        whitespace_file = temp_workspace / 'whitespace.txt'
        whitespace_content = "   \n\t\t\n   \n"
        whitespace_file.write_text(whitespace_content)
        
        result = file_read_tool.run_impl(file_path=str(whitespace_file))
        
        assert isinstance(result, str)
        # Should preserve whitespace in output
        assert "\t   " in result or "\t\t\t" in result


class TestFileReadToolLineNumbering:
    """Test line numbering format (cat -n style)."""
    
    def test_line_number_format(self, file_read_tool, sample_files):
        """Test that line numbers follow cat -n format."""
        file_path = str(sample_files['python'])
        result = file_read_tool.run_impl(file_path=file_path, limit=10)
        
        lines = result.split('\n')
        content_lines = [line for line in lines if not line.startswith('[File content')]
        
        # Check that content lines have proper format: "     N\tcontent"
        for i, line in enumerate(content_lines):
            if '\t' in line:
                line_num_part, content_part = line.split('\t', 1)
                line_num = line_num_part.strip()
                try:
                    num = int(line_num)
                    assert num >= 1, f"Line number should be >= 1, got {num}"
                except ValueError:
                    pytest.fail(f"Expected line number, got: '{line_num}'")
                    
    def test_line_numbers_with_offset(self, file_read_tool, sample_files):
        """Test line numbers are correct with offset."""
        file_path = str(sample_files['python'])
        result = file_read_tool.run_impl(file_path=file_path, offset=5, limit=3)
        
        assert "showing lines 5-7" in result
        lines = result.split('\n')
        
        # Find content lines (those with tabs)
        content_lines = [line for line in lines if '\t' in line and not line.startswith('[')]
        
        for line in content_lines:
            line_num_part = line.split('\t')[0].strip()
            try:
                num = int(line_num_part)
                assert 5 <= num <= 7, f"Line number should be between 5-7, got {num}"
            except ValueError:
                pytest.fail(f"Expected line number between 5-7, got: '{line_num_part}'")
