import asyncio

from typing import Any, Optional
from ii_agent.browser.browser import Browser
from ii_agent.browser.utils import is_pdf_url
from ii_agent.controller.state import State
from ii_tool.tools.base import BaseTool, ToolResult, ImageContent, TextContent, ToolConfirmationDetails
from ii_tool.tools.browser_tools.base import BrowserTool


class BrowserScrollDownTool(BrowserTool):
    name = "browser_scroll_down"
    display_name = 'browser scroll down'
    description = "Scroll down the current browser page"
    input_schema = {"type": "object", "properties": {}, "required": []}
    read_only = False

    def __init__(self, browser: Browser):
        super().__init__(browser)

    async def execute(
        self,
        tool_input: dict[str, Any],
    ) -> ToolResult:
        """Scroll down the current browser page."""
        try:
            page = await self.browser.get_current_page()
            state = self.browser.get_state()
            is_pdf = is_pdf_url(page.url)
            if is_pdf:
                await page.keyboard.press("PageDown")
                await asyncio.sleep(0.1)
            else:
                await page.mouse.move(state.viewport.width / 2, state.viewport.height / 2)
                await asyncio.sleep(0.1)
                await page.mouse.wheel(0, state.viewport.height * 0.8)
                await asyncio.sleep(0.1)

            state = await self.browser.update_state()

            msg = "Scrolled page down"
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
            error_msg = f"Scroll down operation failed: {type(e).__name__}: {str(e)}"
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


class BrowserScrollUpTool(BrowserTool):
    name = "browser_scroll_up"
    display_name = 'browser scroll up'
    description = "Scroll up the current browser page"
    input_schema = {"type": "object", "properties": {}, "required": []}
    read_only = False

    def __init__(self, browser: Browser):
        super().__init__(browser)

    async def execute(
        self,
        tool_input: dict[str, Any],
    ) -> ToolResult:
        """Scroll up the current browser page."""
        try:
            page = await self.browser.get_current_page()
            state = self.browser.get_state()
            is_pdf = is_pdf_url(page.url)
            if is_pdf:
                await page.keyboard.press("PageUp")
                await asyncio.sleep(0.1)
            else:
                await page.mouse.move(state.viewport.width / 2, state.viewport.height / 2)
                await asyncio.sleep(0.1)
                await page.mouse.wheel(0, -state.viewport.height * 0.8)
                await asyncio.sleep(0.1)

            state = await self.browser.update_state()

            msg = "Scrolled page up"
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
            error_msg = f"Scroll up operation failed: {type(e).__name__}: {str(e)}"
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