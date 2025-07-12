"""
Adapter tools that bridge external file system tools to ii-agent framework.

These tools provide a unified interface for file system operations that work
in both local and remote (Docker) environments.
"""

import logging
import json
from typing import Any, Optional, List, Dict
from asyncio import Queue

from ii_agent.llm.message_history import MessageHistory
from ii_agent.tools.base import LLMTool, ToolImplOutput
from ii_agent.core.event import EventType, RealtimeEvent
from ii_agent.core.storage.models.settings import Settings
from ii_agent.tools.clients.filesystem_client import FileSystemClient

logger = logging.getLogger(__name__)


class FileSystemToolError(Exception):
    """Custom exception for file system tool errors."""
    pass


class ReadTool(LLMTool):
    """Tool for reading file contents with optional line range specification."""
    
    name = "Read"
    description = """Reads and returns the content of a specified file from the local filesystem. Handles text files, images (PNG, JPG, GIF, WEBP, SVG, BMP), and PDF files.

Usage:
- The file_path parameter must be an absolute path, not a relative path
- For text files and PDFs: reads up to 2000 lines by default with optional offset/limit parameters
- For images: returns base64-encoded content with MIME type information
- For PDFs: extracts and returns readable text content (falls back to base64 if text extraction fails)
- Any lines longer than 2000 characters will be truncated
- Results are returned using cat -n format, with line numbers starting at 1
- If you read a file that exists but has empty contents you will receive a system reminder warning in place of file contents."""

    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "The absolute path to the file to read",
            },
            "limit": {
                "type": "integer",
                "description": "The number of lines to read. Only provide if the file is too large to read at once.",
            },
            "offset": {
                "type": "integer", 
                "description": "The line number to start reading from. Only provide if the file is too large to read at once",
            },
        },
        "required": ["file_path"],
    }

    def __init__(self, settings: Settings, message_queue: Optional[Queue] = None):
        super().__init__()
        self.message_queue = message_queue
        self.filesystem_client = FileSystemClient(settings)

    async def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        file_path = tool_input["file_path"]
        limit = tool_input.get("limit")
        offset = tool_input.get("offset")

        try:
            response = self.filesystem_client.read_file(file_path, limit, offset)
            
            if response.success:
                return ToolImplOutput(
                    response.file_content,
                    f"Successfully read file {file_path}",
                    {"success": True},
                )
            else:
                return ToolImplOutput(
                    response.file_content,
                    f"Failed to read file {file_path}",
                    {"success": False},
                )
        except Exception as e:
            return ToolImplOutput(
                f"Error reading file: {str(e)}",
                f"Error reading file {file_path}",
                {"success": False},
            )

    def get_tool_start_message(self, tool_input: dict[str, Any]) -> str:
        return f"Reading file {tool_input['file_path']}"


