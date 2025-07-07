"""Comprehensive tests for MultiEditTool."""

import pytest
import tempfile
import os
import shutil
from pathlib import Path
from unittest.mock import Mock, patch

# Add src to path for imports
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from tools.file_system.multi_edit_tool import MultiEditTool
from core.workspace import WorkspaceManager


class TestMultiEditTool:
    """Test class for MultiEditTool functionality."""

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
    def multi_edit_tool(self, workspace_manager):
        """Create a MultiEditTool instance."""
        return MultiEditTool(workspace_manager)

    def test_tool_initialization(self, multi_edit_tool):
        """Test that the tool initializes correctly."""
        assert multi_edit_tool.name == "MultiEdit"
        assert "multiple edits to a single file" in multi_edit_tool.description
        assert multi_edit_tool.file_edit_tool is not None

    def test_create_new_file_single_edit(self, multi_edit_tool, temp_workspace):
        """Test creating a new file with a single edit."""
        test_file = temp_workspace / "new_file.txt"
        content = "Hello, World!\nThis is a new file."
        
        edits = [
            {
                "old_string": "",
                "new_string": content
            }
        ]
        
        result = multi_edit_tool.run_impl(
            file_path=str(test_file),
            edits=edits
        )
        
        assert "SUCCESS: Created new file" in result
        assert test_file.exists()
        assert test_file.read_text() == content

    def test_create_new_file_multiple_edits(self, multi_edit_tool, temp_workspace):
        """Test creating a new file and then applying additional edits."""
        test_file = temp_workspace / "new_file.txt"
        initial_content = "Hello World!\nThis is a test."
        
        edits = [
            {
                "old_string": "",
                "new_string": initial_content
            },
            {
                "old_string": "Hello World!",
                "new_string": "Hello Python!"
            },
            {
                "old_string": "test",
                "new_string": "demo"
            }
        ]
        
        result = multi_edit_tool.run_impl(
            file_path=str(test_file),
            edits=edits
        )
        
        assert "SUCCESS: Created new file" in result
        assert "applied 2 additional edit(s)" in result
        assert test_file.exists()
        
        final_content = test_file.read_text()
        assert "Hello Python!" in final_content
        assert "This is a demo." in final_content
        assert "Hello World!" not in final_content

    def test_multiple_edits_existing_file(self, multi_edit_tool, temp_workspace):
        """Test applying multiple edits to an existing file."""
        test_file = temp_workspace / "existing_file.txt"
        original_content = "def old_function():\n    return 'old'\n\nclass OldClass:\n    pass\n\n# TODO: old comment"
        test_file.write_text(original_content)
        
        edits = [
            {
                "old_string": "old_function",
                "new_string": "new_function"
            },
            {
                "old_string": "return 'old'",
                "new_string": "return 'new'"
            },
            {
                "old_string": "OldClass",
                "new_string": "NewClass"
            },
            {
                "old_string": "# TODO: old comment",
                "new_string": "# DONE: new comment"
            }
        ]
        
        result = multi_edit_tool.run_impl(
            file_path=str(test_file),
            edits=edits
        )
        
        assert "SUCCESS: Modified file" in result
        assert "applied 4 edit(s)" in result
        assert "4 total replacement(s)" in result
        
        final_content = test_file.read_text()
        assert "def new_function():" in final_content
        assert "return 'new'" in final_content
        assert "class NewClass:" in final_content
        assert "# DONE: new comment" in final_content

    def test_sequential_dependent_edits(self, multi_edit_tool, temp_workspace):
        """Test edits where later edits depend on earlier ones."""
        test_file = temp_workspace / "sequential.txt"
        original_content = "var old_name = 'value';\nfunction old_name() { }\nconsole.log(old_name);"
        test_file.write_text(original_content)
        
        edits = [
            {
                "old_string": "old_name",
                "new_string": "new_name",
                "replace_all": True
            },
            {
                "old_string": "new_name = 'value'",
                "new_string": "new_name = 'updated_value'"
            }
        ]
        
        result = multi_edit_tool.run_impl(
            file_path=str(test_file),
            edits=edits
        )
        
        assert "SUCCESS: Modified file" in result
        final_content = test_file.read_text()
        assert "var new_name = 'updated_value'" in final_content
        assert "function new_name()" in final_content
        assert "console.log(new_name)" in final_content
        assert "old_name" not in final_content

    def test_multiline_edits(self, multi_edit_tool, temp_workspace):
        """Test multiple edits involving multiline content."""
        test_file = temp_workspace / "multiline.txt"
        original_content = """def function1():
    print("first")
    return 1

def function2():
    print("second")
    return 2

def function3():
    print("third")
    return 3"""
        test_file.write_text(original_content)
        
        edits = [
            {
                "old_string": """def function1():
    print("first")
    return 1""",
                "new_string": """def enhanced_function1():
    print("enhanced first")
    return 10"""
            },
            {
                "old_string": "print(\"second\")",
                "new_string": "print(\"modified second\")"
            }
        ]
        
        result = multi_edit_tool.run_impl(
            file_path=str(test_file),
            edits=edits
        )
        
        assert "SUCCESS: Modified file" in result
        final_content = test_file.read_text()
        assert "def enhanced_function1():" in final_content
        assert "enhanced first" in final_content
        assert "return 10" in final_content
        assert "modified second" in final_content
        assert "def function3():" in final_content  # Unchanged

    def test_replace_all_in_multiple_edits(self, multi_edit_tool, temp_workspace):
        """Test using replace_all in multiple edits."""
        test_file = temp_workspace / "replace_all.txt"
        original_content = "test test test\nAnother test line\ntest again test"
        test_file.write_text(original_content)
        
        edits = [
            {
                "old_string": "test",
                "new_string": "demo",
                "replace_all": True
            },
            {
                "old_string": "demo again demo",
                "new_string": "demo final demo"
            }
        ]
        
        result = multi_edit_tool.run_impl(
            file_path=str(test_file),
            edits=edits
        )
        
        assert "SUCCESS: Modified file" in result
        final_content = test_file.read_text()
        assert final_content == "demo demo demo\nAnother demo line\ndemo final demo"

    def test_empty_edits_list_error(self, multi_edit_tool, temp_workspace):
        """Test error when no edits are provided."""
        test_file = temp_workspace / "test.txt"
        
        result = multi_edit_tool.run_impl(
            file_path=str(test_file),
            edits=[]
        )
        
        assert "ERROR: No edits provided" in result

    def test_invalid_edit_structure_error(self, multi_edit_tool, temp_workspace):
        """Test error when edit structure is invalid."""
        test_file = temp_workspace / "test.txt"
        
        # Test non-dictionary edit
        edits = ["invalid_edit"]
        result = multi_edit_tool.run_impl(
            file_path=str(test_file),
            edits=edits
        )
        assert "ERROR: Edit 1 must be a dictionary" in result
        
        # Test missing required fields
        edits = [{"old_string": "test"}]  # Missing new_string
        result = multi_edit_tool.run_impl(
            file_path=str(test_file),
            edits=edits
        )
        assert "ERROR: Edit 1 must contain 'old_string' and 'new_string' fields" in result

    def test_same_old_new_string_error(self, multi_edit_tool, temp_workspace):
        """Test error when old_string equals new_string in any edit."""
        test_file = temp_workspace / "test.txt"
        test_file.write_text("Hello World!")
        
        edits = [
            {
                "old_string": "Hello",
                "new_string": "Hi"
            },
            {
                "old_string": "same",
                "new_string": "same"  # Error here
            }
        ]
        
        result = multi_edit_tool.run_impl(
            file_path=str(test_file),
            edits=edits
        )
        
        assert "ERROR: Edit 2: old_string and new_string cannot be the same" in result

    def test_file_not_found_error(self, multi_edit_tool, temp_workspace):
        """Test error when file doesn't exist and first edit has non-empty old_string."""
        test_file = temp_workspace / "nonexistent.txt"
        
        edits = [
            {
                "old_string": "something",
                "new_string": "replacement"
            }
        ]
        
        result = multi_edit_tool.run_impl(
            file_path=str(test_file),
            edits=edits
        )
        
        assert "ERROR:" in result
        assert "does not exist" in result
        assert "empty old_string in the first edit" in result

    def test_string_not_found_error(self, multi_edit_tool, temp_workspace):
        """Test error when old_string is not found in any edit."""
        test_file = temp_workspace / "test.txt"
        test_file.write_text("Hello World!")
        
        edits = [
            {
                "old_string": "Hello",
                "new_string": "Hi"
            },
            {
                "old_string": "nonexistent",
                "new_string": "replacement"
            }
        ]
        
        result = multi_edit_tool.run_impl(
            file_path=str(test_file),
            edits=edits
        )
        
        assert "ERROR: Edit 2:" in result
        assert "String to replace not found" in result

    def test_multiple_occurrences_error(self, multi_edit_tool, temp_workspace):
        """Test error when multiple occurrences exist without replace_all."""
        test_file = temp_workspace / "test.txt"
        test_file.write_text("test test test")
        
        edits = [
            {
                "old_string": "test",
                "new_string": "demo",
                "replace_all": False
            }
        ]
        
        result = multi_edit_tool.run_impl(
            file_path=str(test_file),
            edits=edits
        )
        
        assert "ERROR: Edit 1:" in result
        assert "3 occurrences" in result

    def test_empty_old_string_subsequent_edit_error(self, multi_edit_tool, temp_workspace):
        """Test error when empty old_string is used in subsequent edits after file creation."""
        test_file = temp_workspace / "new_file.txt"
        
        edits = [
            {
                "old_string": "",
                "new_string": "Initial content"
            },
            {
                "old_string": "",  # Error: empty old_string in subsequent edit
                "new_string": "More content"
            }
        ]
        
        result = multi_edit_tool.run_impl(
            file_path=str(test_file),
            edits=edits
        )
        
        assert "ERROR: Edit 2: old_string cannot be empty for subsequent edits" in result

    def test_invalid_file_path_error(self, multi_edit_tool):
        """Test error with invalid file path."""
        edits = [
            {
                "old_string": "",
                "new_string": "content"
            }
        ]
        
        result = multi_edit_tool.run_impl(
            file_path="",
            edits=edits
        )
        
        assert "ERROR: File path cannot be empty" in result

    def test_workspace_boundary_validation(self, temp_workspace):
        """Test that files outside workspace boundary are rejected."""
        workspace_manager = WorkspaceManager(str(temp_workspace))
        multi_edit_tool = MultiEditTool(workspace_manager)
        
        edits = [
            {
                "old_string": "",
                "new_string": "content"
            }
        ]
        
        # Try to edit a file outside the workspace
        outside_file = "/tmp/outside_workspace.txt"
        result = multi_edit_tool.run_impl(
            file_path=outside_file,
            edits=edits
        )
        
        assert "ERROR:" in result
        assert "not within workspace boundary" in result

    def test_permission_error_simulation(self, multi_edit_tool, temp_workspace):
        """Test handling of permission errors."""
        test_file = temp_workspace / "test.txt"
        
        edits = [
            {
                "old_string": "",
                "new_string": "content"
            }
        ]
        
        # Mock file operations to simulate permission error
        with patch('pathlib.Path.write_text', side_effect=PermissionError("Permission denied")):
            result = multi_edit_tool.run_impl(
                file_path=str(test_file),
                edits=edits
            )
            
            assert "ERROR: Permission denied writing to file" in result

    def test_unicode_content_multiple_edits(self, multi_edit_tool, temp_workspace):
        """Test handling of unicode content in multiple edits."""
        test_file = temp_workspace / "unicode.txt"
        
        edits = [
            {
                "old_string": "",
                "new_string": "Hello 世界! 🌟"
            },
            {
                "old_string": "世界",
                "new_string": "Python"
            },
            {
                "old_string": "🌟",
                "new_string": "⭐"
            }
        ]
        
        result = multi_edit_tool.run_impl(
            file_path=str(test_file),
            edits=edits
        )
        
        assert "SUCCESS: Created new file" in result
        final_content = test_file.read_text(encoding='utf-8')
        assert "Hello Python! ⭐" == final_content

    def test_large_number_of_edits(self, multi_edit_tool, temp_workspace):
        """Test handling of a large number of edits."""
        test_file = temp_workspace / "large_edits.txt"
        initial_content = "\n".join([f"exact_line_{i:03d}_unique" for i in range(100)])
        test_file.write_text(initial_content)
        
        # Create edits to change every line
        edits = []
        for i in range(100):
            edits.append({
                "old_string": f"exact_line_{i:03d}_unique",
                "new_string": f"modified_line_{i:03d}_unique"
            })
        
        result = multi_edit_tool.run_impl(
            file_path=str(test_file),
            edits=edits
        )
        
        assert "SUCCESS: Modified file" in result
        assert "applied 100 edit(s)" in result
        
        final_content = test_file.read_text()
        for i in range(100):
            assert f"modified_line_{i:03d}_unique" in final_content
            assert f"exact_line_{i:03d}_unique" not in final_content

    def test_atomic_behavior_on_error(self, multi_edit_tool, temp_workspace):
        """Test that no changes are made if any edit fails (atomic behavior)."""
        test_file = temp_workspace / "atomic_test.txt"
        original_content = "Hello World!\nThis is a test."
        test_file.write_text(original_content)
        
        edits = [
            {
                "old_string": "Hello",
                "new_string": "Hi"
            },
            {
                "old_string": "nonexistent_string",  # This will fail
                "new_string": "replacement"
            }
        ]
        
        result = multi_edit_tool.run_impl(
            file_path=str(test_file),
            edits=edits
        )
        
        assert "ERROR: Edit 2:" in result
        
        # File should remain unchanged
        final_content = test_file.read_text()
        assert final_content == original_content
        assert "Hello World!" in final_content  # Not changed to "Hi"

    def test_whitespace_preservation_multiple_edits(self, multi_edit_tool, temp_workspace):
        """Test that whitespace is preserved correctly across multiple edits."""
        test_file = temp_workspace / "whitespace.txt"
        original_content = "    def function():\n        return 'old'\n\n\tclass MyClass:\n\t    pass"
        test_file.write_text(original_content)
        
        edits = [
            {
                "old_string": "def function():",
                "new_string": "def new_function():"
            },
            {
                "old_string": "return 'old'",
                "new_string": "return 'new'"
            },
            {
                "old_string": "MyClass",
                "new_string": "NewClass"
            }
        ]
        
        result = multi_edit_tool.run_impl(
            file_path=str(test_file),
            edits=edits
        )
        
        assert "SUCCESS: Modified file" in result
        final_content = test_file.read_text()
        
        # Check that indentation is preserved
        assert "    def new_function():" in final_content
        assert "        return 'new'" in final_content
        assert "\tclass NewClass:" in final_content
        assert "\t    pass" in final_content


