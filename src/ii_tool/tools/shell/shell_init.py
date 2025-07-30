from typing import Optional, Any
from ii_tool.tools.shell.terminal_manager import BaseShellManager, ShellInvalidSessionNameError, TmuxSessionExists
from ii_tool.core.workspace import WorkspaceManager, FileSystemValidationError
from ii_tool.tools.base import BaseTool, ToolResult

# Name
NAME = "BashInit"
DISPLAY_NAME = "Initialize bash session"

# Tool description
DESCRIPTION = "Initialize a bash session with a given name and start directory. Use this before running any commands in the session."

# Input schema
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "session_name": {
            "type": "string",
            "description": "The name of the session to initialize."
        },
        "start_directory": {
            "type": "string",
            "description": "The absolute path to a directory to start the session in. If not provided, the session will start in the workspace directory."
        }
    },
    "required": ["session_name"]
}

class ShellInit(BaseTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = False
    
    def __init__(self, shell_manager: BaseShellManager, workspace_manager: WorkspaceManager) -> None:
        self.shell_manager = shell_manager
        self.workspace_manager = workspace_manager

    async def execute(
        self,
        tool_input: dict[str, Any],
    ) -> ToolResult:
        """Initialize a bash session with the specified name and directory."""
        session_name = tool_input.get("session_name")
        start_directory = tool_input.get("start_directory")
        
        try:
            if session_name in self.shell_manager.get_all_sessions():
                return ToolResult(
                    llm_content=f"Session '{session_name}' already exists",
                    is_error=True
                )

            if not start_directory:
                start_directory = str(self.workspace_manager.get_workspace_path())

            self.workspace_manager.validate_existing_directory_path(start_directory)
            
            self.shell_manager.create_session(session_name, start_directory)
            return ToolResult(
                llm_content=f"Session '{session_name}' initialized successfully at start directory `{start_directory}`",
                is_error=False
            )
        except (
            FileSystemValidationError,
            ShellInvalidSessionNameError,
            TmuxSessionExists,
        ) as e:
            return ToolResult(
                llm_content=f"Error initializing session: {e}",
                is_error=True
            )

    async def execute_mcp_wrapper(
        self,
        session_name: str,
        start_directory: Optional[str] = None,
    ):
        return await self._mcp_wrapper(
            tool_input={
                "session_name": session_name,
                "start_directory": start_directory,
            }
        )