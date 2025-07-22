"""File editing tool for making targeted edits to files."""

from pathlib import Path
from typing import Annotated
from pydantic import Field
from ii_tool.core.workspace import WorkspaceManager, FileSystemValidationError
from ii_tool.tools.file_system.base import BaseFileSystemTool

DESCRIPTION = """Performs exact string replacements in files. 

Usage:
- You must use your `Read` tool at least once in the conversation before editing. This tool will error if you attempt an edit without reading the file. 
- When editing text from Read tool output, ensure you preserve the exact indentation (tabs/spaces) as it appears AFTER the line number prefix. The line number prefix format is: spaces + line number + tab. Everything after that tab is the actual file content to match. Never include any part of the line number prefix in the old_string or new_string.
- ALWAYS prefer editing existing files in the codebase. NEVER write new files unless explicitly required.
- Only use emojis if the user explicitly requests it. Avoid adding emojis to files unless asked.
- The edit will FAIL if `old_string` is not unique in the file. Either provide a larger string with more surrounding context to make it unique or use `replace_all` to change every instance of `old_string`. 
- Use `replace_all` for replacing and renaming strings across the file. This parameter is useful if you want to rename a variable for instance."""


class FileEditToolError(Exception):
    """Custom exception for file edit tool errors."""
    pass

def perform_replacement(content: str, old_string: str, new_string: str, replace_all: bool) -> tuple[str, int]:
    """Perform string replacement. Returns (new_content, occurrences)."""
    
    # Count occurrences
    occurrences = content.count(old_string)
    
    if occurrences == 0:
        raise FileEditToolError("String to replace not found in file. Make sure the old_string exactly matches the file content, including whitespace and indentation")
    
    # For single replacement, ensure uniqueness
    if not replace_all and occurrences > 1:
        raise FileEditToolError(f"Found {occurrences} occurrences of old_string. Either provide more context to make it unique, or use replace_all=True to replace all occurrences")

    new_content = content.replace(old_string, new_string)
    
    return new_content, occurrences


class FileEditTool(BaseFileSystemTool):
    """Tool for making targeted string replacements in files."""
    
    name = "Edit"
    description = DESCRIPTION
    read_only = False
    
    def __init__(self, workspace_manager: WorkspaceManager):
        super().__init__(workspace_manager)

    def run_impl(
        self,
        file_path: Annotated[str, Field(description="The absolute path to the file to modify")],
        old_string: Annotated[str, Field(description="The text to replace")],
        new_string: Annotated[str, Field(description="The text to replace it with (must be different from old_string)")],
        replace_all: Annotated[bool, Field(description="Replace all occurences of old_string (default false)", default=False)],
    ) -> str:
        """Execute the file edit operation."""
        
        # Validate parameters
        if old_string == new_string:
            return "ERROR: old_string and new_string cannot be the same"

        # Validate file path
        try:
            self.workspace_manager.validate_existing_file_path(file_path)
        
            path = Path(file_path).resolve()

            # Read current file content
            current_content = path.read_text(encoding='utf-8')
        
            # Perform the replacement
            new_content, occurrences = perform_replacement(
                current_content, old_string, new_string, replace_all
            )
            # Write the new content
            path.write_text(new_content, encoding='utf-8')
            
            return f"Modified file `{path}` - made {occurrences} replacement(s). Review the changes and make sure they are as expected. Edit the file again if necessary."
        
        except (FileSystemValidationError, FileEditToolError) as e:
            return f"ERROR: {e}"