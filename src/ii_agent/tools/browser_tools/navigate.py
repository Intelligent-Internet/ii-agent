import asyncio

from typing import Any, Optional
from playwright.async_api import TimeoutError
from ii_agent.browser.browser import Browser
from ii_agent.tools.base import ToolImplOutput
from ii_agent.tools.browser_tools import BrowserTool, utils
from ii_agent.llm.message_history import MessageHistory


class BrowserNavigationTool(BrowserTool):
    name = "browser_navigation"
    description = "Navigate browser to specified URL"
    input_schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Complete URL to visit. Must include protocol prefix.",
            }
        },
        "required": ["url"],
    }

    def __init__(self, browser: Browser):
        super().__init__(browser)

    async def _run(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        url = tool_input["url"]

        page = await self.browser.get_current_page()
        try:
            await page.goto(url, wait_until="domcontentloaded")
            await asyncio.sleep(1.5)
        except TimeoutError:
            msg = f"Timeout error navigating to {url}"
            return ToolImplOutput(msg, msg)
        except Exception:
            msg = f"Something went wrong while navigating to {url}; double check the URL and try again."
            return ToolImplOutput(msg, msg)

        state = await self.browser.update_state()
        state = await self.browser.handle_pdf_url_navigation()

        msg = f"Navigated to {url}"

        return utils.format_screenshot_tool_output(state.screenshot, msg)


class BrowserRestartTool(BrowserTool):
    name = "browser_restart"
    description = "Restart browser and navigate to specified URL"
    input_schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Complete URL to visit after restart. Must include protocol prefix.",
            }
        },
        "required": ["url"],
    }

    def __init__(self, browser: Browser):
        super().__init__(browser)

    async def _run(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        url = tool_input["url"]
        await self.browser.restart()

        page = await self.browser.get_current_page()
        try:
            await page.goto(url, wait_until="domcontentloaded")
            await asyncio.sleep(1.5)
        except TimeoutError:
            msg = f"Timeout error navigating to {url}"
            return ToolImplOutput(msg, msg)
        except Exception:
            msg = f"Something went wrong while navigating to {url}; double check the URL and try again."
            return ToolImplOutput(msg, msg)

        state = await self.browser.update_state()
        state = await self.browser.handle_pdf_url_navigation()

        msg = f"Navigated to {url}"

        return utils.format_screenshot_tool_output(state.screenshot, msg)
