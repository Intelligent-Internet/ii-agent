from enum import Enum
import os
from pathlib import Path

from e2b import Sandbox

from ii_agent.sandbox.config import SandboxSettings
from ii_agent.sandbox.docker_sandbox import DockerSandbox


class WorkSpaceMode(Enum):
    DOCKER = "docker"
    E2B = "e2b"
    LOCAL = "local"

    def __str__(self):
        return self.value


class WorkspaceManager:
    root: Path
    session_id: str
    workspace_mode: WorkSpaceMode
    e2b_sandbox_id: str

    def __init__(
        self,
        parent_dir: str,
        session_id: str,
        workspace_mode: WorkSpaceMode = WorkSpaceMode.LOCAL,
    ):
        # Make new workspace directory
        self.root = Path(parent_dir).resolve() / session_id
        self.root.mkdir(parents=True, exist_ok=True)
        # Container configuration
        self.workspace_mode = workspace_mode
        self.session_id = session_id
        self.container_workspace = (
            None if self._is_local_workspace() else Path(SandboxSettings().work_dir)
        )
        self.e2b_sandbox_id = None

    async def start_sandbox(self):
        if self.workspace_mode == WorkSpaceMode.E2B:
            print("Starting e2b sandbox...")
            sandbox = Sandbox(
                os.getenv("E2B_TEMPLATE_ID"),
                api_key=os.getenv("E2B_API_KEY"),
                timeout=3600,
            )
            self.e2b_sandbox_id = sandbox.sandbox_id
        elif self.workspace_mode == WorkSpaceMode.DOCKER:
            print("Starting docker sandbox...")
            await self._create_container_workspace(container_name=self.session_id)
        else:
            print("Local workspace, skipping...")

    def _is_local_workspace(self) -> bool:
        return self.workspace_mode == WorkSpaceMode.LOCAL

    def use_container_workspace(self) -> bool:
        return self.workspace_mode != WorkSpaceMode.LOCAL

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
            if not self._is_local_workspace():
                return self.container_workspace / path
            else:
                return self.root / path
        return path

    def root_path(self) -> Path:
        """Return the absolute path of the workspace root.
        If there is no container workspace, return the absolute local path.
        """
        if not self._is_local_workspace():
            return self.container_workspace.absolute()
        else:
            return self.root.absolute()

    def relative_path(self, path: Path | str) -> Path:
        """Given a path, return the relative path from the workspace root.
        If the path is not under the workspace root, returns the absolute path.
        """
        path = Path(path)
        if not self._is_local_workspace():
            abs_path = self.container_path(path)
        else:
            abs_path = self.workspace_path(path)
        try:
            if self._is_local_workspace():
                return abs_path.relative_to(self.root.absolute())
            else:
                return abs_path
        except ValueError:
            return abs_path

    async def _create_container_workspace(self, container_name: str):
        settings = SandboxSettings()
        await DockerSandbox(
            container_name=container_name,
            config=settings,
            volume_bindings={
                os.getenv("WORKSPACE_PATH") + "/" + container_name: settings.work_dir
            },
        ).create()
