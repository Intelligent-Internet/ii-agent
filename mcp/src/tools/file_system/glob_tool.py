"""File pattern matching tool using glob patterns."""

from pathlib import Path
from typing import Annotated, Optional
from pydantic import Field
from src.core.workspace import WorkspaceManager
from src.tools.constants import MAX_GLOB_RESULTS
from .base import BaseFileSystemTool


DESCRIPTION = """- Fast file pattern matching tool that works with any codebase size
- Supports glob patterns like "**/*.js" or "src/**/*.ts"
- Returns matching file paths sorted by modification time
- Use this tool when you need to find files by name patterns
- When you are doing an open ended search that may require multiple rounds of globbing and grepping, use the Agent tool instead
- You have the capability to call multiple tools in a single response. It is always better to speculatively perform multiple searches as a batch that are potentially useful."""


class GlobTool(BaseFileSystemTool):
    """Tool for finding files using glob patterns."""
    
    name = "Glob"
    description = DESCRIPTION

    def __init__(self, workspace_manager: WorkspaceManager):
        super().__init__(workspace_manager)

    def run_impl(
        self,
        pattern: Annotated[str, Field(description="The glob pattern to match files against")],
        path: Annotated[Optional[str], Field(description="The directory to search in. If not specified, the current working directory will be used. IMPORTANT: Omit this field to use the default directory. DO NOT enter \"undefined\" or \"null\" - simply omit it for the default behavior. Must be a valid directory path if provided.")],
    ) -> str:
        """Execute the glob pattern matching operation."""

        workspace_path = self.workspace_manager.get_workspace_path()
        
        # Determine the search directory
        if path is None:
            search_dir = workspace_path
        else:
            # Convert to Path and resolve to absolute path
            search_dir = Path(path).resolve()

            # Check if path is in workspace
            if not self.workspace_manager.validate_boundary(search_dir):
                return f"ERROR: Path `{search_dir}` is not in workspace boundary `{workspace_path}`"
            
            # Verify the directory exists
            if not search_dir.exists():
                return f"ERROR: Directory `{search_dir}` does not exist"
            
            if not search_dir.is_dir():
                return f"ERROR: Path `{search_dir}` is not a directory"

        # Execute glob pattern using pathlib
        matches = list(search_dir.glob(pattern))
        
        # Filter out directories, keep only files
        file_matches = [match for match in matches if match.is_file()]
        
        # Sort by modification time (newest first)
        file_matches.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        
        # If no matches found
        if not file_matches:
            return f"No files found matching pattern \"{pattern}\" within {search_dir}"
        
        # Limit results and prepare file list
        original_count = len(file_matches)
        if len(file_matches) > MAX_GLOB_RESULTS:
            file_matches = file_matches[:MAX_GLOB_RESULTS]
        
        # Convert Path objects to relative strings for display
        file_list_description = "\n".join(str(match.relative_to(search_dir)) for match in file_matches)
        file_count = len(file_matches)
        
        # Format result message
        result_message = f"Found {file_count} file(s) matching \"{pattern}\" within {search_dir}"
        result_message += f", sorted by modification time (newest first):\n{file_list_description}"
        
        # Add truncation note if needed
        if original_count > MAX_GLOB_RESULTS:
            result_message += f"\n\nNote: Results limited to {MAX_GLOB_RESULTS} files. Total matches found: {original_count}"
        
        return result_message