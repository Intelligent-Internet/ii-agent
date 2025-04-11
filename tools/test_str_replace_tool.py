from unittest.mock import MagicMock, patch
from tools.str_replace_tool import StrReplaceEditorTool


def build_ws_manager(root):
    workspace_manager = MagicMock()
    workspace_manager.root = root
    workspace_manager.workspace_path.side_effect = lambda path: path
    workspace_manager.container_path.side_effect = lambda path: path
    return workspace_manager


def test_view_command(tmp_path):
    # Setup
    workspace_manager = build_ws_manager(tmp_path)
    test_file = tmp_path / "test.txt"
    test_file.write_text("line1\nline2\nline3")

    tool = StrReplaceEditorTool(
        workspace_manager=workspace_manager,
        ignore_indentation_for_str_replace=False,
    )

    # Test viewing whole file
    result = tool.run_impl({"command": "view", "path": str(test_file)})
    assert result.success
    assert "line1" in result.tool_output
    assert "line2" in result.tool_output
    assert "line3" in result.tool_output
    assert "Total lines in file: 3" in result.tool_output

    # Test viewing range - should still show total lines in file
    result = tool.run_impl(
        {
            "command": "view",
            "path": str(test_file),
            "view_range": [2, 2],
        }
    )
    assert result.success
    assert "line1" not in result.tool_output
    assert "line2" in result.tool_output
    assert "line3" not in result.tool_output
    assert "Total lines in file: 3" in result.tool_output


def test_view_directory(tmp_path):
    # Setup
    workspace_manager = build_ws_manager(tmp_path)
    test_dir = tmp_path / "test_dir"
    test_dir.mkdir()
    (test_dir / "file1.txt").write_text("content1")
    (test_dir / "file2.txt").write_text("content2")
    (test_dir / "subdir").mkdir()
    (test_dir / "subdir" / "file3.txt").write_text("content3")

    tool = StrReplaceEditorTool(
        workspace_manager=workspace_manager,
        ignore_indentation_for_str_replace=False,
    )

    # Test viewing directory
    result = tool.run_impl({"command": "view", "path": str(test_dir)})
    assert result.success
    assert "file1.txt" in result.tool_output
    assert "file2.txt" in result.tool_output
    assert "subdir" in result.tool_output

    # Test view_range not allowed for directory
    result = tool.run_impl(
        {
            "command": "view",
            "path": str(test_dir),
            "view_range": [1, 2],
        }
    )
    assert not result.success
    assert "not allowed" in result.tool_output


def test_view_invalid_range(tmp_path):
    # Setup
    workspace_manager = build_ws_manager(tmp_path)
    test_file = tmp_path / "test.txt"
    test_file.write_text("line1\nline2\nline3")

    tool = StrReplaceEditorTool(
        workspace_manager=workspace_manager,
        ignore_indentation_for_str_replace=False,
    )

    # Test invalid range formats
    for invalid_range in [[1], [1, 2, 3], [-1, 2], [2, 1], [1, 10]]:
        result = tool.run_impl(
            {
                "command": "view",
                "path": str(test_file),
                "view_range": invalid_range,
            }
        )
        assert not result.success
        assert "Invalid" in result.tool_output


def test_create_command(tmp_path):
    # Setup
    workspace_manager = build_ws_manager(tmp_path)
    test_file = tmp_path / "new.txt"

    tool = StrReplaceEditorTool(
        workspace_manager=workspace_manager,
        ignore_indentation_for_str_replace=False,
    )

    # Test creating new file
    result = tool.run_impl(
        {
            "command": "create",
            "path": str(test_file),
            "file_text": "test content",
        }
    )
    assert result.success
    assert test_file.read_text() == "test content"

    # Test creating existing file fails
    result = tool.run_impl(
        {
            "command": "create",
            "path": str(test_file),
            "file_text": "new content",
        }
    )
    assert not result.success

    # Test missing file_text
    result = tool.run_impl({"command": "create", "path": str(tmp_path / "another.txt")})
    assert not result.success
    assert "file_text" in result.tool_output


@patch("pathlib.Path.write_text")
def test_create_with_error(mock_write, tmp_path):
    mock_write.side_effect = PermissionError("Permission denied")
    tool = StrReplaceEditorTool(
        workspace_manager=build_ws_manager(tmp_path),
        ignore_indentation_for_str_replace=False,
    )
    result = tool.run_impl(
        {"command": "create", "path": "/test.txt", "file_text": "content"}
    )
    assert not result.success


