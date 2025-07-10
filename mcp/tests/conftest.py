import pytest
import tempfile
import json
import yaml
import base64
from pathlib import Path

from src.core.workspace import WorkspaceManager
from src.tools.file_system.file_read_tool import FileReadTool
from src.tools.file_system.file_edit_tool import FileEditTool  
from src.tools.file_system.file_write_tool import FileWriteTool


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace directory for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture  
def workspace_manager(temp_workspace):
    """Create a WorkspaceManager instance for testing."""
    return WorkspaceManager(str(temp_workspace))


@pytest.fixture
def file_read_tool(workspace_manager):
    """Create a FileReadTool instance for testing."""
    return FileReadTool(workspace_manager)


@pytest.fixture
def file_edit_tool(workspace_manager):
    """Create a FileEditTool instance for testing."""
    return FileEditTool(workspace_manager)


@pytest.fixture
def file_write_tool(workspace_manager):
    """Create a FileWriteTool instance for testing."""
    return FileWriteTool(workspace_manager)


@pytest.fixture
def sample_files(temp_workspace):
    """Create various sample files for testing."""
    files = {}
    
    # Python file
    python_content = '''#!/usr/bin/env python3
"""Sample Python module for testing."""

import os
import sys
from pathlib import Path


class SampleClass:
    """A sample class for testing."""
    
    def __init__(self, name: str):
        self.name = name
        self.counter = 0
    
    def increment(self) -> int:
        """Increment the counter and return new value."""
        self.counter += 1
        return self.counter
    
    def get_info(self) -> dict:
        """Return information about this instance."""
        return {
            "name": self.name,
            "counter": self.counter,
            "type": "SampleClass"
        }


def main():
    """Main function for testing."""
    sample = SampleClass("test")
    for i in range(5):
        print(f"Count: {sample.increment()}")
    
    print(f"Final info: {sample.get_info()}")


if __name__ == "__main__":
    main()
'''
    files['python'] = temp_workspace / 'sample.py'
    files['python'].write_text(python_content)
    
    # JSON config file
    json_content = {
        "app_name": "test_application",
        "version": "1.0.0",
        "debug": True,
        "database": {
            "host": "localhost",
            "port": 5432,
            "name": "test_db",
            "credentials": {
                "username": "test_user",
                "password": "secret123"
            }
        },
        "features": [
            "authentication",
            "logging", 
            "caching",
            "monitoring"
        ],
        "limits": {
            "max_connections": 100,
            "timeout": 30.0,
            "retry_attempts": 3
        }
    }
    files['json'] = temp_workspace / 'config.json'
    files['json'].write_text(json.dumps(json_content, indent=2))
    
    # YAML config file
    yaml_content = {
        'server': {
            'host': '0.0.0.0',
            'port': 8080,
            'workers': 4
        },
        'logging': {
            'level': 'INFO',
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            'handlers': ['console', 'file']
        },
        'cache': {
            'type': 'redis',
            'url': 'redis://localhost:6379/0',
            'ttl': 3600
        }
    }
    files['yaml'] = temp_workspace / 'config.yaml'
    files['yaml'].write_text(yaml.dump(yaml_content, default_flow_style=False))
    
    # Large text file for testing limits
    large_content = []
    for i in range(2500):  # Exceeds MAX_FILE_READ_LINES (2000)
        large_content.append(f"Line {i + 1}: This is a test line with some content to make it realistic.")
    files['large'] = temp_workspace / 'large.txt'
    files['large'].write_text('\n'.join(large_content))
    
    # File with very long lines
    long_lines = []
    for i in range(10):
        long_line = f"Line {i + 1}: " + "x" * 2500  # Exceeds MAX_LINE_LENGTH (2000)
        long_lines.append(long_line)
    files['long_lines'] = temp_workspace / 'long_lines.txt'
    files['long_lines'].write_text('\n'.join(long_lines))
    
    # Empty file
    files['empty'] = temp_workspace / 'empty.txt'
    files['empty'].write_text('')
    
    # Small image file (PNG) - create a minimal valid PNG
    # This is a minimal 1x1 red PNG file in bytes
    png_data = base64.b64decode(
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=='
    )
    files['image'] = temp_workspace / 'test_image.png'
    files['image'].write_bytes(png_data)
    
    # Binary file (simulated)
    binary_content = b'\x00\x01\x02\x03\x04\x05\xFF\xFE\xFD'
    files['binary'] = temp_workspace / 'binary.bin'
    files['binary'].write_bytes(binary_content)
    
    # Markdown file
    markdown_content = '''# Test Markdown File

This is a sample markdown file for testing purposes.

## Features

- **Bold text**
- *Italic text*
- `Code spans`
- [Links](https://example.com)

## Code Block

```python
def hello_world():
    print("Hello, World!")
```

## Lists

1. First item
2. Second item
   - Nested item
   - Another nested item
3. Third item

> This is a blockquote
> with multiple lines

---

End of document.
'''
    files['markdown'] = temp_workspace / 'README.md'
    files['markdown'].write_text(markdown_content)
    
    # JavaScript file
    js_content = '''/**
 * Sample JavaScript file for testing
 */

const config = {
    apiUrl: 'https://api.example.com',
    timeout: 5000,
    retries: 3
};

class ApiClient {
    constructor(baseUrl, options = {}) {
        this.baseUrl = baseUrl;
        this.timeout = options.timeout || 5000;
        this.retries = options.retries || 3;
    }
    
    async get(endpoint) {
        const url = `${this.baseUrl}/${endpoint}`;
        try {
            const response = await fetch(url, {
                method: 'GET',
                timeout: this.timeout
            });
            return await response.json();
        } catch (error) {
            console.error('API request failed:', error);
            throw error;
        }
    }
    
    async post(endpoint, data) {
        const url = `${this.baseUrl}/${endpoint}`;
        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(data),
                timeout: this.timeout
            });
            return await response.json();
        } catch (error) {
            console.error('API request failed:', error);
            throw error;
        }
    }
}

// Export for use
module.exports = { ApiClient, config };
'''
    files['javascript'] = temp_workspace / 'api_client.js'
    files['javascript'].write_text(js_content)
    
    return files


