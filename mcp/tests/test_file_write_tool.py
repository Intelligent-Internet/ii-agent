"""Comprehensive tests for FileWriteTool."""

import pytest
import json
import yaml
from pathlib import Path


class TestFileWriteToolBasic:
    """Test basic file writing functionality."""

    def test_write_new_text_file(self, file_write_tool, temp_workspace):
        """Test writing content to a new text file."""
        file_path = str(temp_workspace / 'new_file.txt')
        content = "This is a test file.\nWith multiple lines.\nFor testing purposes."
        
        result = file_write_tool.run_impl(file_path=file_path, content=content)
        
        assert "Successfully created and wrote to new file:" in result
        assert file_path in result
        
        # Verify file was actually created with correct content
        created_file = Path(file_path)
        assert created_file.exists()
        assert created_file.read_text() == content

    def test_overwrite_existing_file(self, file_write_tool, sample_files):
        """Test overwriting an existing file."""
        file_path = str(sample_files['python'])
        new_content = "#!/usr/bin/env python3\n# This file has been overwritten\nprint('Hello, World!')"
        
        result = file_write_tool.run_impl(file_path=file_path, content=new_content)
        
        assert "Successfully overwrote file:" in result
        assert file_path in result
        
        # Verify file content was updated
        updated_file = Path(file_path)
        assert updated_file.read_text() == new_content

    def test_write_python_file(self, file_write_tool, temp_workspace):
        """Test writing a Python file."""
        file_path = str(temp_workspace / 'test_script.py')
        content = '''#!/usr/bin/env python3
"""Test Python script."""

def hello_world():
    """Print hello world."""
    print("Hello, World!")

if __name__ == "__main__":
    hello_world()
'''
        
        result = file_write_tool.run_impl(file_path=file_path, content=content)
        
        assert "Successfully created and wrote to new file:" in result
        created_file = Path(file_path)
        assert created_file.exists()
        assert created_file.read_text() == content

    def test_write_json_file(self, file_write_tool, temp_workspace):
        """Test writing a JSON configuration file."""
        file_path = str(temp_workspace / 'config.json')
        config_data = {
            "app_name": "test_app",
            "version": "2.0.0",
            "settings": {
                "debug": False,
                "timeout": 30
            }
        }
        content = json.dumps(config_data, indent=2)
        
        result = file_write_tool.run_impl(file_path=file_path, content=content)
        
        assert "Successfully created and wrote to new file:" in result
        created_file = Path(file_path)
        assert created_file.exists()
        
        # Verify JSON is valid and matches expected content
        loaded_data = json.loads(created_file.read_text())
        assert loaded_data == config_data

    def test_write_yaml_file(self, file_write_tool, temp_workspace):
        """Test writing a YAML configuration file."""
        file_path = str(temp_workspace / 'config.yaml')
        config_data = {
            'application': {
                'name': 'test_app',
                'version': '1.0.0'
            },
            'database': {
                'host': 'localhost',
                'port': 5432
            }
        }
        content = yaml.dump(config_data, default_flow_style=False)
        
        result = file_write_tool.run_impl(file_path=file_path, content=content)
        
        assert "Successfully created and wrote to new file:" in result
        created_file = Path(file_path)
        assert created_file.exists()
        
        # Verify YAML is valid and matches expected content
        loaded_data = yaml.safe_load(created_file.read_text())
        assert loaded_data == config_data


class TestFileWriteToolNestedDirectories:
    """Test writing files in nested directory structures."""

    def test_write_file_with_parent_directory_creation(self, file_write_tool, temp_workspace):
        """Test writing file that requires parent directory creation."""
        file_path = str(temp_workspace / 'deep' / 'nested' / 'structure' / 'file.txt')
        content = "File in deeply nested directory"
        
        result = file_write_tool.run_impl(file_path=file_path, content=content)
        
        assert "Successfully created and wrote to new file:" in result
        created_file = Path(file_path)
        assert created_file.exists()
        assert created_file.read_text() == content
        
        # Verify parent directories were created
        assert created_file.parent.exists()
        assert created_file.parent.is_dir()

    def test_write_component_file(self, file_write_tool, temp_workspace):
        """Test writing a React component file in src/components structure."""
        components_dir = temp_workspace / 'src' / 'components'
        file_path = str(components_dir / 'NewComponent.tsx')
        content = '''import React from 'react';

interface NewComponentProps {
    title: string;
    description?: string;
}

const NewComponent: React.FC<NewComponentProps> = ({ title, description }) => {
    return (
        <div className="new-component">
            <h2>{title}</h2>
            {description && <p>{description}</p>}
        </div>
    );
};

export default NewComponent;
'''
        
        result = file_write_tool.run_impl(file_path=file_path, content=content)
        
        assert "Successfully created and wrote to new file:" in result
        created_file = Path(file_path)
        assert created_file.exists()
        assert created_file.read_text() == content


