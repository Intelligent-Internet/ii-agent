import asyncio

from typing import Any, Optional
from ii_agent.browser.browser import Browser
from ii_agent.controller.state import State
from ii_tool.tools.base import BaseTool, ToolResult, ImageContent, TextContent, ToolConfirmationDetails
from ii_tool.tools.browser_tools.base import BrowserTool


class BrowserWaitTool(BrowserTool):
    name = "browser_wait"
    display_name = 'browser wait'
    description = "Wait for the page to load"
    input_schema = {"type": "object", "properties": {}, "required": []}
    read_only = False

    def __init__(self, browser: Browser):
        super().__init__(browser)

    async def execute(
        self,
        tool_input: dict[str, Any],
    ) -> ToolResult:
        """Wait for the page to load."""
        try:
            await asyncio.sleep(1)
            state = await self.browser.update_state()
            state = await self.browser.handle_pdf_url_navigation()

            msg = "Waited for page"

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
            error_msg = f"Wait operation failed: {type(e).__name__}: {str(e)}"
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