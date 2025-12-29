"""Unit tests for ii_tool.tools.file_system.file_write_tool module."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

from ii_tool.tools.file_system.file_write_tool import (
    FileWriteTool,
    NAME,
    DISPLAY_NAME,
    DESCRIPTION,
    INPUT_SCHEMA,
)
from ii_tool.tools.base import ToolResult, ToolConfirmationDetails
from ii_tool.core.workspace import WorkspaceManager, FileSystemValidationError


# =============================================================================
# Test Constants and Schema
# =============================================================================

class TestModuleConstants:
    """Tests for module-level constants."""

    def test_name_constant(self):
        """Test NAME constant value."""
        assert NAME == "Write"

    def test_display_name_constant(self):
        """Test DISPLAY_NAME constant value."""
        assert DISPLAY_NAME == "Write file"

    def test_description_not_empty(self):
        """Test DESCRIPTION is not empty."""
        assert DESCRIPTION
        assert len(DESCRIPTION) > 50

    def test_description_contains_key_info(self):
        """Test DESCRIPTION contains important information."""
        assert "overwrite" in DESCRIPTION.lower()
        assert "read" in DESCRIPTION.lower()

    def test_input_schema_structure(self):
        """Test INPUT_SCHEMA has required structure."""
        assert INPUT_SCHEMA["type"] == "object"
        assert "properties" in INPUT_SCHEMA
        assert "required" in INPUT_SCHEMA

    def test_input_schema_properties(self):
        """Test INPUT_SCHEMA has correct properties."""
        props = INPUT_SCHEMA["properties"]
        assert "file_path" in props
        assert "content" in props

    def test_input_schema_required_fields(self):
        """Test INPUT_SCHEMA has correct required fields."""
        assert set(INPUT_SCHEMA["required"]) == {"file_path", "content"}

    def test_file_path_schema(self):
        """Test file_path property schema."""
        file_path_schema = INPUT_SCHEMA["properties"]["file_path"]
        assert file_path_schema["type"] == "string"
        assert "description" in file_path_schema

    def test_content_schema(self):
        """Test content property schema."""
        content_schema = INPUT_SCHEMA["properties"]["content"]
        assert content_schema["type"] == "string"
        assert "description" in content_schema


# =============================================================================
# Test FileWriteTool Class
# =============================================================================

class TestFileWriteToolAttributes:
    """Tests for FileWriteTool class attributes."""

    def test_class_name_attribute(self):
        """Test class name attribute matches constant."""
        assert FileWriteTool.name == NAME

    def test_class_display_name_attribute(self):
        """Test class display_name attribute."""
        assert FileWriteTool.display_name == DISPLAY_NAME

    def test_class_description_attribute(self):
        """Test class description attribute."""
        assert FileWriteTool.description == DESCRIPTION

    def test_class_input_schema_attribute(self):
        """Test class input_schema attribute."""
        assert FileWriteTool.input_schema == INPUT_SCHEMA

    def test_class_read_only_attribute(self):
        """Test class read_only is False (writing modifies files)."""
        assert FileWriteTool.read_only is False


class TestFileWriteToolInit:
    """Tests for FileWriteTool initialization."""

    def test_init_with_workspace_manager(self):
        """Test initialization stores workspace_manager."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        tool = FileWriteTool(workspace_manager=mock_wm)
        assert tool.workspace_manager is mock_wm

    def test_init_different_workspace_managers(self):
        """Test initialization with different workspace managers."""
        mock_wm1 = MagicMock(spec=WorkspaceManager)
        mock_wm2 = MagicMock(spec=WorkspaceManager)
        
        tool1 = FileWriteTool(workspace_manager=mock_wm1)
        tool2 = FileWriteTool(workspace_manager=mock_wm2)
        
        assert tool1.workspace_manager is not tool2.workspace_manager


class TestFileWriteToolShouldConfirmExecute:
    """Tests for should_confirm_execute method."""

    def test_returns_confirmation_details(self):
        """Test method returns ToolConfirmationDetails."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        tool = FileWriteTool(workspace_manager=mock_wm)
        
        tool_input = {
            "file_path": "/workspace/test.txt",
            "content": "Hello World"
        }
        
        result = tool.should_confirm_execute(tool_input)
        
        assert isinstance(result, ToolConfirmationDetails)

    def test_confirmation_type_is_edit(self):
        """Test confirmation type is 'edit'."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        tool = FileWriteTool(workspace_manager=mock_wm)
        
        tool_input = {
            "file_path": "/workspace/test.txt",
            "content": "Hello World"
        }
        
        result = tool.should_confirm_execute(tool_input)
        
        assert result.type == "edit"

    def test_confirmation_message_contains_file_path(self):
        """Test confirmation message contains file path."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        tool = FileWriteTool(workspace_manager=mock_wm)
        
        tool_input = {
            "file_path": "/workspace/myfile.py",
            "content": "print('hello')"
        }
        
        result = tool.should_confirm_execute(tool_input)
        
        assert "/workspace/myfile.py" in result.message

    def test_confirmation_message_contains_content(self):
        """Test confirmation message contains content."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        tool = FileWriteTool(workspace_manager=mock_wm)
        
        content = "def hello():\n    return 'world'"
        tool_input = {
            "file_path": "/workspace/test.py",
            "content": content
        }
        
        result = tool.should_confirm_execute(tool_input)
        
        assert content in result.message