class TestFileWriteToolErrors:
    """Test error conditions."""

    def test_relative_path_error(self, file_write_tool):
        """Test writing with relative path should fail."""
        relative_path = 'relative/path/file.txt'
        content = "This should fail"
        
        result = file_write_tool.run_impl(file_path=relative_path, content=content)
        
        assert "Error: File path must be absolute:" in result
        assert relative_path in result

    def test_outside_workspace_boundary(self, file_write_tool):
        """Test writing file outside workspace boundary should fail."""
        outside_path = '/tmp/outside_workspace.txt'
        content = "This should fail"
        
        result = file_write_tool.run_impl(file_path=outside_path, content=content)
        
        assert "Error: File path must be within the workspace directory" in result

    def test_write_to_directory_path(self, file_write_tool, temp_workspace):
        """Test attempting to write to a directory path should fail."""
        directory_path = str(temp_workspace)
        content = "This should fail"
        
        result = file_write_tool.run_impl(file_path=directory_path, content=content)
        
        assert "Error: Path is a directory, not a file:" in result
        assert directory_path in result

    def test_write_to_existing_directory(self, file_write_tool, temp_workspace):
        """Test attempting to write to path that exists as directory should fail."""
        # Create a directory first
        dir_path = temp_workspace / 'existing_dir'
        dir_path.mkdir()
        
        content = "This should fail"
        result = file_write_tool.run_impl(file_path=str(dir_path), content=content)
        
        assert "Error: Path is a directory, not a file:" in result


class TestFileWriteToolEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_write_empty_file(self, file_write_tool, temp_workspace):
        """Test writing empty content to a file."""
        file_path = str(temp_workspace / 'empty.txt')
        content = ""
        
        result = file_write_tool.run_impl(file_path=file_path, content=content)
        
        assert "Successfully created and wrote to new file:" in result
        created_file = Path(file_path)
        assert created_file.exists()
        assert created_file.read_text() == ""

    def test_write_large_content(self, file_write_tool, temp_workspace):
        """Test writing large content to a file."""
        file_path = str(temp_workspace / 'large_file.txt')
        
        # Create content with 5000 lines
        lines = [f"Line {i + 1}: This is a test line with content." for i in range(5000)]
        content = '\n'.join(lines)
        
        result = file_write_tool.run_impl(file_path=file_path, content=content)
        
        assert "Successfully created and wrote to new file:" in result
        created_file = Path(file_path)
        assert created_file.exists()
        assert created_file.read_text() == content

    def test_write_unicode_content(self, file_write_tool, temp_workspace):
        """Test writing file with Unicode characters."""
        file_path = str(temp_workspace / 'unicode.txt')
        content = "Hello 世界! 🌍\nPython is awesome! 🐍\nUnicode test: àáâãäå"
        
        result = file_write_tool.run_impl(file_path=file_path, content=content)
        
        assert "Successfully created and wrote to new file:" in result
        created_file = Path(file_path)
        assert created_file.exists()
        assert created_file.read_text(encoding='utf-8') == content

    def test_write_special_characters(self, file_write_tool, temp_workspace):
        """Test writing file with special characters and symbols."""
        file_path = str(temp_workspace / 'special_chars.txt')
        content = '''Special characters test:
"Quotes" and 'apostrophes'
Symbols: @#$%^&*()
Backslashes: \\ and forward slashes: /
Tab\tcharacter and newline\ncharacter
'''
        
        result = file_write_tool.run_impl(file_path=file_path, content=content)
        
        assert "Successfully created and wrote to new file:" in result
        created_file = Path(file_path)
        assert created_file.exists()
        assert created_file.read_text() == content

    def test_write_whitespace_only_content(self, file_write_tool, temp_workspace):
        """Test writing file with only whitespace content."""
        file_path = str(temp_workspace / 'whitespace.txt')
        content = "   \n\t\t\n   \n"
        
        result = file_write_tool.run_impl(file_path=file_path, content=content)
        
        assert "Successfully created and wrote to new file:" in result
        created_file = Path(file_path)
        assert created_file.exists()
        assert created_file.read_text() == content

    def test_overwrite_with_different_content_type(self, file_write_tool, sample_files):
        """Test overwriting a JSON file with Python content."""
        file_path = str(sample_files['json'])
        python_content = '''#!/usr/bin/env python3
"""Python script that replaced JSON file."""

def main():
    print("JSON file has been replaced with Python code")

if __name__ == "__main__":
    main()
'''
        
        result = file_write_tool.run_impl(file_path=file_path, content=python_content)
        
        assert "Successfully overwrote file:" in result
        updated_file = Path(file_path)
        assert updated_file.read_text() == python_content


