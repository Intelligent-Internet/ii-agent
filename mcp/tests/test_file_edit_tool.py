"""Comprehensive tests for FileEditTool."""

import pytest
import json
import yaml
from pathlib import Path


class TestFileEditToolBasic:
    """Test basic file editing functionality."""

    def test_simple_string_replacement(self, file_edit_tool, sample_files):
        """Test simple string replacement in an existing file."""
        file_path = str(sample_files['python'])
        old_string = 'print(f"Count: {sample.increment()}")'
        new_string = 'print(f"Counter value: {sample.increment()}")'
        
        result = file_edit_tool.run_impl(
            file_path=file_path,
            old_string=old_string,
            new_string=new_string,
            replace_all=False
        )
        
        assert "has been updated" in result
        assert "Counter value:" in Path(file_path).read_text()

    def test_multi_line_replacement(self, file_edit_tool, sample_files):
        """Test replacing multiple lines of content."""
        file_path = str(sample_files['python'])
        old_string = '''def get_info(self) -> dict:
        """Return information about this instance."""
        return {
            "name": self.name,
            "counter": self.counter,
            "type": "SampleClass"
        }'''
        new_string = '''def get_info(self) -> dict:
        """Return detailed information about this instance."""
        return {
            "name": self.name,
            "counter": self.counter,
            "type": "SampleClass",
            "status": "active"
        }'''
        
        result = file_edit_tool.run_impl(
            file_path=file_path,
            old_string=old_string,
            new_string=new_string,
            replace_all=False
        )
        
        assert "has been updated" in result
        content = Path(file_path).read_text()
        assert "detailed information" in content
        assert '"status": "active"' in content

    def test_replace_all_occurrences(self, file_edit_tool, sample_files):
        """Test replacing all occurrences of a string."""
        file_path = str(sample_files['python'])
        old_string = "SampleClass"  # This appears multiple times but not in comments
        new_string = "TestClass"
        
        result = file_edit_tool.run_impl(
            file_path=file_path,
            old_string=old_string,
            new_string=new_string,
            replace_all=True
        )
        
        assert "has been updated" in result
        content = Path(file_path).read_text()
        # Should replace all occurrences
        assert "TestClass" in content

    def test_create_new_file(self, file_edit_tool, temp_workspace):
        """Test creating a new file with empty old_string."""
        file_path = str(temp_workspace / 'new_test_file.py')
        content = '''#!/usr/bin/env python3
"""New test file created by FileEditTool."""

def hello():
    print("Hello from new file!")

if __name__ == "__main__":
    hello()
'''
        
        result = file_edit_tool.run_impl(
            file_path=file_path,
            old_string="",
            new_string=content,
            replace_all=False
        )
        
        assert "Created new file" in result
        created_file = Path(file_path)
        assert created_file.exists()
        assert created_file.read_text() == content

    def test_edit_json_file(self, file_edit_tool, sample_files):
        """Test editing a JSON configuration file."""
        file_path = str(sample_files['json'])
        old_string = '"debug": true'
        new_string = '"debug": false'
        
        result = file_edit_tool.run_impl(
            file_path=file_path,
            old_string=old_string,
            new_string=new_string,
            replace_all=False
        )
        
        assert "has been updated" in result
        
        # Verify JSON is still valid and change was made
        content = json.loads(Path(file_path).read_text())
        assert content["debug"] is False

    def test_edit_yaml_file(self, file_edit_tool, sample_files):
        """Test editing a YAML configuration file."""
        file_path = str(sample_files['yaml'])
        old_string = 'level: INFO'
        new_string = 'level: DEBUG'
        
        result = file_edit_tool.run_impl(
            file_path=file_path,
            old_string=old_string,
            new_string=new_string,
            replace_all=False
        )
        
        assert "has been updated" in result
        
        # Verify YAML is still valid and change was made
        content = yaml.safe_load(Path(file_path).read_text())
        assert content['logging']['level'] == 'DEBUG'


