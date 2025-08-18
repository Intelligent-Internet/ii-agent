import asyncio

from typing import Any, Optional
from ii_agent.browser.browser import Browser
from ii_agent.controller.state import State
from typing import Any
from ii_tool.core.config import ImageSearchConfig
from ii_tool.tools.base import BaseTool, ToolResult, ImageContent, TextContent, ToolConfirmationDetails
from ii_tool.tools.web.clients.image_search_client import create_image_search_client
from ii_tool.tools.browser_tools.base import BrowserTool


class BrowserClickTool(BrowserTool):
    name = "browser_click"
    display_name = 'browser click'
    description = "Click on an element on the current browser page"
    input_schema = {
        "type": "object",
        "properties": {
            "coordinate_x": {
                "type": "number",
                "description": "X coordinate of click position",
            },
            "coordinate_y": {
                "type": "number",
                "description": "Y coordinate of click position",
            },
        },
        "required": ["coordinate_x", "coordinate_y"],
    }
    read_only=False

    def __init__(self, browser: Browser):
        super().__init__(browser)

    async def execute(
        self,
        tool_input: dict[str, Any],
    ) -> ToolResult:
        """Initialize a bash session with the specified name and directory."""
        try:
            coordinate_x = tool_input.get("coordinate_x")
            coordinate_y = tool_input.get("coordinate_y")
            if coordinate_x is None or coordinate_y is None:
                msg = (
                    "Must provide both coordinate_x and coordinate_y to click on an element"
                )
                return ToolResult(
                    llm_content=msg,
                    is_error=True
                )
            page = await self.browser.get_current_page()
            initial_pages = len(self.browser.context.pages) if self.browser.context else 0

            await page.mouse.click(coordinate_x, coordinate_y)
            await asyncio.sleep(1)
            msg = f"Clicked at coordinates {coordinate_x}, {coordinate_y}"

            if self.browser.context and len(self.browser.context.pages) > initial_pages:
                new_tab_msg = "New tab opened - switching to it"
                msg += f" - {new_tab_msg}"
                await self.browser.switch_to_tab(-1)
                await asyncio.sleep(0.1)

            state = await self.browser.update_state()
            state = await self.browser.handle_pdf_url_navigation()
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
            error_msg = f"Click operation failed at ({coordinate_x}, {coordinate_y}): {type(e).__name__}: {str(e)}"
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


    async def execute_mcp_wrapper(self, coordinate_x, coordinate_y):
        return await self._mcp_wrapper(
            tool_input={
                "coordinate_x": coordinate_x,
                "coordinate_y": coordinate_y
            }
        )