# =============================================================================
# Test FileWriteTool.execute() Method
# =============================================================================

class TestFileWriteToolExecuteValidation:
    """Tests for execute method input validation and path validation."""

    @pytest.mark.asyncio
    async def test_path_validation_called(self):
        """Test that workspace path validation is called."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        tool = FileWriteTool(workspace_manager=mock_wm)
        
        tool_input = {
            "file_path": "/workspace/test.txt",
            "content": "test content"
        }
        
        with patch.object(Path, 'exists', return_value=False), \
             patch.object(Path, 'is_dir', return_value=False), \
             patch.object(Path, 'parent', MagicMock()), \
             patch.object(Path, 'write_text'):
            
            await tool.execute(tool_input)
        
        mock_wm.validate_path.assert_called_once_with("/workspace/test.txt")

    @pytest.mark.asyncio
    async def test_validation_error_returns_error_result(self):
        """Test that validation error returns error ToolResult."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        mock_wm.validate_path.side_effect = FileSystemValidationError("Path outside workspace")
        tool = FileWriteTool(workspace_manager=mock_wm)
        
        tool_input = {
            "file_path": "/etc/passwd",
            "content": "malicious"
        }
        
        result = await tool.execute(tool_input)
        
        assert isinstance(result, ToolResult)
        assert result.is_error is True
        assert "Path outside workspace" in result.llm_content


class TestFileWriteToolExecuteDirectoryCheck:
    """Tests for execute method directory check."""

    @pytest.mark.asyncio
    async def test_error_when_path_is_directory(self):
        """Test error when trying to write to a directory."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        tool = FileWriteTool(workspace_manager=mock_wm)
        
        tool_input = {
            "file_path": "/workspace/somedir",
            "content": "content"
        }
        
        with patch.object(Path, 'resolve', return_value=Path("/workspace/somedir")), \
             patch.object(Path, 'exists', return_value=True), \
             patch.object(Path, 'is_dir', return_value=True):
            
            result = await tool.execute(tool_input)
        
        assert result.is_error is True
        assert "directory" in result.llm_content.lower()
        assert "not a file" in result.llm_content.lower()


class TestFileWriteToolExecuteNewFile:
    """Tests for execute method creating new files."""

    @pytest.mark.asyncio
    async def test_creates_parent_directories(self):
        """Test that parent directories are created."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        tool = FileWriteTool(workspace_manager=mock_wm)
        
        mock_parent = MagicMock()
        
        tool_input = {
            "file_path": "/workspace/new/path/file.txt",
            "content": "test content"
        }
        
        with patch.object(Path, 'resolve') as mock_resolve:
            mock_path = MagicMock()
            mock_resolve.return_value = mock_path
            mock_path.exists.return_value = False
            mock_path.is_dir.return_value = False
            mock_path.parent = mock_parent
            
            await tool.execute(tool_input)
            
            mock_parent.mkdir.assert_called_once_with(parents=True, exist_ok=True)

    @pytest.mark.asyncio
    async def test_writes_content_to_new_file(self):
        """Test that content is written to new file."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        tool = FileWriteTool(workspace_manager=mock_wm)
        
        tool_input = {
            "file_path": "/workspace/newfile.txt",
            "content": "Hello, World!"
        }
        
        with patch.object(Path, 'resolve') as mock_resolve:
            mock_path = MagicMock()
            mock_resolve.return_value = mock_path
            mock_path.exists.return_value = False
            mock_path.is_dir.return_value = False
            mock_path.parent = MagicMock()
            
            await tool.execute(tool_input)
            
            mock_path.write_text.assert_called_once_with("Hello, World!", encoding='utf-8')

    @pytest.mark.asyncio
    async def test_new_file_success_message(self):
        """Test success message for new file creation."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        tool = FileWriteTool(workspace_manager=mock_wm)
        
        tool_input = {
            "file_path": "/workspace/brand_new.txt",
            "content": "content"
        }
        
        with patch.object(Path, 'resolve') as mock_resolve:
            mock_path = MagicMock()
            mock_resolve.return_value = mock_path
            mock_path.exists.return_value = False
            mock_path.is_dir.return_value = False
            mock_path.parent = MagicMock()
            mock_path.__str__ = MagicMock(return_value="/workspace/brand_new.txt")
            
            result = await tool.execute(tool_input)
        
        assert result.is_error is False
        assert "new file" in result.llm_content.lower()
        assert "created" in result.llm_content.lower()


