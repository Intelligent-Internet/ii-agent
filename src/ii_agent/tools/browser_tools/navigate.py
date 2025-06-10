import asyncio

from typing import Any, Optional
from playwright.async_api import TimeoutError
from ii_agent.browser.browser import Browser
from ii_agent.tools.base import ToolImplOutput
from ii_agent.tools.browser_tools import BrowserTool, utils
from ii_agent.llm.message_history import MessageHistory


class BrowserNavigationTool(BrowserTool):
    name = "browser_navigation"
    description = """Navigate the browser to a specific webpage URL.

Use this tool to visit any website or webpage. Essential for web browsing tasks.

Important:
- Must include full URL with protocol (http:// or https://)
- Waits for page to load before returning
- Will report timeout or navigation errors if they occur

Example URLs:
- https://www.example.com
- https://docs.python.org
- https://github.com/user/repo

After navigation, use browser_view to see the page content and available interactions."""
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
    description = """Restart the browser and navigate to a fresh page.\n\nUse this tool when the browser is in an unresponsive state or when you need a clean session.\n\nUse cases:\n- Browser becomes unresponsive or stuck\n- Need to clear all cookies, session data, and cache\n- Website has JavaScript errors preventing normal operation\n- Starting a completely fresh browsing session\n- After encountering persistent loading issues\n\nThis tool:\n1. Closes the current browser instance\n2. Starts a new browser session\n3. Navigates to the specified URL\n\nNote: All previous tabs, session data, and login states will be lost."""
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
