from typing import Any
from ii_tool.tools.shell.terminal_manager import BaseShellManager
from ii_tool.tools.base import BaseTool, ToolResult

# Name
NAME = "BashStop"
DISPLAY_NAME = "Stop bash command"

# Tool description
DESCRIPTION = "Stop a running command in a bash session by sending a SIGINT signal (Ctrl+C)."

# Input schema
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "session_name": {
            "type": "string",
            "description": "The name of the session to stop the command in."
        }
    },
    "required": ["session_name"]
}

class ShellStopCommand(BaseTool):
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
        """Stop a running command in the specified bash session."""
        session_name = tool_input.get("session_name")
        
        all_current_sessions = self.shell_manager.get_all_sessions()
        if session_name not in all_current_sessions:
            return ToolResult(
                llm_content=f"Session '{session_name}' is not initialized. Available sessions: {all_current_sessions}",
                is_error=True
            )

        result = self.shell_manager.kill_current_command(session_name)
        return ToolResult(
            llm_content=f"Current running command in session '{session_name}' stopped successfully. Current output:\n\n{result}",
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