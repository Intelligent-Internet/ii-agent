import asyncio

from typing import Any, Optional
from ii_agent.browser.browser import Browser
from ii_agent.tools.base import ToolImplOutput
from ii_agent.tools.browser_tools import BrowserTool, utils
from ii_agent.llm.message_history import MessageHistory


class BrowserPressKeyTool(BrowserTool):
    name = "browser_press_key"
    description = """Simulate keyboard key presses in the browser.\n\nUse this tool for:\n- Pressing special keys (Enter, Tab, Escape, Arrow keys)\n- Keyboard shortcuts (Ctrl+C, Ctrl+V, Ctrl+F)\n- Navigation keys (Page Up, Page Down, Home, End)\n- Function keys and other special key combinations\n\nCommon use cases:\n- Press Enter to submit forms or confirm actions\n- Use Tab to navigate between form fields\n- Press Escape to close modals or cancel operations\n- Use arrow keys for navigation in interactive elements\n- Ctrl+F to open browser search\n\nSupported keys:\n- Enter, Tab, Escape, Space\n- Arrow keys (ArrowUp, ArrowDown, ArrowLeft, ArrowRight)\n- Page navigation (PageUp, PageDown, Home, End)\n- Modifier combinations (Ctrl+key, Alt+key, Shift+key)\n\nNote: For typing regular text, use browser_enter_text instead."""
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
        key = tool_input["key"]
        page = await self.browser.get_current_page()
        try:
            await page.keyboard.press(key)
            await asyncio.sleep(0.5)
        except Exception as e:
            return ToolImplOutput(
                f"Failed to press key: {e}",
                f"Failed to press key",
                auxiliary_data={"success": False, "error": str(e)},
            )

        msg = f'Pressed "{key}" on the keyboard.'
        state = await self.browser.update_state()

        return utils.format_screenshot_tool_output(state.screenshot, msg)
