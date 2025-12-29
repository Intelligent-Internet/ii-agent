"""Unit tests for ii_tool.tools.file_system.file_edit_tool module."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

from ii_tool.tools.file_system.file_edit_tool import (
    FileEditTool,
    FileEditToolError,
    _perform_replacement,
    NAME,
    DISPLAY_NAME,
    DESCRIPTION,
    INPUT_SCHEMA,
)
from ii_tool.tools.base import ToolResult, ToolConfirmationDetails, FileEditToolResultContent
from ii_tool.core.workspace import WorkspaceManager, FileSystemValidationError


# =============================================================================
# Test Constants and Schema
# =============================================================================

class TestModuleConstants:
    """Tests for module-level constants."""

    def test_name_constant(self):
        """Test NAME constant value."""
        assert NAME == "Edit"

    def test_display_name_constant(self):
        """Test DISPLAY_NAME constant value."""
        assert DISPLAY_NAME == "Edit file"

    def test_description_not_empty(self):
        """Test DESCRIPTION is not empty."""
        assert DESCRIPTION
        assert len(DESCRIPTION) > 50

    def test_description_contains_key_info(self):
        """Test DESCRIPTION contains important information."""
        desc_lower = DESCRIPTION.lower()
        assert "replace" in desc_lower
        assert "read" in desc_lower

    def test_input_schema_structure(self):
        """Test INPUT_SCHEMA has required structure."""
        assert INPUT_SCHEMA["type"] == "object"
        assert "properties" in INPUT_SCHEMA
        assert "required" in INPUT_SCHEMA

    def test_input_schema_properties(self):
        """Test INPUT_SCHEMA has correct properties."""
        props = INPUT_SCHEMA["properties"]
        assert "file_path" in props
        assert "old_string" in props
        assert "new_string" in props
        assert "replace_all" in props

    def test_input_schema_required_fields(self):
        """Test INPUT_SCHEMA has correct required fields."""
        assert set(INPUT_SCHEMA["required"]) == {"file_path", "old_string", "new_string"}

    def test_replace_all_is_optional(self):
        """Test replace_all is not required."""
        assert "replace_all" not in INPUT_SCHEMA["required"]

    def test_replace_all_schema(self):
        """Test replace_all property schema."""
        replace_all_schema = INPUT_SCHEMA["properties"]["replace_all"]
        assert replace_all_schema["type"] == "boolean"


# =============================================================================
# Test FileEditToolError Exception
# =============================================================================

class TestFileEditToolError:
    """Tests for FileEditToolError exception class."""

    def test_is_exception_subclass(self):
        """Test FileEditToolError is an Exception."""
        assert issubclass(FileEditToolError, Exception)

    def test_can_be_raised(self):
        """Test FileEditToolError can be raised."""
        with pytest.raises(FileEditToolError):
            raise FileEditToolError("test error")

    def test_error_message(self):
        """Test FileEditToolError preserves message."""
        try:
            raise FileEditToolError("specific error message")
        except FileEditToolError as e:
            assert str(e) == "specific error message"


# =============================================================================
# Test _perform_replacement Function
# =============================================================================

class TestPerformReplacement:
    """Tests for the _perform_replacement helper function."""

    def test_single_replacement_success(self):
        """Test successful single replacement."""
        content = "Hello World"
        new_content, occurrences = _perform_replacement(content, "World", "Universe", False)
        
        assert new_content == "Hello Universe"
        assert occurrences == 1

    def test_replace_all_success(self):
        """Test successful replace_all."""
        content = "foo bar foo baz foo"
        new_content, occurrences = _perform_replacement(content, "foo", "qux", True)
        
        assert new_content == "qux bar qux baz qux"
        assert occurrences == 3

    def test_string_not_found_raises_error(self):
        """Test error when string not found."""
        content = "Hello World"
        
        with pytest.raises(FileEditToolError) as exc_info:
            _perform_replacement(content, "xyz", "abc", False)
        
        assert "not found" in str(exc_info.value).lower()

    def test_multiple_occurrences_without_replace_all_raises_error(self):
        """Test error when multiple occurrences without replace_all."""
        content = "foo bar foo"
        
        with pytest.raises(FileEditToolError) as exc_info:
            _perform_replacement(content, "foo", "baz", False)
        
        assert "2 occurrences" in str(exc_info.value)
        assert "unique" in str(exc_info.value).lower() or "replace_all" in str(exc_info.value)

    def test_single_occurrence_without_replace_all(self):
        """Test single occurrence works without replace_all."""
        content = "unique string here"
        new_content, occurrences = _perform_replacement(content, "unique", "UNIQUE", False)
        
        assert new_content == "UNIQUE string here"
        assert occurrences == 1

    def test_empty_replacement(self):
        """Test replacing with empty string (deletion)."""
        content = "Hello World"
        new_content, occurrences = _perform_replacement(content, " World", "", False)
        
        assert new_content == "Hello"
        assert occurrences == 1

    def test_multiline_replacement(self):
        """Test replacement in multiline content."""
        content = """def foo():
    pass

