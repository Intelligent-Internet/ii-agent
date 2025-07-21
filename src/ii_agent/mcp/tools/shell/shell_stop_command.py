from typing import Annotated
from pydantic import Field
from ii_agent.mcp.tools.shell.terminal_manager import BaseShellManager

class ShellStopCommand:
    name = "BashStop"
    description = "Stop a running command in a bash session by sending a SIGINT signal (Ctrl+C)."

    def __init__(self, BaseShellManager: BaseShellManager) -> None:
        self.shell_manager = BaseShellManager

    def run_impl(
        self,
        session_name: Annotated[str, Field(description="The name of the session to stop the command in.")],
    ):
        all_current_sessions = self.shell_manager.get_all_sessions()
        if session_name not in all_current_sessions:
            return f"Session '{session_name}' is not initialized. Available sessions: {all_current_sessions}"

        result = self.shell_manager.kill_current_command(session_name)
        return f"Current running command in session '{session_name}' stopped successfully. Current output:\n\n{result}"