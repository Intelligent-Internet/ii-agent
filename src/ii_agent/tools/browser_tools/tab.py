import asyncio

from typing import Any, Optional
from ii_agent.browser.browser import Browser
from ii_agent.tools.base import ToolImplOutput
from ii_agent.tools.browser_tools import BrowserTool, utils
from ii_agent.llm.message_history import MessageHistory


class BrowserSwitchTabTool(BrowserTool):
    name = "browser_switch_tab"
    description = "Switch to a specific tab by tab index"
    input_schema = {
        "type": "object",
        "properties": {
            "index": {
                "type": "integer",
                "description": "Index of the tab to switch to.",
            }
        },
        "required": ["index"],
    }

    def __init__(self, browser: Browser):
        super().__init__(browser)

    async def _run(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        index = int(tool_input["index"])
        await self.browser.switch_to_tab(index)
        await asyncio.sleep(0.5)
        msg = f"Switched to tab {index}"
        state = await self.browser.update_state()

        return utils.format_screenshot_tool_output(state.screenshot, msg)


class BrowserOpenNewTabTool(BrowserTool):
    name = "browser_open_new_tab"
    description = "Open a new tab"
    input_schema = {"type": "object", "properties": {}, "required": []}

    def __init__(self, browser: Browser):
        super().__init__(browser)

    async def _run(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        await self.browser.create_new_tab()
        await asyncio.sleep(0.5)
        msg = "Opened a new tab"
        state = await self.browser.update_state()

        return utils.format_screenshot_tool_output(state.screenshot, msg)