def bar():
    pass"""
        
        new_content, occurrences = _perform_replacement(
            content,
            "def foo():\n    pass",
            "def foo():\n    return 42",
            False
        )
        
        assert "return 42" in new_content
        assert occurrences == 1

    def test_whitespace_sensitive(self):
        """Test that replacement is whitespace-sensitive."""
        content = "  indented\n    more indented"
        
        # Should not find without correct whitespace
        with pytest.raises(FileEditToolError):
            _perform_replacement(content, "indented", "new", False)
        
        # Should find with correct whitespace
        new_content, _ = _perform_replacement(content, "  indented", "  NEW", False)
        assert "  NEW" in new_content

    def test_special_characters_in_string(self):
        """Test replacement with special regex characters."""
        content = "price: $100.00"
        new_content, occurrences = _perform_replacement(content, "$100.00", "$200.00", False)
        
        assert new_content == "price: $200.00"
        assert occurrences == 1

    def test_replace_all_with_single_occurrence(self):
        """Test replace_all still works with single occurrence."""
        content = "one item"
        new_content, occurrences = _perform_replacement(content, "item", "thing", True)
        
        assert new_content == "one thing"
        assert occurrences == 1


# =============================================================================
# Test FileEditTool Class
# =============================================================================

class TestFileEditToolAttributes:
    """Tests for FileEditTool class attributes."""

    def test_class_name_attribute(self):
        """Test class name attribute matches constant."""
        assert FileEditTool.name == NAME

    def test_class_display_name_attribute(self):
        """Test class display_name attribute."""
        assert FileEditTool.display_name == DISPLAY_NAME

    def test_class_description_attribute(self):
        """Test class description attribute."""
        assert FileEditTool.description == DESCRIPTION

    def test_class_input_schema_attribute(self):
        """Test class input_schema attribute."""
        assert FileEditTool.input_schema == INPUT_SCHEMA

    def test_class_read_only_attribute(self):
        """Test class read_only is False (editing modifies files)."""
        assert FileEditTool.read_only is False


class TestFileEditToolInit:
    """Tests for FileEditTool initialization."""

    def test_init_with_workspace_manager(self):
        """Test initialization stores workspace_manager."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        tool = FileEditTool(workspace_manager=mock_wm)
        assert tool.workspace_manager is mock_wm


class TestFileEditToolShouldConfirmExecute:
    """Tests for should_confirm_execute method."""

    def test_returns_confirmation_details(self):
        """Test method returns ToolConfirmationDetails."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        tool = FileEditTool(workspace_manager=mock_wm)
        
        tool_input = {
            "file_path": "/workspace/test.py",
            "old_string": "old code",
            "new_string": "new code"
        }
        
        result = tool.should_confirm_execute(tool_input)
        
        assert isinstance(result, ToolConfirmationDetails)

    def test_confirmation_type_is_edit(self):
        """Test confirmation type is 'edit'."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        tool = FileEditTool(workspace_manager=mock_wm)
        
        tool_input = {
            "file_path": "/workspace/test.py",
            "old_string": "old",
            "new_string": "new"
        }
        
        result = tool.should_confirm_execute(tool_input)
        
        assert result.type == "edit"

    def test_confirmation_message_contains_file_path(self):
        """Test confirmation message contains file path."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        tool = FileEditTool(workspace_manager=mock_wm)
        
        tool_input = {
            "file_path": "/workspace/myfile.py",
            "old_string": "old",
            "new_string": "new"
        }
        
        result = tool.should_confirm_execute(tool_input)
        
        assert "/workspace/myfile.py" in result.message

    def test_confirmation_message_contains_old_and_new_strings(self):
        """Test confirmation message contains old and new strings."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        tool = FileEditTool(workspace_manager=mock_wm)
        
        tool_input = {
            "file_path": "/workspace/test.py",
            "old_string": "THE_OLD_CODE",
            "new_string": "THE_NEW_CODE"
        }
        
        result = tool.should_confirm_execute(tool_input)
        
        assert "THE_OLD_CODE" in result.message
        assert "THE_NEW_CODE" in result.message


