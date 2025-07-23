from typing import List
from ii_tool.tools.shell.terminal_manager import BaseShellManager
from ii_tool.tools.base import BaseTool, ToolResult

# Name
NAME = "BashView"
DISPLAY_NAME = "View bash session output"

# Tool description
DESCRIPTION = "View the current output of bash sessions."

# Input schema
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "session_names": {
            "type": "array",
            "items": {"type": "string"},
            "description": "An array of session names to view the output of."
        }
    },
    "required": ["session_names"]
}

class ShellView(BaseTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = True

    def __init__(self, shell_manager: BaseShellManager) -> None:
        self.shell_manager = shell_manager

    async def execute(
        self,
        session_names: List[str],
    ) -> ToolResult:
        """View the current output of the specified bash sessions."""
        all_current_sessions = self.shell_manager.get_all_sessions()
        for session_name in session_names:
            if session_name not in all_current_sessions:
                return ToolResult(
                    llm_content=f"Session '{session_name}' is not initialized. Available sessions: {all_current_sessions}",
                    is_error=True
                )

        result = f"Current output of:\n\n"
        for session_name in session_names:
            result += f"Session: {session_name}\n{self.shell_manager.get_session_output(session_name)}\n"
            result += "---\n"
        
        return ToolResult(
            llm_content=result,
            is_error=False
        )

    async def execute_mcp_wrapper(
        self,
        session_names: List[str],
    ):
        return await self._mcp_wrapper(session_names)