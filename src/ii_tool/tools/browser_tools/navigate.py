import asyncio

from typing import Any, Optional
from playwright.async_api import TimeoutError
from ii_agent.browser.browser import Browser
from ii_agent.controller.state import State
from ii_tool.tools.base import BaseTool, ToolResult, ImageContent, TextContent, ToolConfirmationDetails
from ii_tool.tools.browser_tools.base import BrowserTool


class BrowserNavigationTool(BrowserTool):
    name = "browser_navigation"
    display_name = 'browser navigation'
    description = "Navigate browser to specified URL"
    input_schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Complete URL to visit. Must include protocol prefix.",
            }
        },
        "required": ["url"],
    }
    read_only = False

    def __init__(self, browser: Browser):
        super().__init__(browser)

    async def execute(
        self,
        tool_input: dict[str, Any],
    ) -> ToolResult:
        """Navigate browser to specified URL."""
        try:
            url = tool_input.get("url")
            if not url:
                msg = "Must provide URL to navigate to"
                return ToolResult(
                    llm_content=msg,
                    is_error=True
                )

            page = await self.browser.get_current_page()
            try:
                await page.goto(url, wait_until="domcontentloaded")
                await asyncio.sleep(1.5)
            except TimeoutError:
                msg = f"Timeout error navigating to {url}"
                return ToolResult(llm_content=msg, is_error=True)
            except Exception as e:
                msg = f"Navigation failed to {url}: {type(e).__name__}: {str(e)}"
                return ToolResult(llm_content=msg, is_error=True)

            state = await self.browser.update_state()
            state = await self.browser.handle_pdf_url_navigation()

            msg = f"Navigated to {url}"

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
            error_msg = f"Navigation operation failed: {type(e).__name__}: {str(e)}"
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

    async def execute_mcp_wrapper(self, url):
        return await self._mcp_wrapper(
            tool_input={
                "url": url
            }
        )


class BrowserRestartTool(BrowserTool):
    name = "browser_restart"
    display_name = 'browser restart'
    description = "Restart browser and navigate to specified URL"
    input_schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Complete URL to visit after restart. Must include protocol prefix.",
            }
        },
        "required": ["url"],
    }
    read_only = False

    def __init__(self, browser: Browser):
        super().__init__(browser)

    async def execute(
        self,
        tool_input: dict[str, Any],
    ) -> ToolResult:
        """Restart browser and navigate to specified URL."""
        try:
            url = tool_input.get("url")
            if not url:
                msg = "Must provide URL to navigate to after restart"
                return ToolResult(
                    llm_content=msg,
                    is_error=True
                )
                
            await self.browser.restart()

            page = await self.browser.get_current_page()
            try:
                await page.goto(url, wait_until="domcontentloaded")
                await asyncio.sleep(1.5)
            except TimeoutError:
                msg = f"Timeout error navigating to {url}"
                return ToolResult(llm_content=msg, is_error=True)
            except Exception as e:
                msg = f"Navigation failed to {url}: {type(e).__name__}: {str(e)}"
                return ToolResult(llm_content=msg, is_error=True)

            state = await self.browser.update_state()
            state = await self.browser.handle_pdf_url_navigation()

            msg = f"Browser restarted and navigated to {url}"

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
            error_msg = f"Browser restart and navigation failed: {type(e).__name__}: {str(e)}"
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

    async def execute_mcp_wrapper(self, url):
        return await self._mcp_wrapper(
            tool_input={
                "url": url
            }
        )