class TestFileWriteToolExtensions:
    """Test writing files with various extensions."""

    def test_write_markdown_file(self, file_write_tool, temp_workspace):
        """Test writing a Markdown file."""
        file_path = str(temp_workspace / 'README.md')
        content = '''# Test Project

This is a test project created for testing purposes.

## Features

- Feature 1
- Feature 2
- Feature 3

## Installation

```bash
pip install test-project
```

## Usage

```python
import test_project
test_project.run()
```
'''
        
        result = file_write_tool.run_impl(file_path=file_path, content=content)
        
        assert "Successfully created and wrote to new file:" in result
        created_file = Path(file_path)
        assert created_file.exists()
        assert created_file.read_text() == content

    def test_write_css_file(self, file_write_tool, temp_workspace):
        """Test writing a CSS file."""
        file_path = str(temp_workspace / 'styles.css')
        content = '''.container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 20px;
}

.header {
    background-color: #333;
    color: white;
    padding: 1rem;
}

.button {
    background-color: #007bff;
    color: white;
    border: none;
    padding: 10px 20px;
    border-radius: 4px;
    cursor: pointer;
}

.button:hover {
    background-color: #0056b3;
}
'''
        
        result = file_write_tool.run_impl(file_path=file_path, content=content)
        
        assert "Successfully created and wrote to new file:" in result
        created_file = Path(file_path)
        assert created_file.exists()
        assert created_file.read_text() == content

    def test_write_html_file(self, file_write_tool, temp_workspace):
        """Test writing an HTML file."""
        file_path = str(temp_workspace / 'index.html')
        content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Test Page</title>
</head>
<body>
    <header>
        <h1>Welcome to Test Page</h1>
    </header>
    <main>
        <p>This is a test HTML file.</p>
        <button onclick="alert('Hello!')">Click me</button>
    </main>
</body>
</html>
'''
        
        result = file_write_tool.run_impl(file_path=file_path, content=content)
        
        assert "Successfully created and wrote to new file:" in result
        created_file = Path(file_path)
        assert created_file.exists()
        assert created_file.read_text() == content


class TestFileWriteToolConsistency:
    """Test consistency between write and read operations."""

    def test_write_then_read_consistency(self, file_write_tool, file_read_tool, temp_workspace):
        """Test that written content can be read back consistently."""
        file_path = str(temp_workspace / 'consistency_test.txt')
        original_content = '''This is a consistency test.
Line 2 with special chars: àáâãäå
Line 3 with symbols: @#$%^&*()
Line 4 with quotes: "double" and 'single'
Line 5 with unicode: 世界 🌍
'''
        
        # Write the file
        write_result = file_write_tool.run_impl(file_path=file_path, content=original_content)
        assert "Successfully created and wrote to new file:" in write_result
        
        # Read the file back
        read_result = file_read_tool.run_impl(file_path=file_path)
        
        # Verify content consistency
        # Note: file_read_tool adds line numbers, so we need to extract the content
        assert isinstance(read_result, str)
        assert "This is a consistency test." in read_result
        assert "àáâãäå" in read_result
        assert "@#$%^&*()" in read_result
        assert "世界 🌍" in read_result

    def test_multiple_write_operations(self, file_write_tool, temp_workspace):
        """Test multiple write operations to the same file."""
        file_path = str(temp_workspace / 'multiple_writes.txt')
        
        # First write
        content1 = "First content"
        result1 = file_write_tool.run_impl(file_path=file_path, content=content1)
        assert "Successfully created and wrote to new file:" in result1
        
        # Second write (overwrite)
        content2 = "Second content that overwrites the first"
        result2 = file_write_tool.run_impl(file_path=file_path, content=content2)
        assert "Successfully overwrote file:" in result2
        
        # Third write (overwrite again)
        content3 = "Third and final content"
        result3 = file_write_tool.run_impl(file_path=file_path, content=content3)
        assert "Successfully overwrote file:" in result3
        
        # Verify final content
        final_file = Path(file_path)
        assert final_file.read_text() == content3
