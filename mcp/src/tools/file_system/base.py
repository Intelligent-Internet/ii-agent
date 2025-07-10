import os

from src.tools.base import BaseTool
from src.core.workspace import WorkspaceManager


class FileSystemValidationError(Exception):
    """Custom exception for file system validation errors."""
    pass


class BaseFileSystemTool(BaseTool):
    def __init__(self, workspace_manager: WorkspaceManager):
        self.workspace_manager = workspace_manager

    def validate_path(self, path: str) -> None:
        """Validate that path is absolute and within workspace boundary.
        
        Raises:
            FileSystemValidationError
        """
        if not path.strip():
            raise FileSystemValidationError("Path cannot be empty")

        if not os.path.isabs(path):
            raise FileSystemValidationError(f"Path `{path}` is not absolute")
        
        workspace_path = self.workspace_manager.get_workspace_path()
        if not self.workspace_manager.validate_boundary(path):
            raise FileSystemValidationError(f"Path `{path}` is not within workspace boundary `{workspace_path}`")

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