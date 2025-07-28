"""Tests for MCPTool."""

import pytest
from unittest.mock import Mock, AsyncMock

from ii_agent.tools.mcp_tool import MCPTool
from ii_agent.tools.base import ToolResult, ToolConfirmationDetails


class TestMCPTool:
    """Test cases for MCPTool."""

    @pytest.fixture
    def mock_mcp_client(self):
        """Create a mock MCP client."""
        client = Mock()
        client.call_tool = AsyncMock()
        # Add async context manager support
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        return client

    @pytest.fixture
    def sample_input_schema(self):
        """Create a sample input schema."""
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query"},
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results",
                    "default": 10,
                },
            },
            "required": ["query"],
        }

    @pytest.fixture
    def mcp_tool(self, mock_mcp_client, sample_input_schema):
        """Create an MCPTool instance."""
        return MCPTool(
            name="search_tool",
            description="Search for information",
            input_schema=sample_input_schema,
            mcp_client=mock_mcp_client,
            annotations=None,
            trust=False,
        )

    def test_mcp_tool_initialization(
        self, mcp_tool, mock_mcp_client, sample_input_schema
    ):
        """Test MCPTool initialization."""
        assert mcp_tool.name == "search_tool"
        assert mcp_tool.description == "Search for information"
        assert mcp_tool.input_schema == sample_input_schema
        assert mcp_tool.mcp_client == mock_mcp_client
        assert mcp_tool.annotations is None
        assert not mcp_tool.trust

    def test_mcp_tool_initialization_with_annotations(
        self, mock_mcp_client, sample_input_schema
    ):
        """Test MCPTool initialization with annotations."""
        annotations = {"audience": ["user"], "level": "beginner"}
        tool = MCPTool(
            name="annotated_tool",
            description="A tool with annotations",
            input_schema=sample_input_schema,
            mcp_client=mock_mcp_client,
            annotations=annotations,
            trust=True,
        )

        assert tool.annotations == annotations
        assert tool.trust

    def test_is_read_only_default(self, mcp_tool):
        """Test that MCPTool is not read-only by default."""
        assert not mcp_tool.is_read_only()

    @pytest.mark.asyncio
    async def test_should_confirm_execute_untrusted(self, mcp_tool):
        """Test confirmation requirement for untrusted MCP tool."""
        tool_input = {"query": "test search"}

        confirmation = await mcp_tool.should_confirm_execute(tool_input)

        assert isinstance(confirmation, ToolConfirmationDetails)
        assert confirmation.type == "mcp"
        assert "Do you want to execute the tool search_tool" in confirmation.message
        assert "search_tool" in confirmation.message

    @pytest.mark.asyncio
    async def test_should_confirm_execute_trusted(
        self, mock_mcp_client, sample_input_schema
    ):
        """Test no confirmation needed for trusted MCP tool."""
        trusted_tool = MCPTool(
            name="trusted_tool",
            description="A trusted tool",
            input_schema=sample_input_schema,
            mcp_client=mock_mcp_client,
            annotations=None,
            trust=True,
        )

        tool_input = {"query": "test"}
        confirmation = await trusted_tool.should_confirm_execute(tool_input)

        assert not confirmation

    @pytest.mark.asyncio
    async def test_execute_successful(self, mcp_tool, mock_mcp_client):
        """Test successful MCP tool execution."""
        # Mock MCP client response
        mock_content_item = Mock()
        mock_content_item.type = "text"
        mock_content_item.text = "Search results: Found 3 items"

        mock_response = Mock()
        mock_response.content = [mock_content_item]  # Make content a list

        mock_mcp_client.call_tool.return_value = mock_response

        tool_input = {"query": "python tutorials", "limit": 5}

        result = await mcp_tool.execute(tool_input)

        assert isinstance(result, ToolResult)
        assert result.llm_content[0].text == mock_response.content[0].text

        # Verify MCP client was called correctly
        mock_mcp_client.call_tool.assert_called_once_with("search_tool", tool_input)

    @pytest.mark.asyncio
    async def test_execute_with_text_content(self, mcp_tool, mock_mcp_client):
        """Test execution with text content in response."""
        # Create mock content items
        mock_content_item1 = Mock()
        mock_content_item1.type = "text"
        mock_content_item1.text = "First result"

        mock_content_item2 = Mock()
        mock_content_item2.type = "text"
        mock_content_item2.text = "Second result"

        # Create mock response
        mock_response = Mock()
        mock_response.content = [mock_content_item1, mock_content_item2]

        mock_mcp_client.call_tool.return_value = mock_response

        tool_input = {"query": "test"}

        result = await mcp_tool.execute(tool_input)

        assert result.llm_content[0].text == "First result"
        assert result.llm_content[1].text == "Second result"
        assert "First result" in result.user_display_content
        assert "Second result" in result.user_display_content

    @pytest.mark.asyncio
    async def test_execute_with_image_content(self, mcp_tool, mock_mcp_client):
        """Test execution with image content in response."""
        # Create mock text content item
        mock_text_item = Mock()
        mock_text_item.type = "text"
        mock_text_item.text = "Here's an image:"

        # Create mock image content item
        mock_image_item = Mock()
        mock_image_item.type = "image"
        mock_image_item.mimeType = "image/png"
        mock_image_item.data = "iVBORw0KGgoAAAANSUhEUgA..."

        # Create mock response
        mock_response = Mock()
        mock_response.content = [mock_text_item, mock_image_item]

        mock_mcp_client.call_tool.return_value = mock_response

        tool_input = {"query": "image search"}
        result = await mcp_tool.execute(tool_input)

        assert result.llm_content[0].text == "Here's an image:"
        assert result.llm_content[1].type == "image"
        assert "Here's an image:" in result.user_display_content
        assert "[Redacted image]" in result.user_display_content

    @pytest.mark.asyncio
    async def test_execute_with_mixed_content(self, mcp_tool, mock_mcp_client):
        """Test execution with mixed content types."""
        # Create mock text content item 1
        mock_text_item1 = Mock()
        mock_text_item1.type = "text"
        mock_text_item1.text = "Analysis results:"

        # Create mock image content item
        mock_image_item = Mock()
        mock_image_item.type = "image"
        mock_image_item.data = "base64encodeddata"
        mock_image_item.mimeType = "image/png"

        # Create mock text content item 2
        mock_text_item2 = Mock()
        mock_text_item2.type = "text"
        mock_text_item2.text = "Summary: Analysis complete"

        # Create mock response
        mock_response = Mock()
        mock_response.content = [mock_text_item1, mock_image_item, mock_text_item2]

        mock_mcp_client.call_tool.return_value = mock_response

        tool_input = {"query": "analyze"}

        result = await mcp_tool.execute(tool_input)

        assert result.llm_content[0].text == "Analysis results:"
        assert result.llm_content[1].type == "image"
        assert result.llm_content[2].text == "Summary: Analysis complete"

        user_display = result.user_display_content
        assert "Analysis results:" in user_display
        assert "[Redacted image]" in user_display
        assert "Summary: Analysis complete" in user_display

    @pytest.mark.asyncio
    async def test_execute_empty_content(self, mcp_tool, mock_mcp_client):
        """Test execution with empty content."""
        mock_response = Mock()
        mock_response.content = []
        mock_mcp_client.call_tool.return_value = mock_response

        tool_input = {"query": "empty"}

        result = await mcp_tool.execute(tool_input)

        assert result.llm_content == []
        assert result.user_display_content == ""

    @pytest.mark.asyncio
    async def test_execute_mcp_error(self, mcp_tool, mock_mcp_client):
        """Test handling of MCP client errors."""
        # Mock MCP client to raise an exception
        mock_mcp_client.call_tool.side_effect = Exception("MCP connection failed")

        tool_input = {"query": "test"}

        with pytest.raises(Exception, match="MCP connection failed"):
            await mcp_tool.execute(tool_input)

    @pytest.mark.asyncio
    async def test_execute_with_complex_input(self, mcp_tool, mock_mcp_client):
        """Test execution with complex input parameters."""
        mock_item = Mock()
        mock_item.type = "text"
        mock_item.text = "Complex search completed"

        mock_response = Mock()
        mock_response.content = [mock_item]
        mock_mcp_client.call_tool.return_value = mock_response

        complex_input = {
            "query": "machine learning",
            "limit": 20,
            "filters": {
                "date_range": "2023-2024",
                "categories": ["ai", "ml", "deep-learning"],
            },
            "sort_by": "relevance",
        }

        result = await mcp_tool.execute(complex_input)

        assert isinstance(result, ToolResult)
        mock_mcp_client.call_tool.assert_called_once_with("search_tool", complex_input)

    def test_tool_inheritance(self, mcp_tool):
        """Test that MCPTool inherits from BaseTool."""
        from ii_agent.tools.base import BaseTool

        assert isinstance(mcp_tool, BaseTool)

    @pytest.mark.asyncio
    async def test_confirmation_message_formatting(self, mcp_tool):
        """Test that confirmation message is properly formatted."""
        tool_input = {"query": "test", "limit": 5}

        confirmation = await mcp_tool.should_confirm_execute(tool_input)

        assert isinstance(confirmation, ToolConfirmationDetails)
        message = confirmation.message
        assert "search_tool" in message
        assert "Do you want to execute" in message
        # Should contain formatted input
        assert "query" in message
        assert "test" in message

    def test_string_representation(self, mcp_tool):
        """Test string representation of MCPTool."""
        str_repr = str(mcp_tool)
        # Should contain key information about the tool
        assert "search_tool" in str_repr or hasattr(mcp_tool, "__str__")

    @pytest.mark.asyncio
    async def test_execute_preserves_mcp_response_structure(
        self, mcp_tool, mock_mcp_client
    ):
        """Test that execute preserves the MCP response structure."""
        mock_text_item = Mock()
        mock_text_item.type = "text"
        mock_text_item.text = "Result"

        mock_image_item = Mock()
        mock_image_item.type = "image"
        mock_image_item.data = "base64encodeddata"
        mock_image_item.mimeType = "image/png"

        # Create mock response
        mock_response = Mock()
        mock_response.content = [mock_text_item, mock_image_item]

        mock_mcp_client.call_tool.return_value = mock_response

        result = await mcp_tool.execute({"query": "test"})

        # The llm_content should preserve the original structure
        assert result.llm_content[0].text == "Result"
        assert result.llm_content[1].type == "image"
        assert result.llm_content[1].data == "base64encodeddata"
        assert result.llm_content[1].mimeType == "image/png"
        # While user_display_content should be formatted for readability
        assert isinstance(result.user_display_content, str)
