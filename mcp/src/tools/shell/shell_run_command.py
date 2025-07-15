from typing import Annotated
from pydantic import Field
from src.tools.shell.terminal_manager import BaseShellManager, ShellCommandTimeoutError, ShellBusyError

DEFAULT_TIMEOUT = 60

class ShellRunCommand:
    name = "shell_run_command"
    description = "Execute a shell command in a sandboxed environment."

    def __init__(self, BaseShellManager: BaseShellManager) -> None:
        self.shell_manager = BaseShellManager

    def run_impl(
        self,
        session_name: Annotated[str, Field(description="The name of the session to execute the command in.")],
        command: Annotated[str, Field(description="The command to execute.")],
        timeout: Annotated[int, Field(description="The timeout for the command in seconds.")] = DEFAULT_TIMEOUT,
        wait_for_output: Annotated[bool, Field(description="Whether to wait for the command to finish and return the output within the timeout. For serving or long running commands, it is recommended to set this to False and use `ShellView` to get the output.")] = True,
    ):
        all_current_sessions = self.shell_manager.get_all_sessions()
        if session_name not in all_current_sessions:
            return f"Session '{session_name}' is not initialized. Use `ShellInit` to initialize a session. Available sessions: {all_current_sessions}"
            
        try:
            result = self.shell_manager.run_command(session_name, command, timeout=timeout, wait_for_output=wait_for_output)
            return result
        except ShellCommandTimeoutError:
            return "Command timed out"
        except ShellBusyError:
            return f"The last command is not finished. Current view:\n\n{self.shell_manager.get_session_output(session_name)}"