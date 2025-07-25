"""File pattern matching tool using glob patterns."""

from pathlib import Path
from typing import Annotated, Optional
from pydantic import Field
from .base import BaseFileSystemTool, FileSystemValidationError
from ii_agent.utils.file_system_workspace import FileSystemWorkspace

DESCRIPTION = """- Fast file pattern matching tool that works with any codebase size
- Supports glob patterns like "**/*.js" or "src/**/*.ts"
- Returns matching file paths sorted by modification time
- Use this tool when you need to find files by name patterns
- When you are doing an open ended search that may require multiple rounds of globbing and grepping, use the Agent tool instead
- You have the capability to call multiple tools in a single response. It is always better to speculatively perform multiple searches as a batch that are potentially useful."""
MAX_GLOB_RESULTS = 100


class GlobTool(BaseFileSystemTool):
    """Tool for finding files using glob patterns."""
    
    name = "Glob"
    description = DESCRIPTION

    def __init__(self, workspace_manager: FileSystemWorkspace):
        super().__init__(workspace_manager)

    def run_impl(
        self,
        pattern: Annotated[str, Field(description="The glob pattern to match files against")],
        path: Annotated[Optional[str], Field(description="The directory to search in. If not specified, the current working directory will be used. IMPORTANT: Omit this field to use the default directory. DO NOT enter \"undefined\" or \"null\" - simply omit it for the default behavior. Must be a valid directory path if provided.")] = None,
    ) -> str:
        """Execute the glob pattern matching operation."""
        
        try:
            if path is None:
                search_dir = self.workspace_manager.get_workspace_path()
            else:
                self.validate_existing_directory_path(path)
                search_dir = Path(path).resolve()

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
            need_truncation = original_count > MAX_GLOB_RESULTS
            if need_truncation:
                file_matches = file_matches[:MAX_GLOB_RESULTS]
            
            # Convert Path objects to relative strings for display
            file_list_description = "\n".join(str(match.relative_to(search_dir)) for match in file_matches)
            
            # Format result message
            result_message = f"Found {len(file_matches)} file(s) matching \"{pattern}\" within {search_dir}"
            result_message += f", sorted by modification time (newest first):\n{file_list_description}"
            
            # Add truncation note if needed
            if need_truncation:
                result_message += f"\n\nNote: Results limited to {MAX_GLOB_RESULTS} files. Total matches found: {original_count}"
            
            return result_message
        except FileSystemValidationError as e:
            return f"ERROR: {e}"