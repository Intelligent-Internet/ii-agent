import asyncio

from typing import Any, Optional
from ii_agent.tools.browser_tools import BrowserTool, utils
from ii_agent.browser.browser import Browser
from ii_agent.browser.utils import is_pdf_url
from ii_agent.tools.base import ToolImplOutput
from ii_agent.llm.message_history import MessageHistory


class BrowserScrollDownTool(BrowserTool):
    name = "browser_scroll_down"
    description = """Scroll down the current webpage to see more content below.

Use this tool when:
- Content extends below the visible area
- Looking for more elements or information
- The browser_view tool shows there's more content to explore
- Navigating through long pages or infinite scroll content

After scrolling:
- Use browser_view to see newly visible elements
- Some websites load content dynamically as you scroll
- Previously visible elements may scroll out of view

Note: Each scroll moves the page down by approximately one screen height."""
    input_schema = {"type": "object", "properties": {}, "required": []}

    def __init__(self, browser: Browser):
        super().__init__(browser)

    async def _run(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
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


class BrowserScrollUpTool(BrowserTool):
    name = "browser_scroll_up"
    description = """Scroll up the current webpage to see content above.

Use this tool when:
- You've scrolled down and need to go back up
- Looking for content that's now above the visible area
- Returning to the top of a page
- Accessing navigation or header elements

After scrolling:
- Use browser_view to see newly visible elements
- Previously visible elements may scroll out of view
- Some websites may reload or change content when scrolling up

Note: Each scroll moves the page up by approximately one screen height."""
    input_schema = {"type": "object", "properties": {}, "required": []}

    def __init__(self, browser: Browser):
        super().__init__(browser)

    async def _run(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
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
