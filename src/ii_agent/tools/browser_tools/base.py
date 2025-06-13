import asyncio

from typing import Any, Optional
from ii_agent.tools.base import (
    LLMTool,
    ToolImplOutput,
)
from ii_agent.browser.browser import Browser
from ii_agent.llm.message_history import MessageHistory


def get_event_loop():
    try:
        # Try to get the existing event loop
        loop = asyncio.get_event_loop()
    except RuntimeError:
        # If no event loop exists, create a new one
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop


class BrowserTool(LLMTool):
    def __init__(self, browser: Browser):
        self.browser = browser

    async def _run(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        raise NotImplementedError("Subclasses must implement this method")

    async def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        try:
            return await self._run(tool_input, message_history)
        except Exception as e:
            error_msg = f"Browser operation failed: {type(e).__name__}: {str(e)}"
            if hasattr(self, 'name'):
                error_msg = f"{self.name} failed: {type(e).__name__}: {str(e)}"
            return ToolImplOutput(
                tool_output=error_msg,
                tool_result_message=error_msg
            )
