from typing import Annotated
from pydantic import Field
from ii_tool.tools.shell.terminal_manager import BaseShellManager, ShellInvalidSessionNameError, TmuxSessionExists
from ii_tool.core.workspace import WorkspaceManager, FileSystemValidationError

class ShellInit:
    name = "BashInit"
    description = "Initialize a bash session with a given name and start directory. Use this before running any commands in the session."

    def __init__(self, BaseShellManager: BaseShellManager, workspace_manager: WorkspaceManager) -> None:
        self.shell_manager = BaseShellManager
        self.workspace_manager = workspace_manager

    def run_impl(
        self,
        session_name: Annotated[str, Field(description="The name of the session to initialize.")],
        start_directory: Annotated[str | None, Field(description="The absolute path to a directory to start the session in. If not provided, the session will start in the workspace directory.")],
    ):
        try:
            if session_name in self.shell_manager.get_all_sessions():
                return f"Session '{session_name}' already exists"

            if not start_directory:
                start_directory = str(self.workspace_manager.get_workspace_path())

            self.workspace_manager.validate_existing_directory_path(start_directory)
            
            self.shell_manager.create_session(session_name, start_directory)
            return f"Session '{session_name}' initialized successfully at start directory `{start_directory}`"
        except (
            FileSystemValidationError,
            ShellInvalidSessionNameError,
            TmuxSessionExists,
        ) as e:
            return f"Error initializing session: {e}"