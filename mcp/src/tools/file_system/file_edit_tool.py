"""File editing tool for making targeted edits to files."""

import os
from pathlib import Path
from glob import glob
from typing import Annotated
from pydantic import Field
from src.core.workspace import WorkspaceManager
from .base import BaseFileSystemTool


DESCRIPTION = """Performs exact string replacements in files. 

Usage:
- You must use your `Read` tool at least once in the conversation before editing. This tool will error if you attempt an edit without reading the file. 
- When editing text from Read tool output, ensure you preserve the exact indentation (tabs/spaces) as it appears AFTER the line number prefix. The line number prefix format is: spaces + line number + tab. Everything after that tab is the actual file content to match. Never include any part of the line number prefix in the old_string or new_string.
- ALWAYS prefer editing existing files in the codebase. NEVER write new files unless explicitly required.
- Only use emojis if the user explicitly requests it. Avoid adding emojis to files unless asked.
- The edit will FAIL if `old_string` is not unique in the file. Either provide a larger string with more surrounding context to make it unique or use `replace_all` to change every instance of `old_string`. 
- Use `replace_all` for replacing and renaming strings across the file. This parameter is useful if you want to rename a variable for instance."""


def find_similar_file(file_path: str) -> str | None:
    """Find similar files with different extensions."""
    try:
        base_path = os.path.splitext(file_path)[0]
        parent_dir = os.path.dirname(file_path)
        base_name = os.path.basename(base_path)
        
        # Look for files with same base name but different extensions
        pattern = os.path.join(parent_dir, f"{base_name}.*")
        similar_files = glob.glob(pattern)
        
        if similar_files:
            # Return the first match that's not the original file
            for similar in similar_files:
                if similar != file_path:
                    return similar
        
        return None
    except Exception:
        return None


