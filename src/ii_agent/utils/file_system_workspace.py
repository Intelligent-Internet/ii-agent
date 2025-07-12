from pathlib import Path


class WorkspaceError(Exception):
    """Custom exception for workspace-related errors."""
    pass

class FileSystemWorkspace:
    """Manages file system operations within a designated workspace directory."""

    def __init__(self, workspace_path: str | Path):
        """
        Initialize the WorkspaceManager with a workspace directory.

        Args:
            workspace_path: Path to the workspace directory (string or Path object)

        Raises:
            WorkspaceError: If the workspace path is invalid or not a directory
        """
        # Convert to Path object if it's a string
        if isinstance(workspace_path, str):
            workspace_path = Path(workspace_path)

        # Validate that the path exists and is a directory
        if not workspace_path.exists():
            raise WorkspaceError(f"Workspace path `{workspace_path}` does not exist")

        if not workspace_path.is_dir():
            raise WorkspaceError(f"Workspace path `{workspace_path}` is not a directory")

        self.workspace_path = workspace_path.resolve()

    def get_workspace_path(self) -> Path:
        """
        Get the absolute path to the workspace directory.

        Returns:
            Path object representing the workspace directory
        """
        return self.workspace_path

    def validate_boundary(self, path: Path | str) -> bool:
        """
        Check if a given path is within the workspace directory.

        Args:
            path: Path to check (string or Path object)

        Returns:
            True if path is within workspace, False otherwise
        """
        # Convert to Path object if it's a string
        if isinstance(path, str):
            path = Path(path)
        try:
            # Resolve both paths to absolute, normalized form
            path = path.resolve()
            workspace = self.get_workspace_path()
            # Check if the path is the workspace or inside it
            return workspace in path.parents or path == workspace
        except Exception:
            return False(base)