import asyncio

from typing import Any, Optional
from ii_agent.browser.browser import Browser
from ii_agent.tools.base import ToolImplOutput
from ii_agent.tools.browser_tools import BrowserTool, utils
from ii_agent.llm.message_history import MessageHistory


class BrowserSwitchTabTool(BrowserTool):
    name = "browser_switch_tab"
    description = """Switch to a different browser tab by its index number.

Use this tool when:
- Multiple tabs are open and you need to switch between them
- Working with content across different websites
- Comparing information from multiple pages
- Managing multiple browser sessions

Important:
- Tab indices start at 0 (first tab is 0, second is 1, etc.)
- Use browser_view after switching to see the new tab's content
- Switching tabs doesn't close the previous tab
- Each tab maintains its own state and session

Note: If the specified tab index doesn't exist, an error will occur."""
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
    description = """Open a new browser tab.

Use this tool when:
- You need to visit multiple websites simultaneously
- Want to keep the current page open while exploring elsewhere
- Need to compare content across different websites
- Starting a new browsing session without losing current work

After opening:
- The new tab becomes the active tab
- Use browser_navigation to visit a URL in the new tab
- Use browser_switch_tab to return to previous tabs
- All tabs remain independent with their own state

Tip: Combine with browser_navigation to immediately go to a specific URL in the new tab."""
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