def test_str_replace_command(tmp_path):
    # Setup
    workspace_manager = build_ws_manager(tmp_path)
    test_file = tmp_path / "test.txt"
    test_file.write_text("line1\nline2\nline3")

    tool = StrReplaceEditorTool(
        workspace_manager=workspace_manager,
        ignore_indentation_for_str_replace=False,
    )

    # Test successful replacement - should show total lines in file
    result = tool.run_impl(
        {
            "command": "str_replace",
            "path": str(test_file),
            "old_str": "line2",
            "new_str": "replaced",
        }
    )
    assert result.success
    assert test_file.read_text() == "line1\nreplaced\nline3"
    assert "Total lines in file: 3" in result.tool_output

    # Test replacement with multiline string - should update total lines
    result = tool.run_impl(
        {
            "command": "str_replace",
            "path": str(test_file),
            "old_str": "replaced",
            "new_str": "new\nreplaced\nlines",
        }
    )
    assert result.success
    assert "Total lines in file: 5" in result.tool_output

    # Test non-existent string
    result = tool.run_impl(
        {
            "command": "str_replace",
            "path": str(test_file),
            "old_str": "nonexistent",
            "new_str": "replaced",
        }
    )
    assert not result.success
    assert "did not appear" in result.tool_output

    # Test multiple occurrences
    test_file.write_text("line1\nline2\nline2")
    result = tool.run_impl(
        {
            "command": "str_replace",
            "path": str(test_file),
            "old_str": "line2",
            "new_str": "replaced",
        }
    )
    assert not result.success
    assert "Multiple occurrences" in result.tool_output


def test_str_replace_edge_cases(tmp_path):
    workspace_manager = build_ws_manager(tmp_path)
    test_file = tmp_path / "test.txt"
    test_file.write_text("line1\nline2\nline3")

    tool = StrReplaceEditorTool(
        workspace_manager=workspace_manager,
        ignore_indentation_for_str_replace=False,
    )

    # Test missing parameters
    result = tool.run_impl({"command": "str_replace", "path": str(test_file)})
    assert not result.success
    assert "required" in result.tool_output

    # Test empty new_str
    result = tool.run_impl(
        {
            "command": "str_replace",
            "path": str(test_file),
            "old_str": "line2",
            "new_str": "",
        }
    )
    assert result.success
    assert test_file.read_text() == "line1\n\nline3"

    # Test multiline strings
    result = tool.run_impl(
        {
            "command": "str_replace",
            "path": str(test_file),
            "old_str": "line1\n\n",
            "new_str": "replaced\ntext\n",
        }
    )
    assert result.success


def test_insert_command(tmp_path):
    # Setup
    workspace_manager = build_ws_manager(tmp_path)
    test_file = tmp_path / "test.txt"
    test_file.write_text("line1\nline2\nline3")

    tool = StrReplaceEditorTool(
        workspace_manager=workspace_manager,
        ignore_indentation_for_str_replace=False,
    )

    # Test inserting in middle - should show total lines
    result = tool.run_impl(
        {
            "command": "insert",
            "path": str(test_file),
            "insert_line": 1,
            "new_str": "inserted",
        }
    )
    assert result.success
    assert test_file.read_text() == "line1\ninserted\nline2\nline3"
    assert "Total lines in file: 4" in result.tool_output

    # Test inserting multiline string - should update total lines
    result = tool.run_impl(
        {
            "command": "insert",
            "path": str(test_file),
            "insert_line": 2,
            "new_str": "new\nmultiline\ninsert",
        }
    )
    assert result.success
    assert "Total lines in file: 7" in result.tool_output

    # Test invalid line number
    result = tool.run_impl(
        {
            "command": "insert",
            "path": str(test_file),
            "insert_line": 10,
            "new_str": "inserted",
        }
    )
    assert not result.success
    assert "Invalid" in result.tool_output


def test_insert_edge_cases(tmp_path):
    workspace_manager = build_ws_manager(tmp_path)
    test_file = tmp_path / "test.txt"
    test_file.write_text("line1\nline2\nline3")

    tool = StrReplaceEditorTool(
        workspace_manager=workspace_manager,
        ignore_indentation_for_str_replace=False,
    )

    # Test missing parameters
    result = tool.run_impl({"command": "insert", "path": str(test_file)})
    assert not result.success
    assert "required" in result.tool_output

    # Test insert at beginning
    result = tool.run_impl(
        {
            "command": "insert",
            "path": str(test_file),
            "insert_line": 0,
            "new_str": "first",
        }
    )
    assert result.success
    assert test_file.read_text().startswith("first\n")

    # Test insert at end
    result = tool.run_impl(
        {
            "command": "insert",
            "path": str(test_file),
            "insert_line": 4,
            "new_str": "last",
        }
    )
    assert result.success
    assert test_file.read_text().endswith("last")

    # Test negative line number
    result = tool.run_impl(
        {
            "command": "insert",
            "path": str(test_file),
            "insert_line": -1,
            "new_str": "negative",
        }
    )
    assert not result.success