class EditTool(LLMTool):
    """Tool for making targeted string replacements in files."""
    
    name = "Edit"
    description = """Performs exact string replacements in files. 

Usage:
- You must use your `Read` tool at least once in the conversation before editing. This tool will error if you attempt an edit without reading the file. 
- When editing text from Read tool output, ensure you preserve the exact indentation (tabs/spaces) as it appears AFTER the line number prefix. The line number prefix format is: spaces + line number + tab. Everything after that tab is the actual file content to match. Never include any part of the line number prefix in the old_string or new_string.
- ALWAYS prefer editing existing files in the codebase. NEVER write new files unless explicitly required.
- Only use emojis if the user explicitly requests it. Avoid adding emojis to files unless asked.
- The edit will FAIL if `old_string` is not unique in the file. Either provide a larger string with more surrounding context to make it unique or use `replace_all` to change every instance of `old_string`. 
- Use `replace_all` for replacing and renaming strings across the file. This parameter is useful if you want to rename a variable for instance."""

    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "The absolute path to the file to modify",
            },
            "old_string": {
                "type": "string",
                "description": "The text to replace",
            },
            "new_string": {
                "type": "string",
                "description": "The text to replace it with (must be different from old_string)",
            },
            "replace_all": {
                "type": "boolean",
                "description": "Replace all occurences of old_string (default false)",
                "default": False,
            },
        },
        "required": ["file_path", "old_string", "new_string"],
    }

    def __init__(self, settings: Settings, message_queue: Optional[Queue] = None):
        super().__init__()
        self.message_queue = message_queue
        self.filesystem_client = FileSystemClient(settings)

    async def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        file_path = tool_input["file_path"]
        old_string = tool_input["old_string"]
        new_string = tool_input["new_string"]
        replace_all = tool_input.get("replace_all", False)

        try:
            response = self.filesystem_client.edit_file(file_path, old_string, new_string, replace_all)
            
            if response.success:
                self._send_file_update(file_path)
                return ToolImplOutput(
                    response.file_content,
                    f"Successfully edited file {file_path}",
                    {"success": True},
                )
            else:
                return ToolImplOutput(
                    response.file_content,
                    f"Failed to edit file {file_path}",
                    {"success": False},
                )
        except Exception as e:
            return ToolImplOutput(
                f"Error editing file: {str(e)}",
                f"Error editing file {file_path}",
                {"success": False},
            )

    def get_tool_start_message(self, tool_input: dict[str, Any]) -> str:
        return f"Editing file {tool_input['file_path']}"

    def _send_file_update(self, file_path: str):
        """Send file update event through message queue if available."""
        if self.message_queue:
            # Read the updated file content to send the update
            try:
                response = self.filesystem_client.read_file(file_path)
                if response.success:
                    self.message_queue.put_nowait(
                        RealtimeEvent(
                            type=EventType.FILE_EDIT,
                            content={
                                "path": str(file_path),
                                "content": response.file_content,
                                "total_lines": len(response.file_content.splitlines()),
                            },
                        )
                    )
            except Exception as e:
                logger.error(f"Failed to send file update for {file_path}: {e}")


class WriteTool(LLMTool):
    """Tool for creating new files or overwriting existing ones."""
    
    name = "Write"
    description = """Writes a file to the local filesystem.

Usage:
- This tool will overwrite the existing file if there is one at the provided path.
- If this is an existing file, you MUST use the Read tool first to read the file's contents. This tool will fail if you did not read the file first.
- ALWAYS prefer editing existing files in the codebase. NEVER write new files unless explicitly required.
- NEVER proactively create documentation files (*.md) or README files. Only create documentation files if explicitly requested by the User.
- Only use emojis if the user explicitly requests it. Avoid writing emojis to files unless asked."""

    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "The absolute path to the file to write (must be absolute, not relative)",
            },
            "content": {
                "type": "string",
                "description": "The content to write to the file",
            },
        },
        "required": ["file_path", "content"],
    }

    def __init__(self, settings: Settings, message_queue: Optional[Queue] = None):
        super().__init__()
        self.message_queue = message_queue
        self.filesystem_client = FileSystemClient(settings)

    async def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        file_path = tool_input["file_path"]
        content = tool_input["content"]

        try:
            response = self.filesystem_client.write_file(file_path, content)
            
            if response.success:
                self._send_file_update(file_path, content)
                return ToolImplOutput(
                    response.file_content,
                    f"Successfully wrote file {file_path}",
                    {"success": True},
                )
            else:
                return ToolImplOutput(
                    response.file_content,
                    f"Failed to write file {file_path}",
                    {"success": False},
                )
        except Exception as e:
            return ToolImplOutput(
                f"Error writing file: {str(e)}",
                f"Error writing file {file_path}",
                {"success": False},
            )

    def get_tool_start_message(self, tool_input: dict[str, Any]) -> str:
        return f"Writing file {tool_input['file_path']}"

    def _send_file_update(self, file_path: str, content: str):
        """Send file update event through message queue if available."""
        if self.message_queue:
            self.message_queue.put_nowait(
                RealtimeEvent(
                    type=EventType.FILE_EDIT,
                    content={
                        "path": str(file_path),
                        "content": content,
                        "total_lines": len(content.splitlines()),
                    },
                )
            )