class TestFileWriteToolExecuteOverwrite:
    """Tests for execute method overwriting existing files."""

    @pytest.mark.asyncio
    async def test_overwrites_existing_file(self):
        """Test that existing file is overwritten."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        tool = FileWriteTool(workspace_manager=mock_wm)
        
        tool_input = {
            "file_path": "/workspace/existing.txt",
            "content": "new content"
        }
        
        with patch.object(Path, 'resolve') as mock_resolve:
            mock_path = MagicMock()
            mock_resolve.return_value = mock_path
            # First call returns True (file exists), subsequent calls are for is_dir
            mock_path.exists.return_value = True
            mock_path.is_dir.return_value = False
            mock_path.parent = MagicMock()
            
            result = await tool.execute(tool_input)
            
            mock_path.write_text.assert_called_once_with("new content", encoding='utf-8')

    @pytest.mark.asyncio
    async def test_overwrite_success_message(self):
        """Test success message for overwriting file."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        tool = FileWriteTool(workspace_manager=mock_wm)
        
        tool_input = {
            "file_path": "/workspace/existing.txt",
            "content": "content"
        }
        
        with patch.object(Path, 'resolve') as mock_resolve:
            mock_path = MagicMock()
            mock_resolve.return_value = mock_path
            mock_path.exists.return_value = True
            mock_path.is_dir.return_value = False
            mock_path.parent = MagicMock()
            mock_path.__str__ = MagicMock(return_value="/workspace/existing.txt")
            
            result = await tool.execute(tool_input)
        
        assert result.is_error is False
        assert "overwrote" in result.llm_content.lower()


class TestFileWriteToolExecuteEncoding:
    """Tests for execute method encoding handling."""

    @pytest.mark.asyncio
    async def test_uses_utf8_encoding(self):
        """Test that UTF-8 encoding is used."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        tool = FileWriteTool(workspace_manager=mock_wm)
        
        tool_input = {
            "file_path": "/workspace/unicode.txt",
            "content": "Unicode: 日本語 🎉"
        }
        
        with patch.object(Path, 'resolve') as mock_resolve:
            mock_path = MagicMock()
            mock_resolve.return_value = mock_path
            mock_path.exists.return_value = False
            mock_path.is_dir.return_value = False
            mock_path.parent = MagicMock()
            
            await tool.execute(tool_input)
            
            mock_path.write_text.assert_called_once()
            call_args = mock_path.write_text.call_args
            assert call_args[1]['encoding'] == 'utf-8'


# =============================================================================
# Test FileWriteTool.execute_mcp_wrapper() Method
# =============================================================================

class TestFileWriteToolMCPWrapper:
    """Tests for execute_mcp_wrapper method."""

    @pytest.mark.asyncio
    async def test_mcp_wrapper_calls_internal_wrapper(self):
        """Test MCP wrapper calls _mcp_wrapper with correct args."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        tool = FileWriteTool(workspace_manager=mock_wm)
        
        tool._mcp_wrapper = AsyncMock(return_value=ToolResult(llm_content="Success"))
        
        await tool.execute_mcp_wrapper(
            file_path="/workspace/test.txt",
            content="test content"
        )
        
        tool._mcp_wrapper.assert_called_once_with(
            tool_input={
                "file_path": "/workspace/test.txt",
                "content": "test content"
            }
        )

    @pytest.mark.asyncio
    async def test_mcp_wrapper_returns_result(self):
        """Test MCP wrapper returns the result."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        tool = FileWriteTool(workspace_manager=mock_wm)
        
        expected_result = ToolResult(llm_content="File written successfully")
        tool._mcp_wrapper = AsyncMock(return_value=expected_result)
        
        result = await tool.execute_mcp_wrapper(
            file_path="/workspace/test.txt",
            content="content"
        )
        
        assert result is expected_result


# =============================================================================
# Test FileWriteTool Edge Cases
# =============================================================================

class TestFileWriteToolEdgeCases:
    """Tests for edge cases and special scenarios."""

    @pytest.mark.asyncio
    async def test_empty_content(self):
        """Test writing empty content."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        tool = FileWriteTool(workspace_manager=mock_wm)
        
        tool_input = {
            "file_path": "/workspace/empty.txt",
            "content": ""
        }
        
        with patch.object(Path, 'resolve') as mock_resolve:
            mock_path = MagicMock()
            mock_resolve.return_value = mock_path
            mock_path.exists.return_value = False
            mock_path.is_dir.return_value = False
            mock_path.parent = MagicMock()
            
            result = await tool.execute(tool_input)
            
            mock_path.write_text.assert_called_once_with("", encoding='utf-8')
            assert result.is_error is False

    @pytest.mark.asyncio
    async def test_multiline_content(self):
        """Test writing multiline content."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        tool = FileWriteTool(workspace_manager=mock_wm)
        
        multiline_content = """Line 1
