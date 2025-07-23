"""MultiEdit tool for making multiple edits to a single file atomically."""

from pathlib import Path
from typing import List, Dict, Any
from ii_tool.tools.base import BaseTool, ToolResult
from ii_tool.tools.file_system.file_edit_tool import FileEditTool, FileEditToolError, _perform_replacement
from ii_tool.core.workspace import WorkspaceManager, FileSystemValidationError

# Name
NAME = "MultiEdit"
DISPLAY_NAME = "Edit multiple files"

# Tool description
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


# Input schema
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "file_path": {
            "type": "string",
            "description": "The absolute path to the file to modify",
        },
        "edits": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "old_string": {"type": "string"},
                    "new_string": {"type": "string"},
                    "replace_all": {"type": "boolean", "default": False}
                },
                "required": ["old_string", "new_string"]
            },
            "description": "Array of edit operations to perform sequentially on the file",
        }
    },
    "required": ["file_path", "edits"]
}


class MultiEditTool(BaseTool):
    """Tool for making multiple edits to a single file in one operation."""
    
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = False
    
    def __init__(self, workspace_manager: WorkspaceManager):
        self.workspace_manager = workspace_manager

    async def execute(
        self,
        file_path: str,
        edits: List[Dict[str, Any]],
    ) -> ToolResult:
        """Execute multiple file edit operations atomically."""
        
        # Validate that we have edits to perform
        if not edits:
            return ToolResult(
                llm_content="ERROR: No edits provided",
                is_error=True
            )
        
        try:
            # Validate file path first
            self.workspace_manager.validate_existing_file_path(file_path)
            path = Path(file_path).resolve()

            # Read current file content
            current_content = path.read_text(encoding='utf-8')
            
            # Process each edit and validate them all before applying any
            working_content = current_content
            successful_edits = []
            
            for i, edit in enumerate(edits):
                # Validate edit structure
                if not isinstance(edit, dict):
                    return ToolResult(
                        llm_content=f"ERROR: Edit {i+1} must be a dictionary",
                        is_error=True
                    )
                
                if 'old_string' not in edit or 'new_string' not in edit:
                    return ToolResult(
                        llm_content=f"ERROR: Edit {i+1} must contain 'old_string' and 'new_string' fields",
                        is_error=True
                    )
                
                old_string = edit['old_string']
                new_string = edit['new_string']
                replace_all = edit.get('replace_all', False)
                
                # Validate that old_string and new_string are different
                if old_string == new_string:
                    return ToolResult(
                        llm_content=f"ERROR: Edit {i+1}: old_string and new_string cannot be the same",
                        is_error=True
                    )
                
                # Perform the replacement on working content
                try:
                    new_content, occurrences = _perform_replacement(
                        working_content, old_string, new_string, replace_all
                    )
                    
                    # Update working content for next edit
                    working_content = new_content
                    successful_edits.append({
                        'index': i+1,
                        'occurrences': occurrences,
                        'replace_all': replace_all
                    })
                    
                except FileEditToolError as e:
                    return ToolResult(
                        llm_content=f"ERROR: Edit {i+1}: {e}",
                        is_error=True
                    )
            
            # All edits validated successfully, now write the final content
            path.write_text(working_content, encoding='utf-8')
            
            # Generate success message
            total_replacements = sum(edit['occurrences'] for edit in successful_edits)
            total_edits = len(successful_edits)
            
            msg = f"Modified file `{path}` - applied {total_edits} edit(s) with {total_replacements} total replacement(s). Review the changes and make sure they are as expected. Edit the file again if necessary."
            return ToolResult(
                llm_content=msg,
                is_error=False
            )
        
        except (FileSystemValidationError, FileEditToolError) as e:
            msg = f"ERROR: {e}"
            return ToolResult(
                llm_content=msg,
                is_error=True
            )
        except Exception as e:
            msg = f"ERROR: Unexpected error: {e}"
            return ToolResult(
                llm_content=msg,
                is_error=True
            )        

    async def execute_mcp_wrapper(
        self,
        file_path: str,
        edits: List[Dict[str, Any]],
    ):
        return await self._mcp_wrapper(file_path, edits) 