class MultiEditTool(LLMTool):
    """Tool for making multiple edits to a single file in one operation."""
    
    name = "MultiEdit"
    description = """This is a tool for making multiple edits to a single file in one operation. It is built on top of the Edit tool and allows you to perform multiple find-and-replace operations efficiently. Prefer this tool over the Edit tool when you need to make multiple edits to the same file.

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

    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "The absolute path to the file to modify",
            },
            "edits": {
                "type": "array",
                "description": "Array of edit operations to perform sequentially on the file",
                "items": {
                    "type": "object",
                    "properties": {
                        "old_string": {
                            "type": "string",
                            "description": "The text to replace",
                        },
                        "new_string": {
                            "type": "string",
                            "description": "The text to replace it with",
                        },
                        "replace_all": {
                            "type": "boolean",
                            "description": "Replace all occurences of old_string (default false).",
                            "default": False,
                        },
                    },
                    "required": ["old_string", "new_string"],
                },
                "minItems": 1,
            },
        },
        "required": ["file_path", "edits"],
    }

    def __init__(self, settings: Settings, message_queue: Optional[Queue] = None):
        super().__init__()
        self.message_queue = message_queue
        self.filesystem_client = FileSystemClient(settings)

    async def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        file_path = tool_input["file_path"]
        edits = tool_input["edits"]

        try:
            response = self.filesystem_client.multi_edit(file_path, edits)
            
            if response.success:
                self._send_file_update(file_path)
                return ToolImplOutput(
                    response.file_content,
                    f"Successfully applied {len(edits)} edits to file {file_path}",
                    {"success": True},
                )
            else:
                return ToolImplOutput(
                    response.file_content,
                    f"Failed to apply edits to file {file_path}",
                    {"success": False},
                )
        except Exception as e:
            return ToolImplOutput(
                f"Error applying multi-edit: {str(e)}",
                f"Error applying edits to file {file_path}",
                {"success": False},
            )

    def get_tool_start_message(self, tool_input: dict[str, Any]) -> str:
        num_edits = len(tool_input.get("edits", []))
        return f"Applying {num_edits} edits to file {tool_input['file_path']}"

    def _send_file_update(self, file_path: str):
        """Send file update event through message queue if available."""
        if self.message_queue:
            try:
                response = self.filesystem_client.read_file(file_path)
                if response.success:
                    self.message_queue.put_nowait(
                        RealtimeEvent(
                            type=EventType.FILE_EDIT,
                            content={
                                "path": str(file_path),
                                "content": response.file_content,
                                "total_lines": len(response.file_content.splitlines()),
                            },
                        )
                    )
            except Exception as e:
                logger.error(f"Failed to send file update for {file_path}: {e}")


class LSTool(LLMTool):
    """Tool for listing files and directories."""
    
    name = "LS"
    description = """Lists files and directories in a given path. The path parameter must be an absolute path, not a relative path. You can optionally provide an array of glob patterns to ignore with the ignore parameter. You should generally prefer the Glob and Grep tools, if you know which directories to search."""

    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "The absolute path to the directory to list (must be absolute, not relative)",
            },
            "ignore": {
                "type": "array",
                "description": "List of glob patterns to ignore",
                "items": {"type": "string"},
            },
        },
        "required": ["path"],
    }

    def __init__(self, settings: Settings):
        super().__init__()
        self.filesystem_client = FileSystemClient(settings)

    async def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        path = tool_input["path"]
        ignore = tool_input.get("ignore")

        try:
            response = self.filesystem_client.ls(path, ignore)
            
            if response.success:
                return ToolImplOutput(
                    response.file_content,
                    f"Successfully listed directory {path}",
                    {"success": True},
                )
            else:
                return ToolImplOutput(
                    response.file_content,
                    f"Failed to list directory {path}",
                    {"success": False},
                )
        except Exception as e:
            return ToolImplOutput(
                f"Error listing directory: {str(e)}",
                f"Error listing directory {path}",
                {"success": False},
            )

    def get_tool_start_message(self, tool_input: dict[str, Any]) -> str:
        return f"Listing directory {tool_input['path']}"


class GlobTool(LLMTool):
    """Tool for fast file pattern matching."""
    
    name = "Glob"
    description = """- Fast file pattern matching tool that works with any codebase size