Line 2
Line 3
"""
        tool_input = {
            "file_path": "/workspace/multiline.txt",
            "content": multiline_content
        }
        
        with patch.object(Path, 'resolve') as mock_resolve:
            mock_path = MagicMock()
            mock_resolve.return_value = mock_path
            mock_path.exists.return_value = False
            mock_path.is_dir.return_value = False
            mock_path.parent = MagicMock()
            
            result = await tool.execute(tool_input)
            
            mock_path.write_text.assert_called_once_with(multiline_content, encoding='utf-8')

    @pytest.mark.asyncio
    async def test_special_characters_in_content(self):
        """Test writing content with special characters."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        tool = FileWriteTool(workspace_manager=mock_wm)
        
        special_content = "Tab:\tNewline:\nQuote:\"Backslash:\\"
        tool_input = {
            "file_path": "/workspace/special.txt",
            "content": special_content
        }
        
        with patch.object(Path, 'resolve') as mock_resolve:
            mock_path = MagicMock()
            mock_resolve.return_value = mock_path
            mock_path.exists.return_value = False
            mock_path.is_dir.return_value = False
            mock_path.parent = MagicMock()
            
            result = await tool.execute(tool_input)
            
            mock_path.write_text.assert_called_once_with(special_content, encoding='utf-8')

    @pytest.mark.asyncio
    async def test_missing_file_path_in_input(self):
        """Test behavior when file_path is missing from input."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        tool = FileWriteTool(workspace_manager=mock_wm)
        
        tool_input = {
            "content": "some content"
            # missing file_path
        }
        
        # The validate_path call will receive None
        mock_wm.validate_path.side_effect = FileSystemValidationError("Invalid path: None")
        
        result = await tool.execute(tool_input)
        
        assert result.is_error is True

    @pytest.mark.asyncio
    async def test_missing_content_in_input(self):
        """Test behavior when content is missing from input."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        tool = FileWriteTool(workspace_manager=mock_wm)
        
        tool_input = {
            "file_path": "/workspace/test.txt"
            # missing content
        }
        
        with patch.object(Path, 'resolve') as mock_resolve:
            mock_path = MagicMock()
            mock_resolve.return_value = mock_path
            mock_path.exists.return_value = False
            mock_path.is_dir.return_value = False
            mock_path.parent = MagicMock()
            
            result = await tool.execute(tool_input)
            
            # Content will be None, write_text should still be called
            mock_path.write_text.assert_called_once_with(None, encoding='utf-8')


# =============================================================================
# Test FileWriteTool Integration Scenarios  
# =============================================================================

class TestFileWriteToolIntegration:
    """Integration-style tests with realistic scenarios."""

    @pytest.mark.asyncio
    async def test_write_python_file(self):
        """Test writing a Python file."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        tool = FileWriteTool(workspace_manager=mock_wm)
        
        python_content = '''"""Module docstring."""

def hello_world():
    """Say hello."""
    print("Hello, World!")

if __name__ == "__main__":
    hello_world()
'''
        tool_input = {
            "file_path": "/workspace/hello.py",
            "content": python_content
        }
        
        with patch.object(Path, 'resolve') as mock_resolve:
            mock_path = MagicMock()
            mock_resolve.return_value = mock_path
            mock_path.exists.return_value = False
            mock_path.is_dir.return_value = False
            mock_path.parent = MagicMock()
            mock_path.__str__ = MagicMock(return_value="/workspace/hello.py")
            
            result = await tool.execute(tool_input)
        
        assert result.is_error is False
        mock_path.write_text.assert_called_once_with(python_content, encoding='utf-8')

    @pytest.mark.asyncio
    async def test_write_json_file(self):
        """Test writing a JSON file."""
        mock_wm = MagicMock(spec=WorkspaceManager)
        tool = FileWriteTool(workspace_manager=mock_wm)
        
        json_content = '''{
    "name": "test-project",
    "version": "1.0.0",
    "dependencies": {
        "python": ">=3.10"
    }
}'''
        tool_input = {
            "file_path": "/workspace/package.json",
            "content": json_content
        }
        
        with patch.object(Path, 'resolve') as mock_resolve:
            mock_path = MagicMock()
            mock_resolve.return_value = mock_path
            mock_path.exists.return_value = False
            mock_path.is_dir.return_value = False
            mock_path.parent = MagicMock()
            mock_path.__str__ = MagicMock(return_value="/workspace/package.json")
            
            result = await tool.execute(tool_input)
        
        assert result.is_error is False