# =============================================================================
# Test FileEditTool.execute() Method - Validation
# =============================================================================

class TestFileEditToolExecuteValidation:
    """Tests for execute method input validation."""

    @pytest.mark.asyncio
    async def test_same_old_new_string_error(self):
        """Test error when old_string equals new_string."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        tool = FileEditTool(workspace_manager=mock_wm)
        
        tool_input = {
            "file_path": "/workspace/test.py",
            "old_string": "same value",
            "new_string": "same value"
        }
        
        result = await tool.execute(tool_input)
        
        assert result.is_error is True
        assert "cannot be the same" in result.llm_content

    @pytest.mark.asyncio
    async def test_path_validation_called(self):
        """Test that workspace path validation is called."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        tool = FileEditTool(workspace_manager=mock_wm)
        
        tool_input = {
            "file_path": "/workspace/test.py",
            "old_string": "old",
            "new_string": "new"
        }
        
        with patch.object(Path, 'resolve') as mock_resolve:
            mock_path = MagicMock()
            mock_resolve.return_value = mock_path
            mock_path.read_text.return_value = "content with old string"
            
            await tool.execute(tool_input)
        
        mock_wm.validate_existing_file_path.assert_called_once_with("/workspace/test.py")

    @pytest.mark.asyncio
    async def test_validation_error_returns_error_result(self):
        """Test that validation error returns error ToolResult."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        mock_wm.validate_existing_file_path.side_effect = FileSystemValidationError("File not found")
        tool = FileEditTool(workspace_manager=mock_wm)
        
        tool_input = {
            "file_path": "/nonexistent/file.py",
            "old_string": "old",
            "new_string": "new"
        }
        
        result = await tool.execute(tool_input)
        
        assert result.is_error is True
        assert "File not found" in result.llm_content


# =============================================================================
# Test FileEditTool.execute() Method - Replacement
# =============================================================================

class TestFileEditToolExecuteReplacement:
    """Tests for execute method replacement functionality."""

    @pytest.mark.asyncio
    async def test_successful_single_replacement(self):
        """Test successful single replacement."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        tool = FileEditTool(workspace_manager=mock_wm)
        
        tool_input = {
            "file_path": "/workspace/test.py",
            "old_string": "old_value",
            "new_string": "new_value"
        }
        
        with patch.object(Path, 'resolve') as mock_resolve:
            mock_path = MagicMock()
            mock_resolve.return_value = mock_path
            mock_path.read_text.return_value = "code with old_value here"
            mock_path.__str__ = MagicMock(return_value="/workspace/test.py")
            
            result = await tool.execute(tool_input)
        
        assert result.is_error is False
        assert "1 replacement" in result.llm_content
        mock_path.write_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_successful_replace_all(self):
        """Test successful replace_all."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        tool = FileEditTool(workspace_manager=mock_wm)
        
        tool_input = {
            "file_path": "/workspace/test.py",
            "old_string": "foo",
            "new_string": "bar",
            "replace_all": True
        }
        
        with patch.object(Path, 'resolve') as mock_resolve:
            mock_path = MagicMock()
            mock_resolve.return_value = mock_path
            mock_path.read_text.return_value = "foo and foo and foo"
            mock_path.__str__ = MagicMock(return_value="/workspace/test.py")
            
            result = await tool.execute(tool_input)
        
        assert result.is_error is False
        assert "3 replacement" in result.llm_content

    @pytest.mark.asyncio
    async def test_writes_correct_content(self):
        """Test that correct content is written to file."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        tool = FileEditTool(workspace_manager=mock_wm)
        
        tool_input = {
            "file_path": "/workspace/test.py",
            "old_string": "REPLACE_ME",
            "new_string": "REPLACED"
        }
        
        with patch.object(Path, 'resolve') as mock_resolve:
            mock_path = MagicMock()
            mock_resolve.return_value = mock_path
            mock_path.read_text.return_value = "prefix REPLACE_ME suffix"
            
            await tool.execute(tool_input)
            
            written_content = mock_path.write_text.call_args[0][0]
            assert written_content == "prefix REPLACED suffix"

    @pytest.mark.asyncio
    async def test_string_not_found_error(self):
        """Test error when string not found in file."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        tool = FileEditTool(workspace_manager=mock_wm)
        
        tool_input = {
            "file_path": "/workspace/test.py",
            "old_string": "nonexistent",
            "new_string": "replacement"
        }
        
        with patch.object(Path, 'resolve') as mock_resolve:
            mock_path = MagicMock()
            mock_resolve.return_value = mock_path
            mock_path.read_text.return_value = "content without the target"
            
            result = await tool.execute(tool_input)
        
        assert result.is_error is True
        assert "not found" in result.llm_content.lower()

    @pytest.mark.asyncio
    async def test_multiple_occurrences_without_replace_all_error(self):
        """Test error when multiple occurrences without replace_all."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        tool = FileEditTool(workspace_manager=mock_wm)
        
        tool_input = {
            "file_path": "/workspace/test.py",
            "old_string": "duplicate",
            "new_string": "unique"
        }
        
        with patch.object(Path, 'resolve') as mock_resolve:
            mock_path = MagicMock()
            mock_resolve.return_value = mock_path
            mock_path.read_text.return_value = "duplicate here and duplicate there"
            
            result = await tool.execute(tool_input)
        
        assert result.is_error is True
        assert "2 occurrences" in result.llm_content


