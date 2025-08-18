import asyncio

from typing import Any, Optional
from ii_agent.browser.browser import Browser
from ii_agent.controller.state import State
from ii_tool.tools.base import BaseTool, ToolResult, ImageContent, TextContent, ToolConfirmationDetails
from ii_tool.tools.browser_tools.base import BrowserTool


class BrowserViewTool(BrowserTool):
    name = "browser_view_interactive_elements"
    display_name = 'browser view interactive elements'
    description = "Return the visible interactive elements on the current page"
    input_schema = {"type": "object", "properties": {}, "required": []}
    read_only = True

    def __init__(self, browser: Browser):
        super().__init__(browser)

    async def execute(
        self,
        tool_input: dict[str, Any],
    ) -> ToolResult:
        """Return the visible interactive elements on the current page."""
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

            return ToolResult(
                llm_content=[
                    ImageContent(
                        type='image',
                        data=state.screenshot_with_highlights,
                        mime_type="image/png"
                    ),
                    TextContent(
                        type='text',
                        text=msg
                    )
                ]
            )
        except Exception as e:
            error_msg = f"View interactive elements operation failed: {type(e).__name__}: {str(e)}"
            return ToolResult(llm_content=error_msg, is_error=True)

    def should_confirm_execute(self, tool_input: dict[str, Any]) -> ToolConfirmationDetails | bool:
        """
        Determine if the tool execution should be confirmed.
        In web application mode, the tool is executed without confirmation.
        In CLI mode, some tools should be confirmed by the user before execution (e.g. file edit, shell command, etc.)

        Args:
            tool_input (dict[str, Any]): The input to the tool.

        Returns:
            ToolConfirmationDetails | bool: The confirmation details or a boolean indicating if the execution should be confirmed.        
        """
        return False

    async def execute_mcp_wrapper(self):
        return await self._mcp_wrapper(tool_input={})