def test_undo_edit_command(tmp_path):
    # Setup
    workspace_manager = build_ws_manager(tmp_path)
    test_file = tmp_path / "test.txt"
    test_file.write_text("line1\nline2\nline3")

    tool = StrReplaceEditorTool(
        workspace_manager=workspace_manager,
        ignore_indentation_for_str_replace=False,
    )

    # Make an edit that adds lines
    tool.run_impl(
        {
            "command": "str_replace",
            "path": str(test_file),
            "old_str": "line2",
            "new_str": "replaced\nwith\nmultiple\nlines",
        }
    )

    # Test undo - should show correct total lines after reverting
    result = tool.run_impl({"command": "undo_edit", "path": str(test_file)})
    assert result.success
    assert test_file.read_text() == "line1\nline2\nline3"
    assert "Total lines in file: 3" in result.tool_output

    # Test undo with no history
    result = tool.run_impl({"command": "undo_edit", "path": str(test_file)})
    assert not result.success
    assert "No edit history" in result.tool_output


def test_multiple_undo_operations(tmp_path):
    workspace_manager = build_ws_manager(tmp_path)
    test_file = tmp_path / "test.txt"
    test_file.write_text("original")

    tool = StrReplaceEditorTool(
        workspace_manager=workspace_manager,
        ignore_indentation_for_str_replace=False,
    )

    # Make multiple edits
    tool.run_impl(
        {
            "command": "str_replace",
            "path": str(test_file),
            "old_str": "original",
            "new_str": "first",
        }
    )
    tool.run_impl(
        {
            "command": "str_replace",
            "path": str(test_file),
            "old_str": "first",
            "new_str": "second",
        }
    )

    # Test multiple undos
    result = tool.run_impl({"command": "undo_edit", "path": str(test_file)})
    assert result.success
    assert test_file.read_text() == "first"

    result = tool.run_impl({"command": "undo_edit", "path": str(test_file)})
    assert result.success
    assert test_file.read_text() == "original"


def test_invalid_command(tmp_path):
    workspace_manager = build_ws_manager(tmp_path)
    test_file = tmp_path / "test.py"
    test_file.write_text("test")
    tool = StrReplaceEditorTool(
        workspace_manager=workspace_manager,
        ignore_indentation_for_str_replace=False,
    )
    result = tool.run_impl({"command": "invalid", "path": str(test_file)})
    assert not result.success
    assert "Unrecognized command" in result.tool_output


def test_tool_start_message():
    tool = StrReplaceEditorTool(
        workspace_manager=MagicMock(),
        ignore_indentation_for_str_replace=False,
    )
    message = tool.get_tool_start_message({"path": "/test.txt"})
    assert message == "Editing file /test.txt"


def test_str_replace_with_indentation(tmp_path):
    # Setup
    workspace_manager = build_ws_manager(tmp_path)
    test_file = tmp_path / "test_indentation.py"

    # Create a file with indented code
    test_file.write_text(
        """def main():
    if True:
        print("Hello")
        if True:
            print("World")
        print("End")
"""
    )

    tool = StrReplaceEditorTool(
        workspace_manager=workspace_manager,
        ignore_indentation_for_str_replace=True,
    )

    # Test with different indentation in old_str
    # Original indentation is 8 spaces for the inner if block
    result = tool.run_impl(
        {
            "command": "str_replace",
            "path": str(test_file),
            "old_str": """if True:
    print("World")""",
            "new_str": """if True:
    print("Modified World")""",
        }
    )

    assert result.success
    assert "Modified World" in test_file.read_text()


def test_str_replace_with_different_indentation_levels(tmp_path):
    # Setup
    workspace_manager = build_ws_manager(tmp_path)
    test_file = tmp_path / "test_multi_indent.py"

    # Create a file with multiple indentation levels
    test_file.write_text(
        """def function():
    # Level 1
    if condition_1:
        # Level 2
        for item in items:
            # Level 3
            if condition_2:
                # Level 4
                process(item)
            else:
                skip(item)
"""
    )

    tool = StrReplaceEditorTool(
        workspace_manager=workspace_manager,
        ignore_indentation_for_str_replace=True,
    )

    # Test with completely different indentation in old_str
    # but preserving the relative structure
    result = tool.run_impl(
        {
            "command": "str_replace",
            "path": str(test_file),
            "old_str": """if condition_2:
    # Level 4
    process(item)
else:
    skip(item)""",
            "new_str": """if condition_2:
    # Level 4
    process_modified(item)
else:
    skip_modified(item)""",
        }
    )

    assert result.success
    assert "process_modified(item)" in test_file.read_text()
    assert "skip_modified(item)" in test_file.read_text()


