"""MultiEdit tool for making multiple edits to a single file atomically."""

from typing import List, Dict, Any
from pathlib import Path
from .base import BaseFileSystemTool, FileSystemValidationError
from .file_edit_tool import perform_replacement, FileEditToolError
from ii_agent.utils.file_system_workspace import FileSystemWorkspace


DESCRIPTION = """This is a tool for making multiple edits to a single file in one operation. It is built on top of the Edit tool and allows you to perform multiple find-and-replace operations efficiently. Prefer this tool over the Edit tool when you need to make multiple edits to the same file.

Before using this tool:

1. Use the Read tool to understand the file's contents and context
2. Verify the directory path is correct

To make multiple file edits, provide the following:
1. file_path: The absolute path to the file to modify (must be absolute, not relative)
2. edits: An array of edit operations to perform, where each edit contains:
   - old_string: The text to replace (must match the file contents exactly, including all whitespace and indentation)
   - new_string: The edited text to replace the old_string
   - replace_all: Replace all occurences of old_string. This parameter is optional and defaults to false.

IMPORTANT:
- All edits are applied in sequence, in the order they are provided
- Each edit operates on the result of the previous edit
- All edits must be valid for the operation to succeed - if any edit fails, none will be applied
- This tool is ideal when you need to make several changes to different parts of the same file

CRITICAL REQUIREMENTS:
1. All edits follow the same requirements as the single Edit tool
2. The edits are atomic - either all succeed or none are applied
3. Plan your edits carefully to avoid conflicts between sequential operations

WARNING:
- The tool will fail if edits.old_string doesn't match the file contents exactly (including whitespace)
- The tool will fail if edits.old_string and edits.new_string are the same
- Since edits are applied in sequence, ensure that earlier edits don't affect the text that later edits are trying to find

When making edits:
- Ensure all edits result in idiomatic, correct code
- Do not leave the code in a broken state
- Always use absolute file paths (starting with /)
- Only use emojis if the user explicitly requests it. Avoid adding emojis to files unless asked.
- Use replace_all for replacing and renaming strings across the file. This parameter is useful if you want to rename a variable for instance."""


class MultiEditTool(BaseFileSystemTool):
    """Tool for making multiple edits to a single file in one operation."""
    
    name = "MultiEdit"
    description = DESCRIPTION
    
    def __init__(self, workspace_manager: FileSystemWorkspace):
        super().__init__(workspace_manager)

    def run_impl(
        self,
        file_path: str,
        edits: List[Dict[str, Any]],
    ) -> str:
        """Execute multiple file edit operations atomically."""
        
        # Validate that we have edits to perform
        if not edits:
            return "ERROR: No edits provided"
        
        try:
            self.validate_existing_file_path(file_path)
            path = Path(file_path).resolve()
            
            # Read current file content
            working_content = path.read_text(encoding='utf-8')
            total_replacements = 0
            
            # Process each edit in sequence
            for i, edit in enumerate(edits):
                # Validate edit structure
                if not isinstance(edit, dict):
                    return f"ERROR: Edit {i+1} must be a dictionary"
                
                if 'old_string' not in edit or 'new_string' not in edit:
                    return f"ERROR: Edit {i+1} must contain 'old_string' and 'new_string' fields"
                
                old_string = edit['old_string']
                new_string = edit['new_string']
                replace_all = edit.get('replace_all', False)
                
                # Validate that old_string and new_string are different
                if old_string == new_string:
                    return f"ERROR: Edit {i+1}: old_string and new_string cannot be the same"
                
                # Perform the replacement on working content
                try:
                    working_content, occurrences = perform_replacement(
                        working_content, old_string, new_string, replace_all
                    )
                    total_replacements += occurrences
                except FileEditToolError as e:
                    return f"ERROR: Edit {i+1}: {e}"
            
            # All edits validated successfully, now write the final content
            path.write_text(working_content, encoding='utf-8')
            
            return f"Modified file `{path}` - applied {len(edits)} edit(s) with {total_replacements} total replacement(s). Review the changes and make sure they are as expected. Edit the file again if necessary."
            
        except (FileSystemValidationError, FileEditToolError) as e:
            return f"ERROR: {e}"
        except Exception as e:
            return f"ERROR: {e}"