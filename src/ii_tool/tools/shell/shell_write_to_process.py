from typing import Any
from ii_tool.tools.shell.terminal_manager import BaseShellManager, ShellCommandTimeoutError, ShellBusyError
from ii_tool.tools.base import BaseTool, ToolResult, ToolConfirmationDetails


NAME = "BashWriteToProcess"
DISPLAY_NAME = "Bash Write to Process"
DESCRIPTION = "Write to a process in a specified shell session. Use for interacting with running processes."
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "session_name": {
            "type": "string",
            "description": "The name of the session to write to."
        },
        "content": {
            "type": "string",
            "description": "The text to write to the process.",
        },
        "press_enter": {
            "type": "boolean",
            "description": "Whether to press enter after writing the text.",
            "default": True
        },
    },
    "required": ["session_name", "content", "press_enter"],
}


class ShellWriteToProcess(BaseTool):
    """Tool for writing to a process in a shell session"""
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = False

    def __init__(self, shell_manager: BaseShellManager) -> None:
        self.shell_manager = shell_manager
    
    def should_confirm_execute(self, tool_input: dict[str, Any]) -> ToolConfirmationDetails | bool:
        return ToolConfirmationDetails(
            type="bash",
            message=f"Write {tool_input['content']} to process in session {tool_input['session_name']}"
        )

    async def execute(
        self,
        tool_input: dict[str, Any],
    ) -> ToolResult:
        session_name = tool_input["session_name"]
        content = tool_input["content"]
        press_enter = tool_input["press_enter"]

        all_current_sessions = self.shell_manager.get_all_sessions()
        if session_name not in all_current_sessions:
            return ToolResult(
                llm_content=f"Session '{session_name}' is not initialized. Available sessions: {all_current_sessions}",
                is_error=True
            )

        result = self.shell_manager.write_to_process(session_name, content, press_enter)
        return ToolResult(
            llm_content=result,
            user_display_content=result,
            is_error=False
        )

    async def execute_mcp_wrapper(
        self,
        session_name: str,
        content: str,
        press_enter: bool = True,
    ):
        return await self._mcp_wrapper(
            tool_input={
                "session_name": session_name,
                "content": content,
                "press_enter": press_enter,
            }
        )