# =============================================================================
# Test FileEditTool.execute() Method - Result Content
# =============================================================================

class TestFileEditToolExecuteResultContent:
    """Tests for execute method result content."""

    @pytest.mark.asyncio
    async def test_result_contains_file_edit_content(self):
        """Test successful result contains FileEditToolResultContent."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        tool = FileEditTool(workspace_manager=mock_wm)
        
        tool_input = {
            "file_path": "/workspace/test.py",
            "old_string": "old",
            "new_string": "new"
        }
        
        with patch.object(Path, 'resolve') as mock_resolve:
            mock_path = MagicMock()
            mock_resolve.return_value = mock_path
            mock_path.read_text.return_value = "old content"
            mock_path.__str__ = MagicMock(return_value="/workspace/test.py")
            
            result = await tool.execute(tool_input)
        
        assert result.is_error is False
        # user_display_content should be a list containing the model dump
        assert isinstance(result.user_display_content, list)
        assert len(result.user_display_content) == 1

    @pytest.mark.asyncio
    async def test_result_llm_content_message(self):
        """Test success message in llm_content."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        tool = FileEditTool(workspace_manager=mock_wm)
        
        tool_input = {
            "file_path": "/workspace/test.py",
            "old_string": "old",
            "new_string": "new"
        }
        
        with patch.object(Path, 'resolve') as mock_resolve:
            mock_path = MagicMock()
            mock_resolve.return_value = mock_path
            mock_path.read_text.return_value = "old text"
            mock_path.__str__ = MagicMock(return_value="/workspace/test.py")
            
            result = await tool.execute(tool_input)
        
        assert "Modified" in result.llm_content or "modified" in result.llm_content.lower()
        assert "test.py" in result.llm_content


# =============================================================================
# Test FileEditTool.execute_mcp_wrapper() Method
# =============================================================================

