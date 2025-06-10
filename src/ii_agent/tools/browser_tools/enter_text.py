import asyncio

from typing import Any, Optional
from ii_agent.browser.browser import Browser
from ii_agent.tools.base import ToolImplOutput
from ii_agent.tools.browser_tools import BrowserTool, utils
from ii_agent.llm.message_history import MessageHistory


class BrowserEnterTextTool(BrowserTool):
    name = "browser_enter_text"
    description = """Type text into input fields, text areas, or other text-accepting elements.\n\nIMPORTANT WORKFLOW:\n1. First use browser_view_interactive_elements to find input fields\n2. Click on the input field using browser_click\n3. Then use this tool to enter text\n\nUse this tool for:\n- Filling out forms (name, email, password fields)\n- Entering search queries in search boxes\n- Typing content into text areas or comment boxes\n- Entering data into any text input field\n\nBehavior:\n- Completely replaces any existing text in the field\n- Does not append to existing text\n- Simulates keyboard typing\n- Works with various input types (text, email, password, search, etc.)\n\nTips:\n- Always click the input field first to focus it\n- Use \\n for line breaks in text areas\n- For sensitive data like passwords, the text will be masked in logs\n- Some fields may have validation that triggers after typing"""
    input_schema = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Text to enter with a keyboard."},
            "press_enter": {
                "type": "boolean",
                "description": "If True, `Enter` button will be pressed after entering the text. Use this when you think it would make sense to press `Enter` after entering the text, such as when you're submitting a form, performing a search, etc.",
            },
        },
        "required": ["text"],
    }

    def __init__(self, browser: Browser):
        super().__init__(browser)

    async def _run(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        text = tool_input["text"]
        press_enter = tool_input.get("press_enter", False)

        page = await self.browser.get_current_page()
        await page.keyboard.press("ControlOrMeta+a")

        await asyncio.sleep(0.1)
        await page.keyboard.press("Backspace")
        await asyncio.sleep(0.1)

        await page.keyboard.type(text)

        if press_enter:
            await page.keyboard.press("Enter")
            await asyncio.sleep(2)

        msg = f'Entered "{text}" on the keyboard. Make sure to double check that the text was entered to where you intended.'
        state = await self.browser.update_state()

        return utils.format_screenshot_tool_output(state.screenshot, msg)
