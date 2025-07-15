from typing import Annotated
from pydantic import Field
from src.tools.shell.terminal_manager import BaseShellManager

class ShellKill:
    name = "shell_kill_session"
    description = "Kill a shell session."

    def __init__(self, BaseShellManager: BaseShellManager) -> None:
        self.shell_manager = BaseShellManager

    def run_impl(
        self,
        session_name: Annotated[str, Field(description="The name of the session to kill.")],
    ):
        all_current_sessions = self.shell_manager.get_all_sessions()
        if session_name not in all_current_sessions:
            return f"Session '{session_name}' is not available. Available sessions: {all_current_sessions}"

        self.shell_manager.delete_session(session_name)
        return f"Session '{session_name}' killed successfully."