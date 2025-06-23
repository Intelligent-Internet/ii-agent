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
            },
            "console": {
                "type": "boolean",
                "description": "If True, return console logs for debugging."
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
        try:
            url = tool_input["url"]
            try:
                await self.browser.goto(url)
            except TimeoutError:
                msg = f"Timeout error navigating to {url}"
                return ToolImplOutput(msg, msg)
            except Exception as e:
                msg = f"Navigation failed to {url}: {type(e).__name__}: {str(e)}"
                return ToolImplOutput(msg, msg)

            state = await self.browser.update_state()
            state = await self.browser.handle_pdf_url_navigation()

            msg = f"Navigated to {url}"
            
            console = tool_input.get("console", False)
            logs = utils.get_console_logs(self.browser, console)
            return utils.format_screenshot_tool_output(state.screenshot, msg, logs)
        except Exception as e:
            error_msg = f"Navigation operation failed: {type(e).__name__}: {str(e)}"
            return ToolImplOutput(tool_output=error_msg, tool_result_message=error_msg)


class BrowserRestartTool(BrowserTool):
    name = "browser_restart"
    description = "Restart browser and navigate to specified URL"
    input_schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Complete URL to visit after restart. Must include protocol prefix.",
            },
            "console": {
                "type": "boolean",
                "description": "If True, return console logs for debugging."
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
        try:
            url = tool_input["url"]
            await self.browser.restart()
            
            try:
                await self.browser.goto(url)
            except TimeoutError:
                msg = f"Timeout error navigating to {url}"
                return ToolImplOutput(msg, msg)
            except Exception as e:
                msg = f"Navigation failed to {url}: {type(e).__name__}: {str(e)}"
                return ToolImplOutput(msg, msg)

            state = await self.browser.update_state()
            state = await self.browser.handle_pdf_url_navigation()

            msg = f"Navigated to {url}"
            
            console = tool_input.get("console", False)
            logs = utils.get_console_logs(self.browser, console)
            return utils.format_screenshot_tool_output(state.screenshot, msg, logs)
        except Exception as e:
            error_msg = f"Browser restart and navigation failed: {type(e).__name__}: {str(e)}"
            return ToolImplOutput(tool_output=error_msg, tool_result_message=error_msg)
