import asyncio

from typing import Any, Optional
from ii_agent.browser.browser import Browser
from ii_agent.tools.base import ToolImplOutput
from ii_agent.tools.browser_tools import BrowserTool, utils
from ii_agent.llm.message_history import MessageHistory


class BrowserWaitTool(BrowserTool):
    name = "browser_wait"
    description = "Wait for the page to load"
    input_schema = {"type": "object", "properties": {}, "required": []}

    def __init__(self, browser: Browser):
        super().__init__(browser)

    async def _run(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        try:
            await asyncio.sleep(1)
            state = await self.browser.update_state()
            state = await self.browser.handle_pdf_url_navigation()

            msg = "Waited for page"

            return utils.format_screenshot_tool_output(state.screenshot, msg)
        except Exception as e:
            error_msg = f"Wait operation failed: {type(e).__name__}: {str(e)}"
            return ToolImplOutput(tool_output=error_msg, tool_result_message=error_msg)
