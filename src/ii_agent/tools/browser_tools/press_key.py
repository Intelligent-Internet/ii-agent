import asyncio

from typing import Any, Optional
from ii_agent.browser.browser import Browser
from ii_agent.tools.base import ToolImplOutput
from ii_agent.tools.browser_tools import BrowserTool, utils
from ii_agent.llm.message_history import MessageHistory


class BrowserPressKeyTool(BrowserTool):
    name = "browser_press_key"
    description = "Simulate key press in the current browser page"
    input_schema = {
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": "Key name to simulate (e.g., Enter, Tab, ArrowUp), supports key combinations (e.g., Control+Enter).",
            }
        },
        "required": ["key"],
    }

    def __init__(self, browser: Browser):
        super().__init__(browser)

    async def _run(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        try:
            key = tool_input["key"]
            page = await self.browser.get_current_page()
            try:
                await page.keyboard.press(key)
                await asyncio.sleep(0.5)
            except Exception as e:
                return ToolImplOutput(
                    f"Failed to press key '{key}': {type(e).__name__}: {str(e)}",
                    f"Failed to press key '{key}': {type(e).__name__}: {str(e)}",
                    auxiliary_data={"success": False, "error": str(e)},
                )

            msg = f'Pressed "{key}" on the keyboard.'
            state = await self.browser.update_state()

            return utils.format_screenshot_tool_output(state.screenshot, msg)
        except Exception as e:
            return ToolImplOutput(
                f"Failed to press key: {type(e).__name__}: {str(e)}",
                "Failed to press key",
                auxiliary_data={"success": False, "error": str(e)},
            )
