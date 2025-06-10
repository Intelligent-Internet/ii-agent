from typing import Any, Optional
from ii_agent.browser.browser import Browser
from ii_agent.tools.base import ToolImplOutput
from ii_agent.tools.browser_tools import BrowserTool, utils
from ii_agent.llm.message_history import MessageHistory


class BrowserViewTool(BrowserTool):
    name = "browser_view_interactive_elements"
    description = """Get all visible and interactive elements on the current webpage for analysis and interaction.\n\nThis is your primary tool for understanding what's available on a webpage. It provides a structured view of all elements you can interact with.\n\nUse this tool to:\n- See what's currently visible on the page\n- Identify buttons, links, form fields, and other interactive elements\n- Get element IDs needed for clicking, typing, or other interactions\n- Understand the page structure and layout\n- Find specific elements by their text content or labels\n\nReturns:\n- Screenshots of the current page state\n- Numbered list of all interactive elements\n- Element types (button, link, input, select, etc.)\n- Element text content and descriptions\n- Element coordinates and IDs for interaction\n\nAlways use this tool first when visiting a new page to understand what actions you can take.\n\nNote: Only returns elements that are currently visible on screen. Use scrolling tools to see more content."""
    input_schema = {"type": "object", "properties": {}, "required": []}

    def __init__(self, browser: Browser):
        super().__init__(browser)

    async def _run(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        state = await self.browser.update_state()

        highlighted_elements = "<highlighted_elements>\n"
        if state.interactive_elements:
            for element in state.interactive_elements.values():
                start_tag = f"[{element.index}]<{element.tag_name}"

                if element.input_type:
                    start_tag += f' type="{element.input_type}"'

                start_tag += ">"
                element_text = element.text.replace("\n", " ")
                highlighted_elements += (
                    f"{start_tag}{element_text}</{element.tag_name}>\n"
                )
        highlighted_elements += "</highlighted_elements>"

        msg = f"""Current URL: {state.url}

Current viewport information:
{highlighted_elements}"""

        return utils.format_screenshot_tool_output(
            state.screenshot_with_highlights, msg
        )
