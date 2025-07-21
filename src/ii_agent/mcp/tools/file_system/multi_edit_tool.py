"""MultiEdit tool for making multiple edits to a single file atomically."""

from typing import Annotated, List, Dict, Any
from pydantic import Field
from ii_agent.mcp.tools.base import BaseTool
from .file_edit_tool import FileEditTool
from ii_agent.mcp.core.workspace import WorkspaceManager


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
- For Jupyter notebooks (.ipynb files), use the NotebookEdit instead

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
- Use replace_all for replacing and renaming strings across the file. This parameter is useful if you want to rename a variable for instance.

If you want to create a new file, use:
- A new file path, including dir name if needed
- First edit: empty old_string and the new file's contents as new_string
- Subsequent edits: normal edit operations on the created content"""

class MultiEditTool(BaseTool):
    """Tool for making multiple edits to a single file in one operation."""
    
    name = "MultiEdit"
    description = DESCRIPTION
    
    def __init__(self, workspace_manager: WorkspaceManager):
        super().__init__()
        self.file_edit_tool = FileEditTool(workspace_manager)

    def is_read_only(self) -> bool:
        return False

    def run_impl(
        self,
        file_path: Annotated[str, Field(description="The absolute path to the file to modify")],
        edits: Annotated[List[Dict[str, Any]], Field(description="Array of edit operations to perform sequentially on the file")],
    ) -> str:
        """Execute multiple file edit operations atomically."""
        
        # Validate that we have edits to perform
        if not edits:
            return "ERROR: No edits provided"
        
        # Validate file path first
        file_path_obj, path_error = self.file_edit_tool._validate_file_path(file_path)
        if path_error or file_path_obj is None:
            return f"ERROR: {path_error or 'Invalid file path'}"
        
        # Read current file content
        current_content, file_exists, read_error = self.file_edit_tool._read_file_content(file_path_obj)
        if read_error:
            return f"ERROR: {read_error}"
        
        # Process each edit and validate them all before applying any
        working_content = current_content
        successful_edits = []
        first_edit_line_number = None
        
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
            
            # Determine if this is a new file creation (first edit with empty old_string)
            is_new_file = not file_exists and i == 0 and old_string == ""
            
            # Handle case where file doesn't exist but old_string is not empty
            if not file_exists and i == 0 and old_string != "":
                return f"ERROR: File `{file_path_obj}` does not exist. To create a new file, use an empty old_string in the first edit"
            
            # For subsequent edits after file creation, old_string cannot be empty
            if i > 0 and old_string == "":
                return f"ERROR: Edit {i+1}: old_string cannot be empty for subsequent edits after file creation"
            
            # Perform the replacement on working content
            new_content, occurrences, edit_line_number, replacement_error = self.file_edit_tool._perform_replacement(
                working_content, old_string, new_string, replace_all, is_new_file
            )
            
            if replacement_error:
                return f"ERROR: Edit {i+1}: {replacement_error}"
            
            # Track the line number of the first edit for snippet display
            if i == 0 and edit_line_number is not None:
                first_edit_line_number = edit_line_number
            
            # Update working content for next edit
            working_content = new_content
            successful_edits.append({
                'index': i+1,
                'occurrences': occurrences,
                'replace_all': replace_all,
                'edit_line_number': edit_line_number
            })
        
        # All edits validated successfully, now write the final content
        if working_content is None:
            return "ERROR: Content is None after processing edits"
        
        write_error = self.file_edit_tool._write_file_content(file_path_obj, working_content)
        if write_error:
            return f"ERROR: {write_error}"
        
        # Generate success message
        if not file_exists and edits[0]['old_string'] == "":
            total_edits = len(successful_edits)
            if total_edits == 1:
                return f"Created new file `{file_path_obj}` with provided content."
            else:
                additional_edits = total_edits - 1
                return f"Created new file `{file_path_obj}` and applied {additional_edits} additional edit(s)."
        else:
            total_replacements = sum(edit['occurrences'] for edit in successful_edits)
            total_edits = len(successful_edits)
            
            # If we have line number information for the first edit, show a snippet
            if first_edit_line_number is not None:
                snippet = self.file_edit_tool._get_snippet_around_line(working_content, first_edit_line_number)
                return f"The file {file_path_obj} has been updated with {total_edits} edit(s) and {total_replacements} total replacement(s). Here's the result of running `cat -n` on a snippet around the first edit:\n{snippet}\nReview the changes and make sure they are as expected. Edit the file again if necessary."
            else:
                return f"SUCCESS: Modified file `{file_path_obj}` - applied {total_edits} edit(s) with {total_replacements} total replacement(s)"        