class TestFileEditToolMCPWrapper:
    """Tests for execute_mcp_wrapper method."""

    @pytest.mark.asyncio
    async def test_mcp_wrapper_calls_internal_wrapper(self):
        """Test MCP wrapper calls _mcp_wrapper with correct args."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        tool = FileEditTool(workspace_manager=mock_wm)
        
        tool._mcp_wrapper = AsyncMock(return_value=ToolResult(llm_content="Success"))
        
        await tool.execute_mcp_wrapper(
            file_path="/workspace/test.py",
            old_string="old",
            new_string="new",
            replace_all=False
        )
        
        tool._mcp_wrapper.assert_called_once_with(
            tool_input={
                "file_path": "/workspace/test.py",
                "old_string": "old",
                "new_string": "new",
                "replace_all": False
            }
        )

    @pytest.mark.asyncio
    async def test_mcp_wrapper_default_replace_all(self):
        """Test MCP wrapper with default replace_all value."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        tool = FileEditTool(workspace_manager=mock_wm)
        
        tool._mcp_wrapper = AsyncMock(return_value=ToolResult(llm_content="Success"))
        
        await tool.execute_mcp_wrapper(
            file_path="/workspace/test.py",
            old_string="old",
            new_string="new"
        )
        
        call_args = tool._mcp_wrapper.call_args[1]["tool_input"]
        assert call_args["replace_all"] is False

    @pytest.mark.asyncio
    async def test_mcp_wrapper_replace_all_true(self):
        """Test MCP wrapper with replace_all=True."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        tool = FileEditTool(workspace_manager=mock_wm)
        
        tool._mcp_wrapper = AsyncMock(return_value=ToolResult(llm_content="Success"))
        
        await tool.execute_mcp_wrapper(
            file_path="/workspace/test.py",
            old_string="var",
            new_string="variable",
            replace_all=True
        )
        
        call_args = tool._mcp_wrapper.call_args[1]["tool_input"]
        assert call_args["replace_all"] is True


# =============================================================================
# Test FileEditTool Edge Cases
# =============================================================================

class TestFileEditToolEdgeCases:
    """Tests for edge cases and special scenarios."""

    @pytest.mark.asyncio
    async def test_replace_all_defaults_to_false(self):
        """Test replace_all defaults to False when not provided."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        tool = FileEditTool(workspace_manager=mock_wm)
        
        tool_input = {
            "file_path": "/workspace/test.py",
            "old_string": "unique",
            "new_string": "changed"
            # replace_all not provided
        }
        
        with patch.object(Path, 'resolve') as mock_resolve:
            mock_path = MagicMock()
            mock_resolve.return_value = mock_path
            mock_path.read_text.return_value = "unique value"
            mock_path.__str__ = MagicMock(return_value="/workspace/test.py")
            
            result = await tool.execute(tool_input)
        
        # Should succeed with single occurrence
        assert result.is_error is False

    @pytest.mark.asyncio
    async def test_empty_new_string_deletion(self):
        """Test replacement with empty new_string (deletion)."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        tool = FileEditTool(workspace_manager=mock_wm)
        
        tool_input = {
            "file_path": "/workspace/test.py",
            "old_string": "DELETE_ME",
            "new_string": ""
        }
        
        with patch.object(Path, 'resolve') as mock_resolve:
            mock_path = MagicMock()
            mock_resolve.return_value = mock_path
            mock_path.read_text.return_value = "prefix DELETE_ME suffix"
            mock_path.__str__ = MagicMock(return_value="/workspace/test.py")
            
            result = await tool.execute(tool_input)
            
            written_content = mock_path.write_text.call_args[0][0]
            assert written_content == "prefix  suffix"
            assert result.is_error is False

    @pytest.mark.asyncio
    async def test_multiline_string_replacement(self):
        """Test replacement of multiline strings."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        tool = FileEditTool(workspace_manager=mock_wm)
        
        old_str = """def old_function():
    pass"""
        new_str = """def new_function():
    return True"""
        
        tool_input = {
            "file_path": "/workspace/test.py",
            "old_string": old_str,
            "new_string": new_str
        }
        
        file_content = f"""# Header
{old_str}
# Footer"""
        
        with patch.object(Path, 'resolve') as mock_resolve:
            mock_path = MagicMock()
            mock_resolve.return_value = mock_path
            mock_path.read_text.return_value = file_content
            mock_path.__str__ = MagicMock(return_value="/workspace/test.py")
            
            result = await tool.execute(tool_input)
            
            written_content = mock_path.write_text.call_args[0][0]
            assert "def new_function():" in written_content
            assert "return True" in written_content
            assert result.is_error is False

    @pytest.mark.asyncio
    async def test_special_regex_characters(self):
        """Test replacement with special regex characters in string."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        tool = FileEditTool(workspace_manager=mock_wm)
        
        tool_input = {
            "file_path": "/workspace/test.py",
            "old_string": "price: $10.00",
            "new_string": "price: $20.00"
        }
        
        with patch.object(Path, 'resolve') as mock_resolve:
            mock_path = MagicMock()
            mock_resolve.return_value = mock_path
            mock_path.read_text.return_value = "The price: $10.00 is fair"
            mock_path.__str__ = MagicMock(return_value="/workspace/test.py")
            
            result = await tool.execute(tool_input)
            
            written_content = mock_path.write_text.call_args[0][0]
            assert written_content == "The price: $20.00 is fair"

    @pytest.mark.asyncio
    async def test_indentation_preservation(self):
        """Test that indentation is preserved correctly."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        tool = FileEditTool(workspace_manager=mock_wm)
        
        tool_input = {
            "file_path": "/workspace/test.py",
            "old_string": "    indented_old",
            "new_string": "    indented_new"
        }
        
        with patch.object(Path, 'resolve') as mock_resolve:
            mock_path = MagicMock()
            mock_resolve.return_value = mock_path
            mock_path.read_text.return_value = "class Test:\n    indented_old\n"
            mock_path.__str__ = MagicMock(return_value="/workspace/test.py")
            
            result = await tool.execute(tool_input)
            
            written_content = mock_path.write_text.call_args[0][0]
            assert "    indented_new" in written_content

    @pytest.mark.asyncio
    async def test_uses_utf8_encoding(self):
        """Test that UTF-8 encoding is used."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        tool = FileEditTool(workspace_manager=mock_wm)
        
        tool_input = {
            "file_path": "/workspace/test.py",
            "old_string": "old",
            "new_string": "new"
        }
        
        with patch.object(Path, 'resolve') as mock_resolve:
            mock_path = MagicMock()
            mock_resolve.return_value = mock_path
            mock_path.read_text.return_value = "old content"
            mock_path.__str__ = MagicMock(return_value="/workspace/test.py")
            
            await tool.execute(tool_input)
            
            mock_path.read_text.assert_called_with(encoding='utf-8')
            write_call = mock_path.write_text.call_args
            assert write_call[1]['encoding'] == 'utf-8'


# =============================================================================
# Test FileEditTool Integration Scenarios
# =============================================================================

class TestFileEditToolIntegration:
    """Integration-style tests with realistic scenarios."""

    @pytest.mark.asyncio
    async def test_rename_variable(self):
        """Test renaming a variable across the file."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        tool = FileEditTool(workspace_manager=mock_wm)
        
        tool_input = {
            "file_path": "/workspace/test.py",
            "old_string": "old_var",
            "new_string": "new_var",
            "replace_all": True
        }
        
        file_content = """old_var = 10
print(old_var)
result = old_var * 2"""
        
        with patch.object(Path, 'resolve') as mock_resolve:
            mock_path = MagicMock()
            mock_resolve.return_value = mock_path
            mock_path.read_text.return_value = file_content
            mock_path.__str__ = MagicMock(return_value="/workspace/test.py")
            
            result = await tool.execute(tool_input)
            
            written_content = mock_path.write_text.call_args[0][0]
            assert "old_var" not in written_content
            assert written_content.count("new_var") == 3
            assert "3 replacement" in result.llm_content

    @pytest.mark.asyncio
    async def test_fix_typo(self):
        """Test fixing a single typo."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        tool = FileEditTool(workspace_manager=mock_wm)
        
        tool_input = {
            "file_path": "/workspace/test.py",
            "old_string": "def recieve_data(",
            "new_string": "def receive_data("
        }
        
        with patch.object(Path, 'resolve') as mock_resolve:
            mock_path = MagicMock()
            mock_resolve.return_value = mock_path
            mock_path.read_text.return_value = "def recieve_data(x):\n    return x"
            mock_path.__str__ = MagicMock(return_value="/workspace/test.py")
            
            result = await tool.execute(tool_input)
            
            written_content = mock_path.write_text.call_args[0][0]
            assert "receive_data" in written_content
            assert result.is_error is False