class TestFileEditToolErrors:
    """Test error conditions and edge cases."""

    def test_nonexistent_file_with_content(self, file_edit_tool, temp_workspace):
        """Test editing non-existent file with non-empty old_string should fail."""
        file_path = str(temp_workspace / 'nonexistent.txt')
        
        result = file_edit_tool.run_impl(
            file_path=file_path,
            old_string="some content",
            new_string="new content",
            replace_all=False
        )
        
        assert "ERROR:" in result
        assert "does not exist" in result
        assert "empty old_string" in result

    def test_string_not_found(self, file_edit_tool, sample_files):
        """Test replacing string that doesn't exist in file."""
        file_path = str(sample_files['python'])
        
        result = file_edit_tool.run_impl(
            file_path=file_path,
            old_string="this string does not exist in the file",
            new_string="replacement",
            replace_all=False
        )
        
        assert "ERROR:" in result
        assert "String to replace not found" in result

    def test_multiple_occurrences_without_replace_all(self, file_edit_tool, sample_files):
        """Test replacing string with multiple occurrences without replace_all flag."""
        file_path = str(sample_files['python'])
        
        result = file_edit_tool.run_impl(
            file_path=file_path,
            old_string="def",  # This appears multiple times
            new_string="function",
            replace_all=False
        )
        
        assert "ERROR:" in result
        assert "Found" in result and "occurrences" in result
        assert "replace_all=True" in result

    def test_same_old_and_new_string(self, file_edit_tool, sample_files):
        """Test using same string for old_string and new_string."""
        file_path = str(sample_files['python'])
        same_string = "SampleClass"
        
        result = file_edit_tool.run_impl(
            file_path=file_path,
            old_string=same_string,
            new_string=same_string,
            replace_all=False
        )
        
        assert "ERROR:" in result
        assert "cannot be the same" in result

    def test_empty_old_string_for_existing_file(self, file_edit_tool, sample_files):
        """Test using empty old_string for existing file should fail."""
        file_path = str(sample_files['python'])
        
        result = file_edit_tool.run_impl(
            file_path=file_path,
            old_string="",
            new_string="some content",
            replace_all=False
        )
        
        assert "ERROR:" in result
        assert "Cannot use empty old_string for existing file" in result

    def test_outside_workspace_boundary(self, file_edit_tool):
        """Test editing file outside workspace boundary should fail."""
        outside_path = '/tmp/outside_workspace.txt'
        
        result = file_edit_tool.run_impl(
            file_path=outside_path,
            old_string="old",
            new_string="new",
            replace_all=False
        )
        
        assert "ERROR:" in result
        assert "not within workspace boundary" in result

    def test_invalid_file_path(self, file_edit_tool):
        """Test using invalid file path."""
        invalid_path = "not\x00valid"
        
        result = file_edit_tool.run_impl(
            file_path=invalid_path,
            old_string="old",
            new_string="new",
            replace_all=False
        )
        
        assert "ERROR:" in result

    def test_edit_directory_path(self, file_edit_tool, temp_workspace):
        """Test attempting to edit a directory path should fail."""
        directory_path = str(temp_workspace)
        
        result = file_edit_tool.run_impl(
            file_path=directory_path,
            old_string="old",
            new_string="new",
            replace_all=False
        )
        
        assert "ERROR:" in result
        assert "is not a file" in result


class TestFileEditToolEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_edit_empty_file(self, file_edit_tool, sample_files):
        """Test editing an empty file."""
        file_path = str(sample_files['empty'])
        
        result = file_edit_tool.run_impl(
            file_path=file_path,
            old_string="",
            new_string="Now the file has content!",
            replace_all=False
        )
        
        assert "ERROR:" in result  # Should fail because file exists but old_string is empty

    def test_replace_with_empty_string(self, file_edit_tool, sample_files):
        """Test replacing content with empty string (deletion)."""
        file_path = str(sample_files['python'])
        old_string = '''
class SampleClass:
    """A sample class for testing."""'''
        new_string = ""
        
        result = file_edit_tool.run_impl(
            file_path=file_path,
            old_string=old_string,
            new_string=new_string,
            replace_all=False
        )
        
        assert "has been updated" in result
        content = Path(file_path).read_text()
        assert "class SampleClass:" not in content

    def test_unicode_content_replacement(self, file_edit_tool, temp_workspace):
        """Test replacing content with Unicode characters."""
        # First create a file with Unicode content
        file_path = str(temp_workspace / 'unicode_test.txt')
        initial_content = "Hello 世界! This is a test."
        Path(file_path).write_text(initial_content)
        
        result = file_edit_tool.run_impl(
            file_path=file_path,
            old_string="Hello 世界!",
            new_string="Hola mundo! 🌍",
            replace_all=False
        )
        
        assert "has been updated" in result
        content = Path(file_path).read_text()
        assert "Hola mundo! 🌍" in content

    def test_whitespace_sensitive_replacement(self, file_edit_tool, sample_files):
        """Test replacement that is sensitive to whitespace."""
        file_path = str(sample_files['python'])
        old_string = '    def __init__(self, name: str):'
        new_string = '    def __init__(self, name: str, age: int = 0):'
        
        result = file_edit_tool.run_impl(
            file_path=file_path,
            old_string=old_string,
            new_string=new_string,
            replace_all=False
        )
        
        assert "has been updated" in result
        content = Path(file_path).read_text()
        assert "age: int = 0" in content

    def test_newline_replacement(self, file_edit_tool, sample_files):
        """Test replacing content that spans multiple lines with different line structure."""
        file_path = str(sample_files['python'])
        old_string = '''for i in range(5):
        print(f"Count: {sample.increment()}")'''
        new_string = '''for i in range(10):
        value = sample.increment()
        print(f"Count: {value}")'''
        
        result = file_edit_tool.run_impl(
            file_path=file_path,
            old_string=old_string,
            new_string=new_string,
            replace_all=False
        )
        
        assert "has been updated" in result
        content = Path(file_path).read_text()
        assert "range(10)" in content
        assert "value = sample.increment()" in content

    def test_special_characters_replacement(self, file_edit_tool, temp_workspace):
        """Test replacing content with special characters."""
        file_path = str(temp_workspace / 'special_chars.py')
        initial_content = '''regex = r"\\d+"
pattern = "test"'''
        Path(file_path).write_text(initial_content)
        
        result = file_edit_tool.run_impl(
            file_path=file_path,
            old_string='regex = r"\\d+"',
            new_string='regex = r"\\w+\\s*\\d*"',
            replace_all=False
        )
        
        assert "has been updated" in result
        content = Path(file_path).read_text()
        assert r'regex = r"\w+\s*\d*"' in content


class TestFileEditToolConsistency:
    """Test consistency and integration with other tools."""

    def test_edit_then_read_consistency(self, file_edit_tool, file_read_tool, sample_files):
        """Test that edited content can be read back consistently."""
        file_path = str(sample_files['python'])
        old_string = 'self.name = name'
        new_string = 'self.name = name\n        self.id = "unique"'
        
        # Make the edit
        edit_result = file_edit_tool.run_impl(
            file_path=file_path,
            old_string=old_string,
            new_string=new_string,
            replace_all=False
        )
        assert "has been updated" in edit_result
        
        # Read the file back
        read_result = file_read_tool.run_impl(file_path=file_path)
        
        # Verify the change is reflected
        assert 'self.id = "unique"' in read_result

    def test_multiple_sequential_edits(self, file_edit_tool, sample_files):
        """Test multiple sequential edits to the same file."""
        file_path = str(sample_files['python'])
        
        # First edit - use more specific context to make it unique
        result1 = file_edit_tool.run_impl(
            file_path=file_path,
            old_string="class SampleClass:",
            new_string="class TestClass:",
            replace_all=False
        )
        assert "has been updated" in result1
        
        # Second edit
        result2 = file_edit_tool.run_impl(
            file_path=file_path,
            old_string="class TestClass:",
            new_string="class MyClass:",
            replace_all=False
        )
        assert "has been updated" in result2
        
        # Third edit - replace all counters
        result3 = file_edit_tool.run_impl(
            file_path=file_path,
            old_string="counter",
            new_string="count",
            replace_all=True
        )
        assert "has been updated" in result3
        
        # Verify changes
        content = Path(file_path).read_text()
        assert "MyClass" in content
        assert "self.count" in content

    def test_create_file_then_edit(self, file_edit_tool, temp_workspace):
        """Test creating a file and then editing it."""
        file_path = str(temp_workspace / 'create_then_edit.py')
        initial_content = '''def greet(name):
    print(f"Hello, {name}!")
'''
        
        # Create the file
        create_result = file_edit_tool.run_impl(
            file_path=file_path,
            old_string="",
            new_string=initial_content,
            replace_all=False
        )
        assert "Created new file" in create_result
        
        # Edit the file
        edit_result = file_edit_tool.run_impl(
            file_path=file_path,
            old_string='print(f"Hello, {name}!")',
            new_string='print(f"Greetings, {name}! Welcome!")',
            replace_all=False
        )
        assert "has been updated" in edit_result
        
        # Verify final content
        content = Path(file_path).read_text()
        assert "Greetings" in content
        assert "Welcome" in content


