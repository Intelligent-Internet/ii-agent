"""File writing tool for creating and overwriting files."""

from typing import Any
from pathlib import Path
from ii_tool.core.workspace import WorkspaceManager, FileSystemValidationError
from ii_tool.tools.base import BaseTool, ToolResult, ToolConfirmationDetails


# Name
NAME = "Write"
DISPLAY_NAME = "Write file"

# Tool description
DESCRIPTION = """Writes a file to the local filesystem.

Usage:
- This tool will overwrite the existing file if there is one at the provided path.
- If this is an existing file, you MUST use the Read tool first to read the file's contents. This tool will fail if you did not read the file first.
- ALWAYS prefer editing existing files in the codebase. NEVER write new files unless explicitly required.
- NEVER proactively create documentation files (*.md) or README files. Only create documentation files if explicitly requested by the User.
- Only use emojis if the user explicitly requests it. Avoid writing emojis to files unless asked."""

# Input schema
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "file_path": {
            "type": "string",
            "description": "The absolute path to the file to write"
        },
        "content": {
            "type": "string",
            "description": "The content to write to the file"
        }
    },
    "required": ["file_path", "content"]
}

class FileWriteTool(BaseTool):
    """Tool for writing content to files."""
    
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = False
    
    def __init__(self, workspace_manager: WorkspaceManager):
        self.workspace_manager = workspace_manager

    def should_confirm_execute(self, tool_input: dict[str, Any]) -> ToolConfirmationDetails | bool:
        return ToolConfirmationDetails(
            type="edit",
            message=f"Write file {tool_input['file_path']} with the following content:\n{tool_input['content']}"
        )

    async def execute(
        self,
        tool_input: dict[str, Any],
    ) -> ToolResult:
        """Execute the file write operation."""
        file_path = tool_input.get("file_path")
        content = tool_input.get("content")
        
        try:
            self.workspace_manager.validate_path(file_path)

            path = Path(file_path).resolve()
            
            # Check if path exists and is a directory
            if path.exists() and path.is_dir():
                return ToolResult(
                    llm_content=f"ERROR: Path is a directory, not a file: {file_path}",
                    is_error=True
                )
            
            # Create parent directories if they don't exist
            path.parent.mkdir(parents=True, exist_ok=True)
            
            # Determine if this is a new file or overwriting existing
            is_new_file = not path.exists()
            
            # Write content to file
            path.write_text(content, encoding='utf-8')
            
            # Return success message
            if is_new_file:
                return ToolResult(
                    llm_content=f"Successfully created and wrote to new file: {file_path}",
                    is_error=False
                )
            else:
                return ToolResult(
                    llm_content=f"Successfully overwrote file: {file_path}",
                    is_error=False
                )
        
        except (FileSystemValidationError) as e:
            return ToolResult(
                llm_content=f"ERROR: {e}",
                is_error=True
            )

    async def execute_mcp_wrapper(
        self,
        file_path: str,
        content: str,
    ):
        return await self._mcp_wrapper(
            tool_input={
                "file_path": file_path,
                "content": content,
            }
        )