- Supports glob patterns like "**/*.js" or "src/**/*.ts"
- Returns matching file paths sorted by modification time
- Use this tool when you need to find files by name patterns
- When you are doing an open ended search that may require multiple rounds of globbing and grepping, use the Agent tool instead
- You have the capability to call multiple tools in a single response. It is always better to speculatively perform multiple searches as a batch that are potentially useful."""

    input_schema = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "The glob pattern to match files against",
            },
            "path": {
                "type": "string",
                "description": "The directory to search in. If not specified, the current working directory will be used. IMPORTANT: Omit this field to use the default directory. DO NOT enter \"undefined\" or \"null\" - simply omit it for the default behavior. Must be a valid directory path if provided.",
            },
        },
        "required": ["pattern"],
    }

    def __init__(self, settings: Settings):
        super().__init__()
        self.filesystem_client = FileSystemClient(settings)

    async def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        pattern = tool_input["pattern"]
        path = tool_input.get("path")

        try:
            response = self.filesystem_client.glob(pattern, path)
            
            if response.success:
                return ToolImplOutput(
                    response.file_content,
                    f"Successfully searched for pattern {pattern}",
                    {"success": True},
                )
            else:
                return ToolImplOutput(
                    response.file_content,
                    f"Failed to search for pattern {pattern}",
                    {"success": False},
                )
        except Exception as e:
            return ToolImplOutput(
                f"Error searching for pattern: {str(e)}",
                f"Error searching for pattern {pattern}",
                {"success": False},
            )

    def get_tool_start_message(self, tool_input: dict[str, Any]) -> str:
        return f"Searching for files matching pattern {tool_input['pattern']}"


class GrepTool(LLMTool):
    """Tool for fast content search."""
    
    name = "Grep"
    description = """
- Fast content search tool that works with any codebase size
- Searches file contents using regular expressions
- Supports full regex syntax (eg. "log.*Error", "function\\s+\\w+", etc.)
- Filter files by pattern with the include parameter (eg. "*.js", "*.{ts,tsx}")
- Returns file paths with at least one match sorted by modification time
- Use this tool when you need to find files containing specific patterns
- If you need to identify/count the number of matches within files, use the Bash tool with `rg` (ripgrep) directly. Do NOT use `grep`.
- When you are doing an open ended search that may require multiple rounds of globbing and grepping, use the Agent tool instead
"""

    input_schema = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "The regular expression pattern to search for in file contents",
            },
            "path": {
                "type": "string",
                "description": "The directory to search in. Defaults to the current working directory.",
            },
            "include": {
                "type": "string",
                "description": "File pattern to include in the search (e.g. \"*.js\", \"*.{ts,tsx}\")",
            },
        },
        "required": ["pattern"],
    }

    def __init__(self, settings: Settings):
        super().__init__()
        self.filesystem_client = FileSystemClient(settings)

    async def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        pattern = tool_input["pattern"]
        path = tool_input.get("path")
        include = tool_input.get("include")

        try:
            response = self.filesystem_client.grep(pattern, path, include)
            
            if response.success:
                return ToolImplOutput(
                    response.file_content,
                    f"Successfully searched for content pattern {pattern}",
                    {"success": True},
                )
            else:
                return ToolImplOutput(
                    response.file_content,
                    f"Failed to search for content pattern {pattern}",
                    {"success": False},
                )
        except Exception as e:
            return ToolImplOutput(
                f"Error searching for content: {str(e)}",
                f"Error searching for content pattern {pattern}",
                {"success": False},
            )

    def get_tool_start_message(self, tool_input: dict[str, Any]) -> str:
        return f"Searching for content matching pattern {tool_input['pattern']}"