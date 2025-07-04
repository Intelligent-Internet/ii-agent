from pathlib import Path

from ii_agent.core.storage.models.settings import Settings
from ii_agent.sandbox.config import SandboxSettings
from ii_agent.utils.constants import WorkSpaceMode


class WorkspaceManager:
    root: Path
    session_id: str
    workspace_mode: WorkSpaceMode

    def __init__(
        self,
        parent_dir: str,
        session_id: str,
        settings: Settings,
    ):
        # Make new workspace directory
        self.root = Path(parent_dir).resolve() / session_id
        self.root.mkdir(parents=True, exist_ok=True)
        # Container configuration
        self.workspace_mode = settings.sandbox_config.mode
        self.session_id = session_id
        self.container_workspace = (
            None if self.is_local_workspace() else Path(SandboxSettings().work_dir)
        )

    def is_local_workspace(self) -> bool:
        return self.workspace_mode == WorkSpaceMode.LOCAL

    def workspace_path(self, path: Path | str) -> Path:
        """Given a path, possibly in a container workspace, return the absolute local path."""
        path = Path(path)
        if not path.is_absolute():
            return self.root / path
        if self.container_workspace and path.is_relative_to(self.container_workspace):
            return self.root / path.relative_to(self.container_workspace)
        return path

    def container_path(self, path: Path | str) -> Path:
        """Given a path, possibly in the local workspace, return the absolute container path.
        If there is no container workspace, return the absolute local path.
        """
        path = Path(path)
        if not path.is_absolute():
            if not self.is_local_workspace():
                return self.container_workspace / path
            else:
                return self.root / path
        return path

    def root_path(self) -> Path:
        """Return the absolute path of the workspace root.
        If there is no container workspace, return the absolute local path.
        """
        if not self.is_local_workspace():
            return self.container_workspace.absolute()
        else:
            return self.root.absolute()

    def relative_path(self, path: Path | str) -> Path:
        """Given a path, return the relative path from the workspace root.
        If the path is not under the workspace root, returns the absolute path.
        """
        path = Path(path)
        if not self.is_local_workspace():
            abs_path = self.container_path(path)
        else:
            abs_path = self.workspace_path(path)
        try:
            if self.is_local_workspace():
                return abs_path.relative_to(self.root.absolute())
            else:
                return abs_path
        except ValueError:
            return abs_path
