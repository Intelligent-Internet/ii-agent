from typing import Any
from ii_tool.tools.shell.terminal_manager import BaseShellManager
from ii_tool.tools.base import BaseTool, ToolResult

# Name
NAME = "BashKill"
DISPLAY_NAME = "Kill bash session"

# Tool description
DESCRIPTION = "Kill a bash session by name"

# Input schema
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "session_name": {
            "type": "string",
            "description": "The name of the session to kill."
        }
    },
    "required": ["session_name"]
}

class ShellKill(BaseTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = False

    def __init__(self, shell_manager: BaseShellManager) -> None:
        self.shell_manager = shell_manager

    async def execute(
        self,
        tool_input: dict[str, Any],
    ) -> ToolResult:
        """Kill the specified bash session."""
        session_name = tool_input.get("session_name")
        
        all_current_sessions = self.shell_manager.get_all_sessions()
        if session_name not in all_current_sessions:
            return ToolResult(
                llm_content=f"Session '{session_name}' is not available. Available sessions: {all_current_sessions}",
                is_error=True
            )

        self.shell_manager.delete_session(session_name)
        return ToolResult(
            llm_content=f"Session '{session_name}' killed successfully.",
            is_error=False
        )

    async def execute_mcp_wrapper(
        self,
        session_name: str,
    ):
        return await self._mcp_wrapper(
            tool_input={
                "session_name": session_name,
            }
        )