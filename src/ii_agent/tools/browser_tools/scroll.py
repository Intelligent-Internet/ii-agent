import asyncio

from typing import Any, Optional
from ii_agent.tools.browser_tools import BrowserTool, utils
from ii_agent.browser.browser import Browser
from ii_agent.browser.utils import is_pdf_url
from ii_agent.tools.base import ToolImplOutput
from ii_agent.llm.message_history import MessageHistory


class BrowserScrollDownTool(BrowserTool):
    name = "browser_scroll_down"
    description = "Scroll down the current browser page"
    input_schema = {"type": "object", "properties": {}, "required": []}

    def __init__(self, browser: Browser):
        super().__init__(browser)

    async def _run(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
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
            return utils.format_screenshot_tool_output(state.screenshot, msg)
        except Exception as e:
            error_msg = f"Scroll down operation failed: {type(e).__name__}: {str(e)}"
            return ToolImplOutput(tool_output=error_msg, tool_result_message=error_msg)


class BrowserScrollUpTool(BrowserTool):
    name = "browser_scroll_up"
    description = "Scroll up the current browser page"
    input_schema = {"type": "object", "properties": {}, "required": []}

    def __init__(self, browser: Browser):
        super().__init__(browser)

    async def _run(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
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
            return utils.format_screenshot_tool_output(state.screenshot, msg)
        except Exception as e:
            error_msg = f"Scroll up operation failed: {type(e).__name__}: {str(e)}"
            return ToolImplOutput(tool_output=error_msg, tool_result_message=error_msg)
