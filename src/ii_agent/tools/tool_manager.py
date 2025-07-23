import asyncio
import logging
from fastmcp import Client
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from ii_agent.llm.base import LLMClient
from ii_agent.tools.base import BaseTool, ToolResult
from ii_agent.utils import WorkspaceManager
from ii_agent.utils.concurrent_execution import should_run_concurrently
from ii_agent.core.storage.models.settings import Settings
from ii_agent.core.logger import logger
from ii_agent.tools.mcp_tool import MCPTool
from ii_agent.tools.web_search_tool import WebSearchTool
from ii_agent.tools.web_visit_tool import WebVisitTool
from ii_agent.tools.web_dev_tool import FullStackInitTool


class ToolCallParameters(BaseModel):
    tool_call_id: str
    tool_name: str
    tool_input: Any


def get_system_tools(
    client: LLMClient,
    workspace_manager: WorkspaceManager,
    settings: Settings,
    container_id: Optional[str] = None,
    tool_args: Optional[Dict[str, Any]] = None,
) -> list[BaseTool]:
    """
    Retrieves a list of all system tools.

    Returns:
        list[BaseTool]: A list of all system tools.
    """

    # TODO: Add more tools here
    return [
        WebSearchTool(settings=settings),
        WebVisitTool(settings=settings),
        FullStackInitTool(workspace_manager=workspace_manager),
    ]


class AgentToolManager:
    """
    Manages the creation and execution of tools for the agent.

    This class is responsible for:
    - Initializing and managing all available tools
    - Providing access to tools by name
    - Executing tools with appropriate inputs
    - Logging tool execution details

    Tools include bash commands, browser interactions, file operations,
    search capabilities, and task completion functionality.
    """

    def __init__(
        self,
        tools: List[BaseTool],
        logger_for_agent_logs: logging.Logger,
        interactive_mode: bool = True,
        reviewer_mode: bool = False,
    ):
        self.tools = tools

    async def register_tools(self, tools: List[BaseTool]):
        self.tools.extend(tools)

    async def register_mcp_tools(
        self,
        mcp_config: Dict[str, Any] | None = None,
        mcp_client: Client | None = None,
        trust: bool = False,
    ):
        if not mcp_config and not mcp_client:
            raise ValueError("Either mcp_config or client must be provided")
        if mcp_config:
            mcp_client = Client(mcp_config)

        async with mcp_client:
            mcp_tools = await mcp_client.list_tools()
            for tool in mcp_tools:
                assert tool.description is not None, (
                    f"Tool {tool.name} has no description"
                )
                tool_annotations = tool.annotations
                self.tools.append(
                    MCPTool(
                        name=tool.name,
                        description=tool.description,
                        input_schema=tool.inputSchema,
                        mcp_client=mcp_client,
                        annotations=tool_annotations,
                        trust=trust,
                    )
                )

    def _validate_tool_parameters(self):
        """Validate tool parameters and check for duplicates."""
        tool_names = [tool.name for tool in self.tools]
        sorted_names = sorted(tool_names)
        for i in range(len(sorted_names) - 1):
            if sorted_names[i] == sorted_names[i + 1]:
                raise ValueError(f"Tool {sorted_names[i]} is duplicated")

    def get_tool(self, tool_name: str) -> BaseTool:
        """
        Retrieves a tool by its name.

        Args:
            tool_name (str): The name of the tool to retrieve.

        Returns:
            BaseTool: The tool object corresponding to the given name.

        Raises:
            ValueError: If the tool with the specified name is not found.
        """
        try:
            tool: BaseTool = next(t for t in self.get_tools() if t.name == tool_name)
            return tool
        except StopIteration:
            raise ValueError(f"Tool with name {tool_name} not found")

    async def run_tool(self, tool_call: ToolCallParameters) -> ToolResult:
        """
        Executes a llm tool asynchronously.

        Args:
            tool_params (ToolCallParameters): The tool parameters.
            history (State): The history of the conversation.
        Returns:
            ToolResult: The result of the tool execution.
        """
        tool_name = tool_call.tool_name
        tool_input = tool_call.tool_input
        llm_tool = self.get_tool(tool_name)
        logger.debug(f"Running tool: {tool_name}")
        logger.debug(f"Tool input: {tool_input}")
        tool_result = await llm_tool.execute(tool_input)

        user_display_content = tool_result.user_display_content

        tool_input_str = "\n".join([f" - {k}: {v}" for k, v in tool_input.items()])

        log_message = f"Calling tool {tool_name} with input:\n{tool_input_str}"
        log_message += f"\nTool output:\n{user_display_content}"

        logger.debug(log_message)

        return tool_result

    async def run_tools_batch(
        self, tool_calls: List[ToolCallParameters]
    ) -> List[ToolResult]:
        """
        Execute multiple tools either concurrently or serially based on their read-only status.

        Args:
            tool_calls: List of tool call parameters

        Returns:
            List of tool results in the same order as input tool_calls
        """
        if not tool_calls:
            return []

        if len(tool_calls) == 1:
            # Single tool - just execute normally
            result = await self.run_tool(tool_calls[0])
            return [result]

        # Determine execution strategy based on read-only status
        if should_run_concurrently(tool_calls, self):
            logger.info(f"Running {len(tool_calls)} tools concurrently (all read-only)")
            return await self._run_tools_concurrently(tool_calls)
        else:
            logger.info(
                f"Running {len(tool_calls)} tools serially (contains non-read-only tools)"
            )
            return await self._run_tools_serially(tool_calls)

    async def _run_tools_concurrently(
        self, tool_calls: List[ToolCallParameters]
    ) -> List[ToolResult]:
        """Execute tools concurrently and return results in order."""

        # Create tasks for each tool with proper concurrency limits
        async def run_single_tool(tool_call: ToolCallParameters) -> ToolResult:
            """Wrapper for single tool execution."""
            result = await self.run_tool(tool_call)
            return result

        # Create tasks for all tools with concurrency limit
        from ii_agent.utils.concurrent_execution import MAX_TOOL_CONCURRENCY

        if len(tool_calls) <= MAX_TOOL_CONCURRENCY:
            # All tools can run concurrently
            tasks = [asyncio.create_task(run_single_tool(tc)) for tc in tool_calls]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        else:
            # Use semaphore to limit concurrency
            semaphore = asyncio.Semaphore(MAX_TOOL_CONCURRENCY)

            async def limited_run_tool(tool_call: ToolCallParameters) -> ToolResult:
                async with semaphore:
                    return await run_single_tool(tool_call)

            tasks = [asyncio.create_task(limited_run_tool(tc)) for tc in tool_calls]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle any exceptions and maintain order
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                error_msg = (
                    f"Error executing tool {tool_calls[i].tool_name}: {str(result)}"
                )
                logger.error(error_msg)
                final_results.append(error_msg)
            else:
                final_results.append(result)

        return final_results

    async def _run_tools_serially(
        self, tool_calls: List[ToolCallParameters]
    ) -> List[ToolResult]:
        """Execute tools serially and return results in order."""
        results = []
        for tool_call in tool_calls:
            try:
                result = await self.run_tool(tool_call)
                results.append(result)
            except Exception as e:
                error_msg = f"Error executing tool {tool_call.tool_name}: {str(e)}"
                logger.error(error_msg)
                results.append(error_msg)
        return results

    def get_tools(self) -> List[BaseTool]:
        """
        Returns the list of tools.
        """
        return self.tools