class FileEditTool(BaseFileSystemTool):
    """Tool for making targeted string replacements in files."""
    
    name = "Edit"
    description = DESCRIPTION
    
    def __init__(self, workspace_manager: WorkspaceManager):
        super().__init__(workspace_manager)

    def _validate_file_path(self, file_path: str) -> tuple[Path | None, str | None]:
        """Validate file path and return Path object and error message if any."""
        if not file_path:
            return None, "File path cannot be empty"
        
        # Convert to Path object and resolve to absolute path
        try:
            file_path_obj = Path(file_path).resolve()
        except Exception as e:
            return None, f"Invalid file path: {e}"
        
        # Check if path is within workspace boundary
        if not self.workspace_manager.validate_boundary(file_path_obj):
            workspace_path = self.workspace_manager.get_workspace_path()
            return None, f"File path `{file_path_obj}` is not within workspace boundary `{workspace_path}`"
        
        return file_path_obj, None

    def _read_file_content(self, file_path: Path) -> tuple[str | None, bool, str | None]:
        """Read file content. Returns (content, file_exists, error_message)."""
        try:
            if not file_path.exists():
                return None, False, None
            
            if not file_path.is_file():
                return None, True, f"Path `{file_path}` exists but is not a file"
            
            content = file_path.read_text(encoding='utf-8', errors='ignore')
            # Normalize line endings to LF for consistent processing
            content = content.replace('\r\n', '\n')
            return content, True, None
            
        except PermissionError:
            return None, True, f"Permission denied reading file `{file_path}`"
        except UnicodeDecodeError:
            return None, True, f"File `{file_path}` contains non-text content or unsupported encoding"
        except Exception as e:
            return None, True, f"Error reading file `{file_path}`: {e}"

    def _write_file_content(self, file_path: Path, content: str) -> str | None:
        """Write content to file. Returns error message if any."""
        try:
            # Ensure parent directories exist
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write content to file
            file_path.write_text(content, encoding='utf-8')
            return None
            
        except PermissionError:
            return f"Permission denied writing to file `{file_path}`"
        except Exception as e:
            return f"Error writing file `{file_path}`: {e}"

    def _perform_replacement(self, content: str | None, old_string: str, new_string: str, 
                           replace_all: bool, is_new_file: bool) -> tuple[str, int, int | None, str | None]:
        """Perform string replacement. Returns (new_content, occurrences, edit_line_number, error_message)."""
        
        # Handle new file creation
        if is_new_file:
            if old_string != "":
                return "", 0, None, "For new file creation, old_string must be empty"
            return new_string, 1, 1, None
        
        # Handle existing file editing
        if content is None:
            return "", 0, None, "Cannot edit file: content is None"
        
        # Handle empty old_string for existing file
        if old_string == "":
            return "", 0, None, "Cannot use empty old_string for existing file (use it only for new file creation)"
        
        # Count occurrences
        occurrences = content.count(old_string)
        
        if occurrences == 0:
            return content, 0, None, "String to replace not found in file. Make sure the old_string exactly matches the file content, including whitespace and indentation"
        
        # For single replacement, ensure uniqueness
        if not replace_all and occurrences > 1:
            return content, occurrences, None, f"Found {occurrences} occurrences of old_string. Either provide more context to make it unique, or use replace_all=True to replace all occurrences"
        
        # Find the line number of the first replacement
        edit_line_number = None
        if occurrences > 0:
            # Find the position of the first occurrence
            first_occurrence_pos = content.find(old_string)
            if first_occurrence_pos != -1:
                # Count newlines before this position to get line number
                edit_line_number = content[:first_occurrence_pos].count('\n') + 1
        
        # Perform replacement
        if replace_all:
            new_content = content.replace(old_string, new_string)
        else:
            # Replace only the first occurrence
            new_content = content.replace(old_string, new_string, 1)
        
        return new_content, occurrences, edit_line_number, None

    def _get_snippet_around_line(self, content: str, line_number: int, lines_before: int = 5, lines_after: int = 5) -> str:
        """Extract a snippet of lines around a specific line number with cat -n format."""
        lines = content.split('\n')
        total_lines = len(lines)
        
        # Calculate the range
        start_line = max(1, line_number - lines_before)
        end_line = min(total_lines, line_number + lines_after)
        
        # Extract the lines (convert to 0-based indexing)
        snippet_lines = lines[start_line - 1:end_line]
        
        # Format with line numbers like cat -n
        formatted_lines = []
        for i, line in enumerate(snippet_lines):
            current_line_num = start_line + i
            formatted_lines.append(f"{current_line_num:6d}\t{line}")
        
        return '\n'.join(formatted_lines)

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
        
        # Validate and resolve file path
        file_path_obj, path_error = self._validate_file_path(file_path)
        if path_error or file_path_obj is None:
            return f"ERROR: {path_error or 'Invalid file path'}"
        
        # Read current file content
        current_content, file_exists, read_error = self._read_file_content(file_path_obj)
        if read_error:
            return f"ERROR: {read_error}"
        
        # Determine if this is a new file creation
        is_new_file = not file_exists and old_string == ""
        
        # Handle case where file doesn't exist but old_string is not empty
        if not file_exists and old_string != "":
            return f"ERROR: File `{file_path_obj}` does not exist. To create a new file, use an empty old_string"
        
        # Perform the replacement
        new_content, occurrences, edit_line_number, replacement_error = self._perform_replacement(
            current_content, old_string, new_string, replace_all, is_new_file
        )
        
        if replacement_error:
            return f"ERROR: {replacement_error}"
        
        # Write the new content
        write_error = self._write_file_content(file_path_obj, new_content)
        if write_error:
            return f"ERROR: {write_error}"
        
        # Generate success message
        if is_new_file:
            return f"Created new file `{file_path_obj}` with provided content."
        else:
            # Get snippet around the edit location
            if edit_line_number is not None:
                snippet = self._get_snippet_around_line(new_content, edit_line_number)
                return f"The file {file_path_obj} has been updated. Here's the result of running `cat -n` on a snippet of the edited file:\n{snippet}\nReview the changes and make sure they are as expected. Edit the file again if necessary."
            else:
                replacement_word = "replacements" if occurrences > 1 else "replacement"
                operation = "all occurrences" if replace_all else "first occurrence"
                return f"Modified file `{file_path_obj}` - made {occurrences} {replacement_word} ({operation})"
        
        