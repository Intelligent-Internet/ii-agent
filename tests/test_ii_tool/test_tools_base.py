"""Unit tests for ii_tool.tools.base module.

This module tests the foundational classes used by all tools:
- Pydantic models: ToolParam, TextContent, ImageContent, FileURLContent, etc.
- ToolResult: The standard result container for tool execution
- BaseTool: Abstract base class for all tools
- _mcp_wrapper: MCP format conversion
- get_tool_params: Tool parameter extraction
"""

import pytest
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

from ii_tool.tools.base import (
    BaseTool,
    FileEditToolResultContent,
    FileURLContent,
    ImageContent,
    TextContent,
    ToolConfirmationDetails,
    ToolParam,
    ToolResult,
)


# =============================================================================
# ToolParam Tests
# =============================================================================

class TestToolParam:
    """Tests for ToolParam Pydantic model."""

    def test_default_type_is_function(self):
        """ToolParam.type should default to 'function'."""
        param = ToolParam(
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object", "properties": {}}
        )
        assert param.type == "function"

    def test_custom_type(self):
        """ToolParam can have custom type."""
        param = ToolParam(
            type="custom",
            name="custom_tool",
            description="A custom tool",
            input_schema={"format": "special"}
        )
        assert param.type == "custom"

    def test_required_fields(self):
        """ToolParam requires name, description, and input_schema."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            ToolParam(name="test")  # Missing required fields

    def test_serialization(self):
        """ToolParam should serialize to dict correctly."""
        param = ToolParam(
            name="test",
            description="desc",
            input_schema={"type": "object"}
        )
        data = param.model_dump()
        assert data["name"] == "test"
        assert data["description"] == "desc"
        assert data["type"] == "function"


# =============================================================================
# Content Model Tests
# =============================================================================

class TestTextContent:
    """Tests for TextContent Pydantic model."""

    def test_type_literal(self):
        """TextContent.type must be 'text'."""
        content = TextContent(type="text", text="hello")
        assert content.type == "text"
        assert content.text == "hello"

    def test_empty_text(self):
        """TextContent allows empty text."""
        content = TextContent(type="text", text="")
        assert content.text == ""


class TestImageContent:
    """Tests for ImageContent Pydantic model."""

    def test_fields(self):
        """ImageContent should store base64 data and mime_type."""
        content = ImageContent(
            type="image",
            data="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
            mime_type="image/png"
        )
        assert content.type == "image"
        assert "iVBOR" in content.data  # Base64 PNG header
        assert content.mime_type == "image/png"

    def test_various_mime_types(self):
        """ImageContent supports various image MIME types."""
        for mime in ["image/png", "image/jpeg", "image/gif", "image/webp"]:
            content = ImageContent(type="image", data="abc123", mime_type=mime)
            assert content.mime_type == mime


class TestFileEditToolResultContent:
    """Tests for FileEditToolResultContent Pydantic model."""

    def test_default_type(self):
        """FileEditToolResultContent.type defaults to 'file_edit'."""
        content = FileEditToolResultContent(
            old_content="before",
            new_content="after"
        )
        assert content.type == "file_edit"

    def test_diff_content(self):
        """FileEditToolResultContent stores old and new content."""
        content = FileEditToolResultContent(
            old_content="line1\nline2",
            new_content="line1\nmodified"
        )
        assert "line2" in content.old_content
        assert "modified" in content.new_content


class TestFileURLContent:
    """Tests for FileURLContent Pydantic model."""

    def test_all_fields(self):
        """FileURLContent requires all fields."""
        content = FileURLContent(
            type="file_url",
            url="https://example.com/file.png",
            mime_type="image/png",
            name="file.png",
            size=1024
        )
        assert content.type == "file_url"
        assert content.url == "https://example.com/file.png"
        assert content.mime_type == "image/png"
        assert content.name == "file.png"
        assert content.size == 1024

    def test_serialization_for_frontend(self):
        """FileURLContent serializes correctly for frontend consumption."""
        content = FileURLContent(
            type="file_url",
            url="https://storage.example.com/img.jpg",
            mime_type="image/jpeg",
            name="photo.jpg",
            size=2048
        )
        data = content.model_dump()
        assert data["type"] == "file_url"
        assert data["url"].startswith("https://")


# =============================================================================
# ToolResult Tests
# =============================================================================

class TestToolResult:
    """Tests for ToolResult Pydantic model."""

    def test_string_llm_content(self):
        """ToolResult accepts string llm_content."""
        result = ToolResult(llm_content="Operation completed successfully")
        assert result.llm_content == "Operation completed successfully"
        assert result.is_error is None
        assert result.is_interrupted is False

    def test_list_llm_content_text(self):
        """ToolResult accepts list of TextContent."""
        result = ToolResult(
            llm_content=[
                TextContent(type="text", text="First part"),
                TextContent(type="text", text="Second part"),
            ]
        )
        assert len(result.llm_content) == 2
        assert result.llm_content[0].text == "First part"

    def test_list_llm_content_mixed(self):
        """ToolResult accepts mixed TextContent and ImageContent."""
        result = ToolResult(
            llm_content=[
                TextContent(type="text", text="Here's an image:"),
                ImageContent(type="image", data="base64data", mime_type="image/png"),
            ]
        )
        assert len(result.llm_content) == 2
        assert isinstance(result.llm_content[0], TextContent)
        assert isinstance(result.llm_content[1], ImageContent)

    def test_user_display_content_string(self):
        """ToolResult accepts string user_display_content."""
        result = ToolResult(
            llm_content="done",
            user_display_content="Task completed!"
        )
        assert result.user_display_content == "Task completed!"

    def test_user_display_content_dict(self):
        """ToolResult accepts dict user_display_content."""
        result = ToolResult(
            llm_content="done",
            user_display_content={"status": "success", "files": ["a.txt", "b.txt"]}
        )
        assert result.user_display_content["status"] == "success"

    def test_user_display_content_list(self):
        """ToolResult accepts list of dicts for user_display_content."""
        result = ToolResult(
            llm_content="done",
            user_display_content=[
                {"file": "a.txt", "action": "created"},
                {"file": "b.txt", "action": "modified"},
            ]
        )
        assert len(result.user_display_content) == 2

    def test_is_error_flag(self):
        """ToolResult.is_error indicates execution failure."""
        result = ToolResult(
            llm_content="Error: File not found",
            is_error=True
        )
        assert result.is_error is True

    def test_is_interrupted_flag(self):
        """ToolResult.is_interrupted indicates user cancellation."""
        result = ToolResult(
            llm_content="Operation cancelled by user",
            is_interrupted=True
        )
        assert result.is_interrupted is True


# =============================================================================
# ToolConfirmationDetails Tests
# =============================================================================

class TestToolConfirmationDetails:
    """Tests for ToolConfirmationDetails Pydantic model."""

    def test_edit_type(self):
        """ToolConfirmationDetails supports 'edit' type."""
        details = ToolConfirmationDetails(
            type="edit",
            message="Modify file.py?"
        )
        assert details.type == "edit"

    def test_bash_type(self):
        """ToolConfirmationDetails supports 'bash' type."""
        details = ToolConfirmationDetails(
            type="bash",
            message="Run: rm -rf /tmp/test"
        )
        assert details.type == "bash"

    def test_mcp_type(self):
        """ToolConfirmationDetails supports 'mcp' type."""
        details = ToolConfirmationDetails(
            type="mcp",
            message="Execute MCP tool?"
        )
        assert details.type == "mcp"


# =============================================================================
# BaseTool Tests
# =============================================================================

class ConcreteTestTool(BaseTool):
    """Concrete implementation of BaseTool for testing."""
    
    name = "test_tool"
    display_name = "Test Tool"
    description = "A tool for testing"
    input_schema = {
        "type": "object",
        "properties": {
            "input": {"type": "string", "description": "Test input"}
        },
        "required": ["input"]
    }
    read_only = True

    async def execute(self, tool_input: Dict[str, Any]) -> ToolResult:
        return ToolResult(
            llm_content=f"Executed with: {tool_input.get('input', '')}",
            user_display_content={"processed": True}
        )


class ConcreteToolWithMetadata(BaseTool):
    """Concrete tool with custom metadata format."""
    
    name = "custom_format_tool"
    display_name = "Custom Format Tool"
    description = "A tool with custom format"
    input_schema = {"type": "object"}
    read_only = False
    # The metadata["format"] is used as input_schema when type is "custom"
    # Per the code, input_schema must be a dict even for custom type
    metadata = {"format": {"type": "custom_object", "template": "{{input}}"}}

    async def execute(self, tool_input: Dict[str, Any]) -> ToolResult:
        return ToolResult(llm_content="done")


class TestBaseTool:
    """Tests for BaseTool abstract base class."""

    def test_concrete_implementation(self):
        """Concrete tool should have all required attributes."""
        tool = ConcreteTestTool()
        assert tool.name == "test_tool"
        assert tool.display_name == "Test Tool"
        assert tool.description == "A tool for testing"
        assert tool.read_only is True
        assert "properties" in tool.input_schema

    def test_should_confirm_execute_default(self):
        """Default should_confirm_execute returns False."""
        tool = ConcreteTestTool()
        result = tool.should_confirm_execute({"input": "test"})
        assert result is False

    @pytest.mark.asyncio
    async def test_execute_returns_tool_result(self):
        """execute() should return ToolResult."""
        tool = ConcreteTestTool()
        result = await tool.execute({"input": "hello"})
        assert isinstance(result, ToolResult)
        assert "hello" in result.llm_content

    def test_get_tool_params_standard(self):
        """get_tool_params returns ToolParam for standard tools."""
        tool = ConcreteTestTool()
        params = tool.get_tool_params()
        assert isinstance(params, ToolParam)
        assert params.type == "function"
        assert params.name == "test_tool"
        assert params.description == "A tool for testing"

    def test_get_tool_params_custom_metadata(self):
        """get_tool_params returns custom type for tools with metadata."""
        tool = ConcreteToolWithMetadata()
        params = tool.get_tool_params()
        assert params.type == "custom"
        # The format dict is passed as input_schema
        assert params.input_schema == {"type": "custom_object", "template": "{{input}}"}


# =============================================================================
# _mcp_wrapper Tests
# =============================================================================

class TestMCPWrapper:
    """Tests for BaseTool._mcp_wrapper method."""

    @pytest.mark.asyncio
    async def test_string_content_conversion(self):
        """_mcp_wrapper converts string llm_content to MCP TextContent."""
        tool = ConcreteTestTool()
        
        # Test with actual execution - don't mock internals
        result = await tool._mcp_wrapper({"input": "test"})
        
        # Result should have content list and structured_content
        assert hasattr(result, 'content')
        assert hasattr(result, 'structured_content')
        assert "user_display_content" in result.structured_content
        
        # Content should be a list with text content
        assert len(result.content) > 0
        assert result.content[0].type == "text"

    @pytest.mark.asyncio
    async def test_wrapper_preserves_error_status(self):
        """_mcp_wrapper preserves is_error in structured_content."""
        
        class ErrorTool(BaseTool):
            name = "error_tool"
            display_name = "Error Tool"
            description = "Returns error"
            input_schema = {"type": "object"}
            read_only = True
            
            async def execute(self, tool_input):
                return ToolResult(llm_content="Error occurred", is_error=True)
        
        tool = ErrorTool()
        result = await tool._mcp_wrapper({})
        assert result.structured_content["is_error"] is True

    @pytest.mark.asyncio
    async def test_wrapper_handles_image_content(self):
        """_mcp_wrapper converts ImageContent to MCP ImageContent."""
        
        class ImageTool(BaseTool):
            name = "image_tool"
            display_name = "Image Tool"
            description = "Returns image"
            input_schema = {"type": "object"}
            read_only = True
            
            async def execute(self, tool_input):
                return ToolResult(
                    llm_content=[
                        ImageContent(type="image", data="base64data", mime_type="image/png")
                    ]
                )
        
        tool = ImageTool()
        result = await tool._mcp_wrapper({})
        # Should have converted ImageContent
        assert len(result.content) == 1

    @pytest.mark.asyncio
    async def test_wrapper_handles_mixed_content(self):
        """_mcp_wrapper handles mixed TextContent and ImageContent."""
        
        class MixedTool(BaseTool):
            name = "mixed_tool"
            display_name = "Mixed Tool"
            description = "Returns mixed content"
            input_schema = {"type": "object"}
            read_only = True
            
            async def execute(self, tool_input):
                return ToolResult(
                    llm_content=[
                        TextContent(type="text", text="Here's an image:"),
                        ImageContent(type="image", data="abc", mime_type="image/jpeg"),
                        TextContent(type="text", text="End of content"),
                    ]
                )
        
        tool = MixedTool()
        result = await tool._mcp_wrapper({})
        assert len(result.content) == 3


# =============================================================================
# Edge Cases and Integration Tests
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_tool_result_with_none_values(self):
        """ToolResult handles None optional fields gracefully."""
        result = ToolResult(
            llm_content="test",
            user_display_content=None,
            is_error=None
        )
        assert result.user_display_content is None
        assert result.is_error is None

    def test_tool_result_empty_list_content(self):
        """ToolResult handles empty list llm_content."""
        result = ToolResult(llm_content=[])
        assert result.llm_content == []

    def test_file_url_content_zero_size(self):
        """FileURLContent allows zero size (empty file)."""
        content = FileURLContent(
            type="file_url",
            url="https://example.com/empty.txt",
            mime_type="text/plain",
            name="empty.txt",
            size=0
        )
        assert content.size == 0

    def test_tool_param_complex_schema(self):
        """ToolParam handles complex nested input_schema."""
        schema = {
            "type": "object",
            "properties": {
                "files": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "content": {"type": "string"}
                        }
                    }
                },
                "options": {
                    "type": "object",
                    "properties": {
                        "recursive": {"type": "boolean"},
                        "depth": {"type": "integer"}
                    }
                }
            }
        }
        param = ToolParam(
            name="complex_tool",
            description="Complex schema tool",
            input_schema=schema
        )
        assert param.input_schema["properties"]["files"]["type"] == "array"
