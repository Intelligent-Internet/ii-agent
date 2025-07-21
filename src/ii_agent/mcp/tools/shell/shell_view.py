from typing import Annotated, List
from pydantic import Field
from ii_agent.mcp.tools.shell.terminal_manager import BaseShellManager

DEFAULT_TIMEOUT = 60

class ShellView:
    name = "BashView"
    description = "View the current output of bash sessions."

    def __init__(self, BaseShellManager: BaseShellManager) -> None:
        self.shell_manager = BaseShellManager

    def run_impl(
        self,
        session_names: Annotated[List[str], Field(description="An array of session names to view the output of.")],
    ):
        all_current_sessions = self.shell_manager.get_all_sessions()
        for session_name in session_names:
            if session_name not in all_current_sessions:
                return f"Session '{session_name}' is not initialized. Available sessions: {all_current_sessions}"

        result = f"Current output of:\n\n"
        for session_name in session_names:
            result += f"Session: {session_name}\n{self.shell_manager.get_session_output(session_name)}\n"
            result += "---\n"
        return result