class TestFileEditToolFileTypes:
    """Test editing different file types."""

    def test_edit_markdown_file(self, file_edit_tool, sample_files):
        """Test editing a Markdown file."""
        file_path = str(sample_files['markdown'])
        old_string = "# Test Markdown File"
        new_string = "# Updated Test Markdown File"
        
        result = file_edit_tool.run_impl(
            file_path=file_path,
            old_string=old_string,
            new_string=new_string,
            replace_all=False
        )
        
        assert "has been updated" in result
        content = Path(file_path).read_text()
        assert "# Updated Test Markdown File" in content

    def test_edit_javascript_file(self, file_edit_tool, sample_files):
        """Test editing a JavaScript file."""
        file_path = str(sample_files['javascript'])
        old_string = "timeout: 5000,"  # More specific string
        new_string = "timeout: 10000,"
        
        result = file_edit_tool.run_impl(
            file_path=file_path,
            old_string=old_string,
            new_string=new_string,
            replace_all=False  # Only replace first occurrence
        )
        
        assert "has been updated" in result
        content = Path(file_path).read_text()
        assert "timeout: 10000," in content

    def test_edit_nested_component_file(self, file_edit_tool, nested_files):
        """Test editing a nested React component file."""
        file_path = str(nested_files['component'])
        old_string = 'className="btn btn-primary"'
        new_string = 'className="btn btn-secondary"'
        
        result = file_edit_tool.run_impl(
            file_path=file_path,
            old_string=old_string,
            new_string=new_string,
            replace_all=False
        )
        
        assert "has been updated" in result
        content = Path(file_path).read_text()
        assert "btn-secondary" in content
        assert "btn-primary" not in content


class TestFileEditToolSnippetDisplay:
    """Test the snippet display functionality."""

    def test_snippet_shows_context(self, file_edit_tool, sample_files):
        """Test that the result shows a snippet with context around the edit."""
        file_path = str(sample_files['python'])
        old_string = "self.counter = 0"
        new_string = "self.counter = 0\n        self.created_at = 'now'"
        
        result = file_edit_tool.run_impl(
            file_path=file_path,
            old_string=old_string,
            new_string=new_string,
            replace_all=False
        )
        
        assert "has been updated" in result
        assert "cat -n" in result
        # Should show line numbers and surrounding context
        assert "\t" in result  # Tab separator in cat -n format
        assert "created_at" in result

    def test_snippet_format_with_line_numbers(self, file_edit_tool, sample_files):
        """Test that snippet shows proper line number formatting."""
        file_path = str(sample_files['python'])
        old_string = "import sys"
        new_string = "import sys\nimport datetime"
        
        result = file_edit_tool.run_impl(
            file_path=file_path,
            old_string=old_string,
            new_string=new_string,
            replace_all=False
        )
        
        assert "has been updated" in result
        # Should show line numbers in proper format (6 spaces + tab)
        lines = result.split('\n')
        snippet_lines = [line for line in lines if '\t' in line and any(char.isdigit() for char in line)]
        assert len(snippet_lines) > 0
        
        # Check line number format
        for line in snippet_lines:
            parts = line.split('\t', 1)
            assert len(parts) == 2
            line_num_part = parts[0].strip()
            assert line_num_part.isdigit()
