import asyncio
from typing import Callable, Coroutine

from attr import dataclass
from pydantic import BaseModel
from typing import List, Any, Optional
from ii_agent.core.logger import logger
from ii_tool.tools.base import BaseTool, ToolResult


MAX_TOOL_CONCURRENCY = 10

# Default timeout for individual tool execution (seconds).
# Browser ops typically finish in <10s; long-running tools (bash compilation)
# can override via a `timeout` attribute on the tool class.
DEFAULT_TOOL_EXECUTION_TIMEOUT = 120

# How often to poll for agent interruption during tool execution (seconds).
INTERRUPT_POLL_INTERVAL = 2


class ToolCallParameters(BaseModel):
    tool_call_id: str
    tool_name: str
    tool_input: Any


@dataclass
class AgentToolManager:
    """
    Manages the registration and execution of tools for the agent.

    This class is responsible for:
    - Initializing and managing all available tools
    - Providing access to tools by name
    - Executing tools with appropriate inputs
    - Logging tool execution details

    Tools include bash commands, browser interactions, file operations,
    search capabilities, and task completion functionality.
    """

    tools: Optional[List[BaseTool]] = None

    def register_tools(self, tools: list[BaseTool]):
        if self.tools is None:
            self.tools = []
        self.tools.extend(tools)
        self._validate_tool_parameters()

    def _validate_tool_parameters(self):
        """Validate tool parameters and check for duplicates."""
        tool_names = [tool.name for tool in self.tools]
        sorted_names = sorted(tool_names)
        for i in range(len(sorted_names) - 1):
            if sorted_names[i] == sorted_names[i + 1]:
                raise ValueError(f"Tool {sorted_names[i]} is duplicated")

    def _should_run_concurrently(self, tool_params: list[ToolCallParameters]) -> bool:
        """
        Determine if tools should run concurrently based on read-only status.

        Tools run concurrently ONLY if ALL tools are read-only.

        Args:
            tools: List of tool call parameters
            tool_manager: Tool manager instance to look up tools

        Returns:
            True if all tools are read-only, False otherwise
        """
        try:
            for tool_call in tool_params:
                tool = self.get_tool(tool_call.tool_name)
                if not tool.is_read_only():
                    return False
            return True
        except Exception:
            # If we can't determine read-only status, err on the side of caution
            return False

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
        try:
            llm_tool = self.get_tool(tool_name)
        except ValueError as e:
            logger.warning(f"Tool lookup failed: {str(e)}")
            return ToolResult(
                llm_content=f"Tool '{tool_name}' is not available: {str(e)}",
                user_display_content=f"Tool '{tool_name}' is not available",
                is_error=True
            )
        except Exception as e:
            logger.error(f"Unexpected error when getting tool '{tool_name}': {str(e)}")
            return ToolResult(
                llm_content=f"Error accessing tool '{tool_name}': {str(e)}",
                user_display_content=f"Tool '{tool_name}' is not available",
                is_error=True
            )

        logger.debug(f"Running tool: {tool_name}")
        logger.debug(f"Tool input: {tool_input}")

        # Use per-tool timeout if defined, otherwise the global default.
        timeout = getattr(llm_tool, 'timeout', DEFAULT_TOOL_EXECUTION_TIMEOUT)

        try:
            tool_result = await asyncio.wait_for(
                llm_tool.execute(tool_input),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            timeout_msg = (
                f"Tool '{tool_name}' timed out after {timeout}s. "
                f"The operation was cancelled but the browser is still running. "
                f"Use browser_wait to take a fresh screenshot and assess current state."
            )
            logger.warning(timeout_msg)
            return ToolResult(
                llm_content=timeout_msg,
                user_display_content=f"Tool '{tool_name}' timed out after {timeout}s",
                is_error=True,
            )

        user_display_content = tool_result.user_display_content

        tool_input_str = "\n".join([f" - {k}: {v}" for k, v in tool_input.items()])

        log_message = f"Calling tool {tool_name} with input:\n{tool_input_str}"
        log_message += f"\nTool output:\n{user_display_content}"

        logger.debug(log_message)

        return tool_result

    async def run_tools_batch(
        self,
        tool_calls: List[ToolCallParameters],
        interrupt_check: Optional[Callable[[], Coroutine[Any, Any, bool]]] = None,
    ) -> List[ToolResult]:
        """
        Execute multiple tools either concurrently or serially based on their read-only status.

        Args:
            tool_calls: List of tool call parameters
            interrupt_check: Optional async callable that returns True if the agent
                has been interrupted (e.g. user pressed cancel). When provided,
                the interrupt is polled during tool execution so that long-running
                tools can be cancelled without waiting for the full timeout.

        Returns:
            List of tool results in the same order as input tool_calls
        """
        if not tool_calls:
            return []

        if len(tool_calls) == 1:
            # Single tool - execute with interrupt monitoring if available
            result = await self._run_tool_with_interrupt(
                tool_calls[0], interrupt_check
            )
            return [result]

        # Determine execution strategy based on read-only status
        if self._should_run_concurrently(tool_calls):
            logger.info(f"Running {len(tool_calls)} tools concurrently (all read-only)")
            return await self._run_tools_concurrently(tool_calls)
        else:
            logger.info(
                f"Running {len(tool_calls)} tools serially (contains non-read-only tools)"
            )
            return await self._run_tools_serially(
                tool_calls, interrupt_check
            )

    async def _run_tools_concurrently(
        self, tool_calls: List[ToolCallParameters]
    ) -> List[ToolResult]:
        """Execute tools concurrently and return results in order."""

        # Create tasks for each tool with proper concurrency limits
        async def run_single_tool(tool_call: ToolCallParameters) -> ToolResult:
            """Wrapper for single tool execution."""
            result = await self.run_tool(tool_call)
            return result

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

    async def _run_tool_with_interrupt(
        self,
        tool_call: ToolCallParameters,
        interrupt_check: Optional[Callable[[], Coroutine[Any, Any, bool]]] = None,
    ) -> ToolResult:
        """Execute a single tool while polling for interruption.

        The tool execution runs as an asyncio task.  If *interrupt_check* is
        provided it is polled every ``INTERRUPT_POLL_INTERVAL`` seconds.  When
        an interruption is detected the task is cancelled and an interrupted
        ToolResult is returned immediately.
        """
        task = asyncio.create_task(self.run_tool(tool_call))

        if interrupt_check is None:
            return await task

        while not task.done():
            try:
                # Wait a short interval, then poll for interruption
                return await asyncio.wait_for(
                    asyncio.shield(task), timeout=INTERRUPT_POLL_INTERVAL
                )
            except asyncio.TimeoutError:
                # Task still running – check for interruption
                try:
                    if await interrupt_check():
                        logger.info(
                            f"Interruption detected during tool '{tool_call.tool_name}', cancelling"
                        )
                        task.cancel()
                        try:
                            await task
                        except (asyncio.CancelledError, Exception):
                            pass
                        return ToolResult(
                            llm_content="Tool execution was interrupted by user.",
                            user_display_content="Tool execution interrupted",
                            is_interrupted=True,
                        )
                except Exception as exc:
                    logger.warning(f"Interrupt check failed: {exc}")

        return task.result()

    async def _run_tools_serially(
        self,
        tool_calls: List[ToolCallParameters],
        interrupt_check: Optional[Callable[[], Coroutine[Any, Any, bool]]] = None,
    ) -> List[ToolResult]:
        """Execute tools serially and return results in order."""
        results = []
        for tool_call in tool_calls:
            try:
                result = await self._run_tool_with_interrupt(
                    tool_call, interrupt_check
                )
                if result.is_interrupted:
                    results.append(result)
                    # Fill remaining tools with interrupt results
                    for remaining in tool_calls[len(results):]:
                        results.append(
                            ToolResult(
                                llm_content="Tool execution was interrupted by user.",
                                user_display_content="Tool execution interrupted",
                                is_interrupted=True,
                            )
                        )
                    break
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
