"""Tests for BaseTool and related classes."""

import pytest
from unittest.mock import Mock
from pydantic import ValidationError

from ii_agent.tools.base import (
    BaseTool,
    ToolResult,
    ToolConfirmationDetails,
    ToolConfirmationOutcome,
    TextContent,
    ImageContent,
)


class TestTextContent:
    """Test cases for TextContent."""

    def test_text_content_creation(self):
        """Test creating TextContent."""
        content = TextContent(type="text", text="Hello world")
        assert content.type == "text"
        assert content.text == "Hello world"

    def test_text_content_validation(self):
        """Test TextContent validation."""
        # Valid content
        content = TextContent(type="text", text="Valid text")
        assert content.type == "text"

        # Invalid type should raise ValidationError
        with pytest.raises(ValidationError):
            TextContent(type="invalid", text="Text")


class TestImageContent:
    """Test cases for ImageContent."""

    def test_image_content_creation(self):
        """Test creating ImageContent."""
        content = ImageContent(
            type="image", data="base64encodeddata", mimeType="image/png"
        )
        assert content.type == "image"
        assert content.data == "base64encodeddata"
        assert content.mimeType == "image/png"

    def test_image_content_validation(self):
        """Test ImageContent validation."""
        # Valid content
        content = ImageContent(type="image", data="data", mimeType="image/jpeg")
        assert content.type == "image"

        # Invalid type should raise ValidationError
        with pytest.raises(ValidationError):
            ImageContent(type="invalid", data="data", mimeType="image/png")


class TestToolResult:
    """Test cases for ToolResult."""

    def test_tool_result_with_string_content(self):
        """Test ToolResult with string content."""
        result = ToolResult(
            llm_content="LLM response", user_display_content="User display"
        )
        assert result.llm_content == "LLM response"
        assert result.user_display_content == "User display"

    def test_tool_result_with_list_content(self):
        """Test ToolResult with list of content blocks."""
        text_content = TextContent(type="text", text="Text response")
        image_content = ImageContent(
            type="image", data="base64data", mimeType="image/png"
        )

        result = ToolResult(
            llm_content=[text_content, image_content],
            user_display_content="Mixed content response",
        )

        assert len(result.llm_content) == 2
        assert result.llm_content[0] == text_content
        assert result.llm_content[1] == image_content
        assert result.user_display_content == "Mixed content response"

    def test_tool_result_empty_list_content(self):
        """Test ToolResult with empty list content."""
        result = ToolResult(llm_content=[], user_display_content="Empty content")

        assert result.llm_content == []
        assert result.user_display_content == "Empty content"


class TestToolConfirmationOutcome:
    """Test cases for ToolConfirmationOutcome enum."""

    def test_confirmation_outcome_values(self):
        """Test ToolConfirmationOutcome enum values."""
        assert ToolConfirmationOutcome.PROCEED_ONCE.value == "proceed_once"
        assert ToolConfirmationOutcome.PROCEED_ALWAYS.value == "proceed_always"
        assert ToolConfirmationOutcome.DO_OTHER.value == "do_other"

    def test_confirmation_outcome_membership(self):
        """Test ToolConfirmationOutcome membership."""
        assert ToolConfirmationOutcome.PROCEED_ONCE in ToolConfirmationOutcome
        assert ToolConfirmationOutcome.PROCEED_ALWAYS in ToolConfirmationOutcome
        assert ToolConfirmationOutcome.DO_OTHER in ToolConfirmationOutcome


class TestToolConfirmationDetails:
    """Test cases for ToolConfirmationDetails."""

    def test_confirmation_details_creation(self):
        """Test creating ToolConfirmationDetails."""
        details = ToolConfirmationDetails(
            type="edit", message="Do you want to edit this file?"
        )
        assert details.type == "edit"
        assert details.message == "Do you want to edit this file?"
        assert details.on_confirm_callback is None

    def test_confirmation_details_with_callback(self):
        """Test ToolConfirmationDetails with callback."""
        callback = Mock()
        details = ToolConfirmationDetails(
            type="bash", message="Execute this command?", on_confirm_callback=callback
        )

        assert details.type == "bash"
        assert details.message == "Execute this command?"
        assert details.on_confirm_callback == callback

    def test_confirmation_details_valid_types(self):
        """Test ToolConfirmationDetails with valid types."""
        valid_types = ["edit", "bash", "mcp"]

        for valid_type in valid_types:
            details = ToolConfirmationDetails(type=valid_type, message="Test message")
            assert details.type == valid_type

    def test_confirmation_details_invalid_type(self):
        """Test ToolConfirmationDetails with invalid type."""
        with pytest.raises(ValidationError):
            ToolConfirmationDetails(type="invalid", message="Test message")


