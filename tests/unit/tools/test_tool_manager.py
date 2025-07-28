"""Tests for AgentToolManager."""

import pytest
from unittest.mock import Mock, AsyncMock, patch

from ii_agent.tools.tool_manager import AgentToolManager, ToolCallParameters
from ii_agent.tools.base import BaseTool, ToolResult


class MockTool(BaseTool):
    """Mock tool for testing."""

    def __init__(self, name="mock_tool", read_only=False, should_fail=False):
        self.name = name
        self.description = f"Mock tool {name}"
        self.input_schema = {"type": "object"}
        self.read_only = read_only
        self._should_fail = should_fail

    async def execute(self, tool_input):
        if self._should_fail:
            raise Exception(f"Mock tool {self.name} failed")
        return ToolResult(
            llm_content=f"Result from {self.name}",
            user_display_content=f"Display result from {self.name}",
        )

    async def should_confirm_execute(self, tool_input):
        """Whether the tool should be confirmed by the user before execution."""
        return False


class TestAgentToolManager:
    """Test cases for AgentToolManager."""

    def test_init(self):
        """Test AgentToolManager initialization."""
        manager = AgentToolManager()
        assert manager.tools == []

    def test_register_tools(self):
        """Test registering tools."""
        manager = AgentToolManager()
        tools = [MockTool("tool1"), MockTool("tool2")]

        manager.register_tools(tools)

        assert len(manager.tools) == 2
        assert manager.tools[0].name == "tool1"
        assert manager.tools[1].name == "tool2"

    def test_register_duplicate_tools_raises_error(self):
        """Test that registering duplicate tools raises error."""
        manager = AgentToolManager()
        tools = [MockTool("duplicate"), MockTool("duplicate")]

        with pytest.raises(ValueError, match="Tool duplicate is duplicated"):
            manager.register_tools(tools)

    def test_get_tool_success(self):
        """Test getting a tool by name."""
        manager = AgentToolManager()
        tool = MockTool("test_tool")
        manager.register_tools([tool])

        retrieved_tool = manager.get_tool("test_tool")
        assert retrieved_tool is tool

    def test_get_tool_not_found(self):
        """Test getting a non-existent tool."""
        manager = AgentToolManager()

        with pytest.raises(ValueError, match="Tool with name nonexistent not found"):
            manager.get_tool("nonexistent")

    def test_get_tools(self):
        """Test getting all tools."""
        manager = AgentToolManager()
        tools = [MockTool("tool1"), MockTool("tool2")]
        manager.register_tools(tools)

        all_tools = manager.get_tools()
        assert len(all_tools) == 2
        assert all_tools == tools

    @pytest.mark.asyncio
    async def test_run_tool_success(self):
        """Test running a tool successfully."""
        manager = AgentToolManager()
        tool = MockTool("test_tool")
        manager.register_tools([tool])

        tool_call = ToolCallParameters(
            tool_call_id="call_123",
            tool_name="test_tool",
            tool_input={"param": "value"},
        )

        result = await manager.run_tool(tool_call)

        assert isinstance(result, ToolResult)
        assert result.llm_content == "Result from test_tool"
        assert result.user_display_content == "Display result from test_tool"

    @pytest.mark.asyncio
    async def test_run_tool_failure(self):
        """Test running a tool that fails."""
        manager = AgentToolManager()
        tool = MockTool("failing_tool", should_fail=True)
        manager.register_tools([tool])

        tool_call = ToolCallParameters(
            tool_call_id="call_123", tool_name="failing_tool", tool_input={}
        )

        with pytest.raises(Exception, match="Mock tool failing_tool failed"):
            await manager.run_tool(tool_call)

    @pytest.mark.asyncio
    async def test_run_tool_nonexistent(self):
        """Test running a non-existent tool."""
        manager = AgentToolManager()

        tool_call = ToolCallParameters(
            tool_call_id="call_123", tool_name="nonexistent", tool_input={}
        )

        with pytest.raises(ValueError, match="Tool with name nonexistent not found"):
            await manager.run_tool(tool_call)

    @pytest.mark.asyncio
    async def test_run_tools_batch_empty(self):
        """Test running empty batch of tools."""
        manager = AgentToolManager()

        results = await manager.run_tools_batch([])
        assert results == []

    @pytest.mark.asyncio
    async def test_run_tools_batch_single(self):
        """Test running single tool in batch."""
        manager = AgentToolManager()
        tool = MockTool("test_tool")
        manager.register_tools([tool])

        tool_call = ToolCallParameters(
            tool_call_id="call_123", tool_name="test_tool", tool_input={}
        )

        results = await manager.run_tools_batch([tool_call])

        assert len(results) == 1
        assert isinstance(results[0], ToolResult)

    @pytest.mark.asyncio
    async def test_run_tools_batch_concurrent_read_only(self):
        """Test running multiple read-only tools concurrently."""
        manager = AgentToolManager()
        tools = [
            MockTool("read_tool1", read_only=True),
            MockTool("read_tool2", read_only=True),
        ]
        manager.register_tools(tools)

        tool_calls = [
            ToolCallParameters(
                tool_call_id="call_1", tool_name="read_tool1", tool_input={}
            ),
            ToolCallParameters(
                tool_call_id="call_2", tool_name="read_tool2", tool_input={}
            ),
        ]

        with patch(
            "ii_agent.tools.tool_manager.should_run_concurrently", return_value=True
        ):
            results = await manager.run_tools_batch(tool_calls)

        assert len(results) == 2
        assert all(isinstance(r, ToolResult) for r in results)

    @pytest.mark.asyncio
    async def test_run_tools_batch_serial_write_tools(self):
        """Test running write tools serially."""
        manager = AgentToolManager()
        tools = [
            MockTool("write_tool1", read_only=False),
            MockTool("write_tool2", read_only=False),
        ]
        manager.register_tools(tools)

        tool_calls = [
            ToolCallParameters(
                tool_call_id="call_1", tool_name="write_tool1", tool_input={}
            ),
            ToolCallParameters(
                tool_call_id="call_2", tool_name="write_tool2", tool_input={}
            ),
        ]

        with patch(
            "ii_agent.tools.tool_manager.should_run_concurrently", return_value=False
        ):
            results = await manager.run_tools_batch(tool_calls)

        assert len(results) == 2
        assert all(isinstance(r, ToolResult) for r in results)

    @pytest.mark.asyncio
    async def test_run_tools_batch_concurrent_with_failure(self):
        """Test concurrent tool execution with one failure."""
        manager = AgentToolManager()
        tools = [
            MockTool("working_tool", read_only=True),
            MockTool("failing_tool", read_only=True, should_fail=True),
        ]
        manager.register_tools(tools)

        tool_calls = [
            ToolCallParameters(
                tool_call_id="call_1", tool_name="working_tool", tool_input={}
            ),
            ToolCallParameters(
                tool_call_id="call_2", tool_name="failing_tool", tool_input={}
            ),
        ]

        with patch(
            "ii_agent.tools.tool_manager.should_run_concurrently", return_value=True
        ):
            results = await manager.run_tools_batch(tool_calls)

        assert len(results) == 2
        assert isinstance(results[0], ToolResult)  # Working tool result
        assert isinstance(results[1], str)  # Error message

    @pytest.mark.asyncio
    async def test_run_tools_batch_serial_with_failure(self):
        """Test serial tool execution with one failure."""
        manager = AgentToolManager()
        tools = [MockTool("working_tool"), MockTool("failing_tool", should_fail=True)]
        manager.register_tools(tools)

        tool_calls = [
            ToolCallParameters(
                tool_call_id="call_1", tool_name="working_tool", tool_input={}
            ),
            ToolCallParameters(
                tool_call_id="call_2", tool_name="failing_tool", tool_input={}
            ),
        ]

        with patch(
            "ii_agent.tools.tool_manager.should_run_concurrently", return_value=False
        ):
            results = await manager.run_tools_batch(tool_calls)

        assert len(results) == 2
        assert isinstance(results[0], ToolResult)  # Working tool result
        assert isinstance(results[1], str)  # Error message

    @pytest.mark.asyncio
    async def test_run_tools_concurrent_with_concurrency_limit(self):
        """Test concurrent execution with concurrency limit."""
        manager = AgentToolManager()
        tools = [MockTool(f"tool_{i}", read_only=True) for i in range(10)]
        manager.register_tools(tools)

        tool_calls = [
            ToolCallParameters(
                tool_call_id=f"call_{i}", tool_name=f"tool_{i}", tool_input={}
            )
            for i in range(10)
        ]

        with patch(
            "ii_agent.tools.tool_manager.should_run_concurrently", return_value=True
        ):
            results = await manager.run_tools_batch(tool_calls)

        assert len(results) == 10
        assert all(isinstance(r, ToolResult) for r in results)

    @pytest.mark.asyncio
    async def test_register_mcp_tools(self):
        """Test registering MCP tools."""
        manager = AgentToolManager()

        # Mock MCP client and tools
        mock_client = AsyncMock()
        mock_tool_info = Mock()
        mock_tool_info.name = "mcp_tool"
        mock_tool_info.description = "MCP test tool"
        mock_tool_info.inputSchema = {"type": "object"}
        mock_tool_info.annotations = None

        mock_client.list_tools.return_value = [mock_tool_info]

        await manager.register_mcp_tools(mock_client, trust=False)

        assert len(manager.tools) == 1
        assert manager.tools[0].name == "mcp_tool"
        mock_client.list_tools.assert_called_once()

    @pytest.mark.asyncio
    async def test_register_mcp_tools_no_description_raises_error(self):
        """Test that MCP tools without description raise error."""
        manager = AgentToolManager()

        mock_client = AsyncMock()
        mock_tool_info = Mock()
        mock_tool_info.name = "bad_tool"
        mock_tool_info.description = None  # No description
        mock_tool_info.inputSchema = {"type": "object"}

        mock_client.list_tools.return_value = [mock_tool_info]

        with pytest.raises(AssertionError, match="Tool bad_tool has no description"):
            await manager.register_mcp_tools(mock_client)

    def test_validate_tool_parameters_success(self):
        """Test successful tool parameter validation."""
        manager = AgentToolManager()
        tools = [MockTool("tool1"), MockTool("tool2")]

        # Should not raise any exception
        manager.register_tools(tools)

    def test_validate_tool_parameters_with_duplicates(self):
        """Test tool parameter validation with duplicates."""
        manager = AgentToolManager()

        # Manually add tools to bypass register_tools validation
        manager.tools = [MockTool("duplicate"), MockTool("duplicate")]

        with pytest.raises(ValueError, match="Tool duplicate is duplicated"):
            manager._validate_tool_parameters()