@pytest.fixture
def nested_files(temp_workspace):
    """Create nested directory structure with files."""
    # Create nested directories
    (temp_workspace / 'src' / 'components').mkdir(parents=True)
    (temp_workspace / 'tests' / 'unit').mkdir(parents=True)
    (temp_workspace / 'docs').mkdir(parents=True)
    
    files = {}
    
    # Component file
    component_content = '''import React from 'react';

interface ButtonProps {
    label: string;
    onClick: () => void;
    disabled?: boolean;
}

const Button: React.FC<ButtonProps> = ({ label, onClick, disabled = false }) => {
    return (
        <button 
            onClick={onClick} 
            disabled={disabled}
            className="btn btn-primary"
        >
            {label}
        </button>
    );
};

export default Button;
'''
    files['component'] = temp_workspace / 'src' / 'components' / 'Button.tsx'
    files['component'].write_text(component_content)
    
    # Test file
    test_content = '''import { render, screen, fireEvent } from '@testing-library/react';
import Button from '../../src/components/Button';

describe('Button Component', () => {
    test('renders with correct label', () => {
        render(<Button label="Click me" onClick={() => {}} />);
        expect(screen.getByText('Click me')).toBeInTheDocument();
    });
    
    test('calls onClick when clicked', () => {
        const mockClick = jest.fn();
        render(<Button label="Click me" onClick={mockClick} />);
        
        fireEvent.click(screen.getByText('Click me'));
        expect(mockClick).toHaveBeenCalledTimes(1);
    });
    
    test('is disabled when disabled prop is true', () => {
        render(<Button label="Click me" onClick={() => {}} disabled={true} />);
        expect(screen.getByText('Click me')).toBeDisabled();
    });
});
'''
    files['test'] = temp_workspace / 'tests' / 'unit' / 'Button.test.tsx'
    files['test'].write_text(test_content)
    
    return files