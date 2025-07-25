from pathlib import Path
import os

class WorkspaceError(Exception):
    """Custom exception for workspace-related errors."""
    pass

class FileSystemValidationError(Exception):
    """Custom exception for file system validation errors."""
    pass

class WorkspaceManager:
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
        try:
            if isinstance(path, str):
                path = Path(path)

            # Resolve both paths to absolute, normalized form
            path = path.resolve()
            
            workspace = self.get_workspace_path()
            # Check if the path is the workspace or inside it
            return workspace in path.parents or path == workspace
        except Exception:
            return False

    def validate_path(self, path: str) -> None:
        """Validate that path is absolute and within workspace boundary.
        
        Raises:
            FileSystemValidationError
        """
        if not path.strip():
            raise FileSystemValidationError("Path cannot be empty")

        if not os.path.isabs(path):
            raise FileSystemValidationError(f"Path `{path}` is not absolute")
        
        if not self.validate_boundary(path):
            raise FileSystemValidationError(f"Path `{path}` is not within workspace boundary `{self.workspace_path}`")

    def validate_existing_file_path(self, file_path: str) -> None:
        """Validate that file_path exists and is a file.
        
        Raises:
            FileSystemValidationError
        """
        self.validate_path(file_path)
        
        if not os.path.exists(file_path):
            raise FileSystemValidationError(f"File `{file_path}` does not exist")

        if not os.path.isfile(file_path):
            raise FileSystemValidationError(f"Path `{file_path}` exists but is not a file")

    def validate_existing_directory_path(self, directory_path: str) -> None:
        """Validate that directory_path exists and is a directory.
        
        Raises:
            FileSystemValidationError
        """
        self.validate_path(directory_path)
        
        if not os.path.exists(directory_path):
            raise FileSystemValidationError(f"Directory `{directory_path}` does not exist")

        if not os.path.isdir(directory_path):
            raise FileSystemValidationError(f"Path `{directory_path}` exists but is not a directory")