def test_str_replace_with_mixed_indentation(tmp_path):
    # Setup
    workspace_manager = build_ws_manager(tmp_path)
    test_file = tmp_path / "test_mixed_indent.py"

    # Create a file with mixed tabs and spaces
    test_file.write_text(
        """def mixed_indentation():
    # 4 spaces
    if condition:
        # 8 spaces
        value = compute()

        # Still 8 spaces
        if value > threshold:
            # 12 spaces
            return value
"""
    )

    tool = StrReplaceEditorTool(
        workspace_manager=workspace_manager,
        ignore_indentation_for_str_replace=True,
    )

    # Test with no indentation in old_str
    result = tool.run_impl(
        {
            "command": "str_replace",
            "path": str(test_file),
            "old_str": """if value > threshold:
    # 12 spaces
    return value""",
            "new_str": """if value > threshold:
    # Modified comment
    return processed_value""",
        }
    )

    assert result.success
    assert "Modified comment" in test_file.read_text()
    assert "processed_value" in test_file.read_text()


def test_str_replace_indentation_edge_cases(tmp_path):
    # Setup
    workspace_manager = build_ws_manager(tmp_path)
    test_file = tmp_path / "test_indent_edge.py"

    # Create a file with some edge cases
    test_file.write_text(
        """def edge_cases():
    # Empty lines between code

    if condition:

        print("Has empty line before")

    # Inconsistent indentation
    if another_condition:
      print("Two spaces")
        print("Four spaces")
          print("Six spaces")
"""
    )

    tool = StrReplaceEditorTool(
        workspace_manager=workspace_manager,
        ignore_indentation_for_str_replace=True,
    )

    # Test with empty lines in the pattern
    result = tool.run_impl(
        {
            "command": "str_replace",
            "path": str(test_file),
            "old_str": """if condition:

    print("Has empty line before")""",
            "new_str": """if condition:
    print("No empty line anymore")""",
        }
    )

    assert result.success
    assert "No empty line anymore" in test_file.read_text()

    # Test with inconsistent indentation
    result = tool.run_impl(
        {
            "command": "str_replace",
            "path": str(test_file),
            "old_str": """if another_condition:
  print("Two spaces")
    print("Four spaces")
      print("Six spaces")""",
            "new_str": """if another_condition:
    print("All four spaces now")
    print("Consistent indentation")""",
        }
    )

    assert result.success
    assert "All four spaces now" in test_file.read_text()
    assert "Consistent indentation" in test_file.read_text()


def test_str_replace_no_match_after_indentation_attempts(tmp_path):
    # Setup
    workspace_manager = build_ws_manager(tmp_path)
    test_file = tmp_path / "test_no_match.py"

    test_file.write_text(
        """def no_match():
    print("This is some code")
    if condition:
        print("More code")
"""
    )

    tool = StrReplaceEditorTool(
        workspace_manager=workspace_manager,
        ignore_indentation_for_str_replace=True,
    )

    # Test with a string that won't match even with indentation adjustment
    result = tool.run_impl(
        {
            "command": "str_replace",
            "path": str(test_file),
            "old_str": """if different_condition:
    print("This doesn't exist")""",
            "new_str": """if different_condition:
    print("Won't be replaced")""",
        }
    )

    assert not result.success
    assert "did not appear" in result.tool_output
    # The error message doesn't mention indentation since that's an implementation detail


def test_str_replace_empty_old_str(tmp_path):
    workspace_manager = build_ws_manager(tmp_path)
    test_file = tmp_path / "test.txt"

    tool = StrReplaceEditorTool(
        workspace_manager=workspace_manager,
        ignore_indentation_for_str_replace=False,
    )

    # Test empty old_str with empty file
    test_file.write_text("")
    result = tool.run_impl(
        {
            "command": "str_replace",
            "path": str(test_file),
            "old_str": "",
            "new_str": "new content",
        }
    )
    assert result.success
    assert test_file.read_text() == "new content"

    # Test empty old_str with non-empty file
    test_file.write_text("existing content")
    result = tool.run_impl(
        {
            "command": "str_replace",
            "path": str(test_file),
            "old_str": "",
            "new_str": "new content",
        }
    )
    assert not result.success
    assert "only allowed when the file is empty" in result.tool_output

    # Test empty old_str with None new_str
    test_file.write_text("")
    result = tool.run_impl(
        {
            "command": "str_replace",
            "path": str(test_file),
            "old_str": "",
            "new_str": None,
        }
    )
    assert result.success
    assert test_file.read_text() == ""
