"""File writing tool for creating and overwriting files."""

from pathlib import Path
from typing import Annotated
from pydantic import Field
from src.core.workspace import WorkspaceManager
from .base import BaseFileSystemTool, FileSystemValidationError


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
        file_path: Annotated[str, Field(description="The absolute path to the file to write")],
        content: Annotated[str, Field(description="The content to write to the file")],
    ) -> str:
        """Execute the file write operation."""
        
        try:
            self.validate_path(file_path)

            path = Path(file_path).resolve()
            
            # Check if path exists and is a directory
            if path.exists() and path.is_dir():
                return f"ERROR: Path is a directory, not a file: {file_path}"
            
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
        
        except (FileSystemValidationError) as e:
            return f"ERROR: {e}"