class TestMultiEditToolIntegration:
    """Integration tests for MultiEditTool."""

    @pytest.fixture
    def real_workspace(self):
        """Create a realistic workspace structure for integration testing."""
        temp_dir = tempfile.mkdtemp()
        workspace = Path(temp_dir)
        
        # Create a realistic project structure
        (workspace / "src").mkdir()
        (workspace / "tests").mkdir()
        (workspace / "docs").mkdir()
        
        # Create sample files
        (workspace / "src" / "main.py").write_text("""#!/usr/bin/env python3
\"\"\"Main application module.\"\"\"

def main():
    print("Hello, World!")
    return 0

if __name__ == "__main__":
    main()
""")
        
        (workspace / "src" / "utils.py").write_text("""\"\"\"Utility functions.\"\"\"

def helper_function(x):
    return x * 2

class HelperClass:
    def __init__(self):
        self.value = 0
""")
        
        yield workspace
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_realistic_code_refactoring(self, real_workspace):
        """Test realistic code refactoring scenario."""
        workspace_manager = WorkspaceManager(str(real_workspace))
        multi_edit_tool = MultiEditTool(workspace_manager)
        
        main_file = real_workspace / "src" / "main.py"
        
        # Refactor main.py: change function name, docstring, and print message
        edits = [
            {
                "old_string": "def main():",
                "new_string": "def run_application():"
            },
            {
                "old_string": "\"\"\"Main application module.\"\"\"",
                "new_string": "\"\"\"Application entry point module.\"\"\""
            },
            {
                "old_string": "print(\"Hello, World!\")",
                "new_string": "print(\"Welcome to the application!\")"
            },
            {
                "old_string": "if __name__ == \"__main__\":\n    main()",
                "new_string": "if __name__ == \"__main__\":\n    run_application()"
            }
        ]
        
        result = multi_edit_tool.run_impl(
            file_path=str(main_file),
            edits=edits
        )
        
        assert "SUCCESS: Modified file" in result
        final_content = main_file.read_text()
        assert "def run_application():" in final_content
        assert "Application entry point module" in final_content
        assert "Welcome to the application!" in final_content
        assert "run_application()" in final_content

    def test_cross_file_consistent_renaming_simulation(self, real_workspace):
        """Test scenario simulating consistent renaming across multiple operations."""
        workspace_manager = WorkspaceManager(str(real_workspace))
        multi_edit_tool = MultiEditTool(workspace_manager)
        
        utils_file = real_workspace / "src" / "utils.py"
        
        # Rename class and method consistently
        edits = [
            {
                "old_string": "class HelperClass:",
                "new_string": "class UtilityClass:"
            },
            {
                "old_string": "def helper_function(x):",
                "new_string": "def utility_function(x):"
            },
            {
                "old_string": "\"\"\"Utility functions.\"\"\"",
                "new_string": "\"\"\"Utility functions and classes.\"\"\""
            }
        ]
        
        result = multi_edit_tool.run_impl(
            file_path=str(utils_file),
            edits=edits
        )
        
        assert "SUCCESS: Modified file" in result
        final_content = utils_file.read_text()
        assert "class UtilityClass:" in final_content
        assert "def utility_function(x):" in final_content
        assert "Utility functions and classes" in final_content 