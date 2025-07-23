from ii_tool.tools.shell.terminal_manager import BaseShellManager
from ii_tool.tools.shell import ShellView
from ii_tool.tools.base import BaseTool, ToolResult

# Name
NAME = "BashList"
DISPLAY_NAME = "List bash sessions"

# Tool description
DESCRIPTION = "List all available bash sessions"

# Input schema
INPUT_SCHEMA = {
    "type": "object",
    "properties": {},
    "required": []
}

class ShellList(BaseTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = True

    def __init__(self, shell_manager: BaseShellManager) -> None:
        self.shell_manager = shell_manager

    async def execute(self) -> ToolResult:
        """List all available bash sessions."""
        all_current_sessions = self.shell_manager.get_all_sessions()
        
        result = f"Available sessions: {all_current_sessions}\n"
        result += f"For the detailed output of a session, use `{ShellView.name}`."

        return ToolResult(
            llm_content=result,
            is_error=False
        )

    async def execute_mcp_wrapper(self):
        return await self._mcp_wrapper()