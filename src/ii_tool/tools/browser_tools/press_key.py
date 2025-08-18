import asyncio

from typing import Any, Optional
from ii_agent.browser.browser import Browser
from ii_agent.controller.state import State
from ii_tool.tools.base import BaseTool, ToolResult, ImageContent, TextContent, ToolConfirmationDetails
from ii_tool.tools.browser_tools.base import BrowserTool


class BrowserPressKeyTool(BrowserTool):
    name = "browser_press_key"
    display_name = 'browser press key'
    description = "Simulate key press in the current browser page"
    input_schema = {
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": "Key name to simulate (e.g., Enter, Tab, ArrowUp), supports key combinations (e.g., Control+Enter).",
            }
        },
        "required": ["key"],
    }
    read_only = False

    def __init__(self, browser: Browser):
        super().__init__(browser)

    async def execute(
        self,
        tool_input: dict[str, Any],
    ) -> ToolResult:
        """Simulate key press in the current browser page."""
        try:
            key = tool_input.get("key")
            if not key:
                msg = "Must provide key to press"
                return ToolResult(
                    llm_content=msg,
                    is_error=True
                )
                
            page = await self.browser.get_current_page()
            try:
                await page.keyboard.press(key)
                await asyncio.sleep(0.5)
            except Exception as e:
                msg = f"Failed to press key '{key}': {type(e).__name__}: {str(e)}"
                return ToolResult(llm_content=msg, is_error=True)

            msg = f'Pressed "{key}" on the keyboard.'
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
            error_msg = f"Failed to press key: {type(e).__name__}: {str(e)}"
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

    async def execute_mcp_wrapper(self, key):
        return await self._mcp_wrapper(
            tool_input={
                "key": key
            }
        )