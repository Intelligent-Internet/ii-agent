import asyncio

from typing import Any, Optional
from ii_agent.browser.browser import Browser
from ii_agent.tools.base import ToolImplOutput
from ii_agent.tools.browser_tools import BrowserTool, utils
from ii_agent.llm.message_history import MessageHistory


class BrowserWaitTool(BrowserTool):
    name = "browser_wait"
    description = """Wait for the current page to finish loading completely.\n\nUse this tool when:\n- A page is still loading after navigation\n- Waiting for dynamic content to appear\n- Ensuring all page elements are ready before interaction\n- After actions that trigger page updates or redirects\n- When you see loading indicators or partial content\n\nThis tool waits for:\n- Page DOM to be fully loaded\n- Essential resources to finish loading\n- JavaScript to complete initial execution\n\nTip: Use this tool before browser_view if the page seems to be still loading or changing."""
    input_schema = {"type": "object", "properties": {}, "required": []}

    def __init__(self, browser: Browser):
        super().__init__(browser)

    async def _run(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        await asyncio.sleep(1)
        state = await self.browser.update_state()
        state = await self.browser.handle_pdf_url_navigation()

        msg = "Waited for page"

        return utils.format_screenshot_tool_output(state.screenshot, msg)
