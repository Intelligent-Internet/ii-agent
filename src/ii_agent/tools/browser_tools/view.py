from typing import Any, Optional
from ii_agent.browser.browser import Browser
from ii_agent.tools.base import ToolImplOutput
from ii_agent.tools.browser_tools import BrowserTool, utils
from ii_agent.llm.message_history import MessageHistory


class BrowserViewTool(BrowserTool):
    name = "browser_view_interactive_elements"
    description = "Return the visible interactive elements on the current page"
    input_schema = {"type": "object", "properties": {}, "required": []}

    def __init__(self, browser: Browser):
        super().__init__(browser)

    async def _run(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        try:
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
        except Exception as e:
            error_msg = f"View interactive elements operation failed: {type(e).__name__}: {str(e)}"
            return ToolImplOutput(tool_output=error_msg, tool_result_message=error_msg)