class MockTool(BaseTool):
    """Mock implementation of BaseTool for testing."""

    def __init__(self, read_only=False):
        self.name = "mock_tool"
        self.description = "A mock tool for testing"
        self.input_schema = {"type": "object"}
        self.display_name = "Mock Tool"
        self._read_only = read_only

    def is_read_only(self):
        return self._read_only

    async def should_confirm_execute(self, tool_input):
        return False

    async def execute(self, tool_input):
        return ToolResult(
            llm_content="Mock result", user_display_content="Mock display result"
        )


class TestBaseTool:
    """Test cases for BaseTool abstract class."""

    def test_base_tool_cannot_be_instantiated(self):
        """Test that BaseTool cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseTool()

    def test_mock_tool_attributes(self):
        """Test MockTool has required attributes."""
        tool = MockTool()
        assert hasattr(tool, "name")
        assert hasattr(tool, "description")
        assert hasattr(tool, "input_schema")
        assert hasattr(tool, "display_name")

        assert tool.name == "mock_tool"
        assert tool.description == "A mock tool for testing"
        assert tool.input_schema == {"type": "object"}
        assert tool.display_name == "Mock Tool"

    def test_is_read_only_default(self):
        """Test is_read_only default behavior."""
        tool = MockTool()
        assert not tool.is_read_only()

    def test_is_read_only_override(self):
        """Test is_read_only can be overridden."""
        read_only_tool = MockTool(read_only=True)
        write_tool = MockTool(read_only=False)

        assert read_only_tool.is_read_only()
        assert not write_tool.is_read_only()

    @pytest.mark.asyncio
    async def test_should_confirm_execute(self):
        """Test should_confirm_execute method."""
        tool = MockTool()
        result = await tool.should_confirm_execute({"param": "value"})
        assert not result

    @pytest.mark.asyncio
    async def test_execute_method(self):
        """Test execute method."""
        tool = MockTool()
        result = await tool.execute({"param": "value"})

        assert isinstance(result, ToolResult)
        assert result.llm_content == "Mock result"
        assert result.user_display_content == "Mock display result"


class ConcreteConfirmationTool(BaseTool):
    """Concrete tool that requires confirmation."""

    def __init__(self):
        self.name = "confirmation_tool"
        self.description = "A tool that requires confirmation"
        self.input_schema = {"type": "object"}
        self.display_name = "Confirmation Tool"

    async def should_confirm_execute(self, tool_input):
        return ToolConfirmationDetails(
            type="edit", message="This will modify files. Continue?"
        )

    async def execute(self, tool_input):
        return ToolResult(
            llm_content="Confirmed execution result",
            user_display_content="Operation completed",
        )


class TestConcreteConfirmationTool:
    """Test concrete tool with confirmation."""

    @pytest.mark.asyncio
    async def test_confirmation_tool_should_confirm(self):
        """Test tool that requires confirmation."""
        tool = ConcreteConfirmationTool()
        confirmation = await tool.should_confirm_execute({"action": "modify"})

        assert isinstance(confirmation, ToolConfirmationDetails)
        assert confirmation.type == "edit"
        assert confirmation.message == "This will modify files. Continue?"

    @pytest.mark.asyncio
    async def test_confirmation_tool_execute(self):
        """Test confirmed tool execution."""
        tool = ConcreteConfirmationTool()
        result = await tool.execute({"action": "modify"})

        assert isinstance(result, ToolResult)
        assert result.llm_content == "Confirmed execution result"
        assert result.user_display_content == "Operation completed"


class TestToolIntegration:
    """Integration tests for tool classes."""

    @pytest.mark.asyncio
    async def test_full_tool_workflow(self):
        """Test complete tool workflow."""
        tool = ConcreteConfirmationTool()

        # Check if confirmation is needed
        confirmation = await tool.should_confirm_execute({"action": "test"})
        assert isinstance(confirmation, ToolConfirmationDetails)

        # Execute the tool (assuming confirmation was given)
        result = await tool.execute({"action": "test"})
        assert isinstance(result, ToolResult)
        assert result.llm_content == "Confirmed execution result"

    def test_tool_result_serialization(self):
        """Test ToolResult can be serialized."""
        result = ToolResult(
            llm_content="Serializable content", user_display_content="Display content"
        )

        # Should be able to convert to dict
        result_dict = result.model_dump()
        assert result_dict["llm_content"] == "Serializable content"
        assert result_dict["user_display_content"] == "Display content"

        # Should be able to recreate from dict
        recreated = ToolResult.model_validate(result_dict)
        assert recreated.llm_content == result.llm_content
        assert recreated.user_display_content == result.user_display_content
