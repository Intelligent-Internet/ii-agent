import asyncio

from typing import Any, Optional
from ii_agent.browser.browser import Browser
from ii_agent.tools.base import ToolImplOutput
from ii_agent.tools.browser_tools import BrowserTool, utils
from ii_agent.llm.message_history import MessageHistory


class BrowserEnterTextTool(BrowserTool):
    name = "browser_enter_text"
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

    def __init__(self, browser: Browser):
        super().__init__(browser)

    async def _run(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        try:
            text = tool_input["text"]
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

            return utils.format_screenshot_tool_output(state.screenshot, msg)
        except Exception as e:
            error_msg = f"Enter text operation failed: {type(e).__name__}: {str(e)}"
            return ToolImplOutput(tool_output=error_msg, tool_result_message=error_msg)
