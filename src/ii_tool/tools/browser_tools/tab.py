import asyncio

from typing import Any, Optional
from ii_agent.browser.browser import Browser
from ii_agent.controller.state import State
from ii_tool.tools.base import BaseTool, ToolResult, ImageContent, TextContent, ToolConfirmationDetails
from ii_tool.tools.browser_tools.base import BrowserTool


class BrowserSwitchTabTool(BrowserTool):
    name = "browser_switch_tab"
    display_name = 'browser switch tab'
    description = "Switch to a specific tab by tab index"
    input_schema = {
        "type": "object",
        "properties": {
            "index": {
                "type": "integer",
                "description": "Index of the tab to switch to.",
            }
        },
        "required": ["index"],
    }
    read_only = False

    def __init__(self, browser: Browser):
        super().__init__(browser)

    async def execute(
        self,
        tool_input: dict[str, Any],
    ) -> ToolResult:
        """Switch to a specific tab by tab index."""
        try:
            index = tool_input.get("index")
            if index is None:
                msg = "Must provide tab index to switch to"
                return ToolResult(
                    llm_content=msg,
                    is_error=True
                )
            index = int(index)
            
            await self.browser.switch_to_tab(index)
            await asyncio.sleep(0.5)
            msg = f"Switched to tab {index}"
            state = await self.browser.update_state()

            return ToolResult(
                llm_content=[
                    ImageContent(
                        type='image',
                        data=state.screenshot,
                        mime_type="image/png"
                    ),
                    TextContent(
                        type='text',
                        text=msg
                    )
                ]
            )
        except Exception as e:
            error_msg = f"Switch tab operation failed for tab {index}: {type(e).__name__}: {str(e)}"
            return ToolResult(llm_content=error_msg, is_error=True)

    def should_confirm_execute(self, tool_input: dict[str, Any]) -> ToolConfirmationDetails | bool:
        """
        Determine if the tool execution should be confirmed.
        In web application mode, the tool is executed without confirmation.
        In CLI mode, some tools should be confirmed by the user before execution (e.g. file edit, shell command, etc.)

        Args:
            tool_input (dict[str, Any]): The input to the tool.

        Returns:
            ToolConfirmationDetails | bool: The confirmation details or a boolean indicating if the execution should be confirmed.        
        """
        return False

    async def execute_mcp_wrapper(self, index):
        return await self._mcp_wrapper(
            tool_input={
                "index": index
            }
        )


class BrowserOpenNewTabTool(BrowserTool):
    name = "browser_open_new_tab"
    display_name = 'browser open new tab'
    description = "Open a new tab"
    input_schema = {"type": "object", "properties": {}, "required": []}
    read_only = False

    def __init__(self, browser: Browser):
        super().__init__(browser)

    async def execute(
        self,
        tool_input: dict[str, Any],
    ) -> ToolResult:
        """Open a new tab."""
        try:
            await self.browser.create_new_tab()
            await asyncio.sleep(0.5)
            msg = "Opened a new tab"
            state = await self.browser.update_state()

            return ToolResult(
                llm_content=[
                    ImageContent(
                        type='image',
                        data=state.screenshot,
                        mime_type="image/png"
                    ),
                    TextContent(
                        type='text',
                        text=msg
                    )
                ]
            )
        except Exception as e:
            error_msg = f"Open new tab operation failed: {type(e).__name__}: {str(e)}"
            return ToolResult(llm_content=error_msg, is_error=True)

    def should_confirm_execute(self, tool_input: dict[str, Any]) -> ToolConfirmationDetails | bool:
        """
        Determine if the tool execution should be confirmed.
        In web application mode, the tool is executed without confirmation.
        In CLI mode, some tools should be confirmed by the user before execution (e.g. file edit, shell command, etc.)

        Args:
            tool_input (dict[str, Any]): The input to the tool.

        Returns:
            ToolConfirmationDetails | bool: The confirmation details or a boolean indicating if the execution should be confirmed.        
        """
        return False

    async def execute_mcp_wrapper(self):
        return await self._mcp_wrapper(tool_input={})