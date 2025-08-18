import asyncio

from typing import Any, Optional
from ii_agent.browser.browser import Browser
from ii_agent.controller.state import State
from ii_tool.tools.base import BaseTool, ToolResult, ImageContent, TextContent, ToolConfirmationDetails
from ii_tool.tools.browser_tools.base import BrowserTool


class BrowserEnterTextTool(BrowserTool):
    name = "browser_enter_text"
    display_name = 'browser enter text'
    description = "Enter text with a keyboard. Use it AFTER you have clicked on an input element. This action will override the current text in the element."
    input_schema = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Text to enter with a keyboard."},
            "press_enter": {
                "type": "boolean",
                "description": "If True, `Enter` button will be pressed after entering the text. Use this when you think it would make sense to press `Enter` after entering the text, such as when you're submitting a form, performing a search, etc.",
            },
        },
        "required": ["text"],
    }
    read_only = False

    def __init__(self, browser: Browser):
        super().__init__(browser)

    async def execute(
        self,
        tool_input: dict[str, Any],
    ) -> ToolResult:
        """Enter text with a keyboard."""
        try:
            text = tool_input.get("text")
            if text is None:
                msg = "Must provide text to enter"
                return ToolResult(
                    llm_content=msg,
                    is_error=True
                )
            
            press_enter = tool_input.get("press_enter", False)

            page = await self.browser.get_current_page()
            await page.keyboard.press("ControlOrMeta+a")

            await asyncio.sleep(0.1)
            await page.keyboard.press("Backspace")
            await asyncio.sleep(0.1)

            await page.keyboard.type(text)

            if press_enter:
                await page.keyboard.press("Enter")
                await asyncio.sleep(2)

            msg = f'Entered "{text}" on the keyboard. Make sure to double check that the text was entered to where you intended.'
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
            error_msg = f"Enter text operation failed: {type(e).__name__}: {str(e)}"
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

    async def execute_mcp_wrapper(self, text, press_enter=False):
        return await self._mcp_wrapper(
            tool_input={
                "text": text,
                "press_enter": press_enter
            }
        )