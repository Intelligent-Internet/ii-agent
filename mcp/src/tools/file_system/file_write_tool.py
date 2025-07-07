"""File writing tool for creating and overwriting files."""

import os
from pathlib import Path

from typing import Annotated, Optional, Dict, Any
from pydantic import Field
from src.core.workspace import WorkspaceManager
from src.tools.constants import MAX_LINE_LENGTH
from .base import BaseFileSystemTool


DESCRIPTION = """Writes a file to the local filesystem.

Usage:
- This tool will overwrite the existing file if there is one at the provided path.
- If this is an existing file, you MUST use the Read tool first to read the file's contents. This tool will fail if you did not read the file first.
- ALWAYS prefer editing existing files in the codebase. NEVER write new files unless explicitly required.
- NEVER proactively create documentation files (*.md) or README files. Only create documentation files if explicitly requested by the User.
- Only use emojis if the user explicitly requests it. Avoid writing emojis to files unless asked."""


class FileWriteTool(BaseFileSystemTool):
    """Tool for writing content to files."""
    
    name = "Write"
    description = DESCRIPTION
    
    def __init__(self, workspace_manager: WorkspaceManager):
        super().__init__(workspace_manager)

    def run_impl(
        self,
        file_path: Annotated[str, Field(description="The absolute path to the file to write (must be absolute, not relative)")],
        content: Annotated[str, Field(description="The content to write to the file")],
    ) -> str:
        """Execute the file write operation."""
        
        try:
            # Convert to Path object for clean handling
            path = Path(file_path)
            
            # Validate that the path is absolute
            if not path.is_absolute():
                return f"Error: File path must be absolute: {file_path}"
            
            # Validate that the path is within the workspace boundary
            if not self.workspace_manager.validate_boundary(path):
                workspace_path = self.workspace_manager.get_workspace_path()
                return f"Error: File path must be within the workspace directory ({workspace_path}): {file_path}"
            
            # Check if path exists and is a directory
            if path.exists() and path.is_dir():
                return f"Error: Path is a directory, not a file: {file_path}"
            
            # Create parent directories if they don't exist
            path.parent.mkdir(parents=True, exist_ok=True)
            
            # Determine if this is a new file or overwriting existing
            is_new_file = not path.exists()
            
            # Write content to file
            path.write_text(content, encoding='utf-8')
            
            # Return success message
            if is_new_file:
                return f"Successfully created and wrote to new file: {file_path}"
            else:
                return f"Successfully overwrote file: {file_path}"
                
        except PermissionError:
            return f"Error: Permission denied when writing to file: {file_path}"
        except OSError as e:
            return f"Error: OS error when writing to file {file_path}: {str(e)}"
        except Exception as e:
            return f"Error: Unexpected error when writing to file {file_path}: {str(e)}"
        
        