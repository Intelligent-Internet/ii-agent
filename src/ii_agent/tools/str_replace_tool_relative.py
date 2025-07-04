"""File editing tool.

This completes the implementation specified in Anthropic's blogpost:
https://www.anthropic.com/engineering/swe-bench-sonnet.
"""

from pathlib import Path
from ii_agent.utils.workspace_manager import WorkspaceManager
from ii_agent.llm.message_history import MessageHistory
from ii_agent.tools.base import (
    LLMTool,
    ToolImplOutput,
)
from ii_agent.core.event import EventType, RealtimeEvent
from asyncio import Queue
from typing import Any, Literal, Optional, get_args
import logging

from ii_agent.tools.clients.str_replace_client import (
    StrReplaceClient,
)

logger = logging.getLogger(__name__)

Command = Literal[
    "view",
    "create",
    "str_replace",
    "insert",
    "undo_edit",
]


class ExtendedToolImplOutput(ToolImplOutput):
    @property
    def success(self) -> bool:
        return bool(self.auxiliary_data.get("success", False))


class ToolError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)

    def __str__(self):
        return self.message


class StrReplaceEditorTool(LLMTool):
    name = "str_replace_editor"

    description = """\
Custom editing tool for viewing, creating and editing files\n
* State is persistent across command calls and discussions with the user\n
* If `path` is a file, `view` displays the result of applying `cat -n`. If `path` is a directory, `view` lists non-hidden files and directories up to 2 levels deep\n
* The `create` command cannot be used if the specified `path` already exists as a file\n
* If a `command` generates a long output, it will be truncated and marked with `<response clipped>` \n
* The `undo_edit` command will revert the last edit made to the file at `path`\n
\n
Notes for using the `str_replace` command:\n
* The `old_str` parameter should match EXACTLY one or more consecutive lines from the original file. Be mindful of whitespaces!\n
* If the `old_str` parameter is not unique in the file, the replacement will not be performed. Make sure to include enough context in `old_str` to make it unique\n
* The `new_str` parameter should contain the edited lines that should replace the `old_str`
* Should use absolute paths with respect to the working directory for file operations. If you use relative paths, they will be resolved from the working directory.
"""
    input_schema = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "enum": ["view", "create", "str_replace", "insert", "undo_edit"],
                "description": "The commands to run. Allowed options are: `view`, `create`, `str_replace`, `insert`, `undo_edit`.",
            },
            "file_text": {
                "description": "Required parameter of `create` command, with the content of the file to be created.",
                "type": "string",
            },
            "insert_line": {
                "description": "Required parameter of `insert` command. The `new_str` will be inserted AFTER the line `insert_line` of `path`.",
                "type": "integer",
            },
            "new_str": {
                "description": "Required parameter of `str_replace` command containing the new string. Required parameter of `insert` command containing the string to insert.",
                "type": "string",
            },
            "old_str": {
                "description": "Required parameter of `str_replace` command containing the string in `path` to replace.",
                "type": "string",
            },
            "path": {
                "description": "Path to file or directory.",
                "type": "string",
            },
            "view_range": {
                "description": "Optional parameter of `view` command when `path` points to a file. If none is given, the full file is shown. If provided, the file will be shown in the indicated line number range, e.g. [11, 12] will show lines 11 and 12. Indexing at 1 to start. Setting `[start_line, -1]` shows all lines from `start_line` to the end of the file.",
                "items": {"type": "integer"},
                "type": "array",
            },
        },
        "required": ["command", "path"],
    }

    def __init__(
        self,
        workspace_manager: WorkspaceManager,
        message_queue: Queue | None = None,
        str_replace_client: StrReplaceClient = None,
    ):
        super().__init__()
        self.workspace_manager = workspace_manager
        self.message_queue = message_queue
        self.str_replace_client = str_replace_client

    async def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ExtendedToolImplOutput:
        command = tool_input["command"]
        path = tool_input["path"]
        file_text = tool_input.get("file_text")
        view_range = tool_input.get("view_range")
        old_str = tool_input.get("old_str")
        new_str = tool_input.get("new_str")
        insert_line = tool_input.get("insert_line")

        try:
            _ws_path = self.workspace_manager.container_path(Path(path))
            self.rel_path = str(self.workspace_manager.relative_path(_ws_path))
            validate_path_response = self.str_replace_client.validate_path(
                command, str(_ws_path), display_path=self.rel_path
            )
            if not validate_path_response.success:
                raise ToolError(validate_path_response.file_content)

            root_path = self.workspace_manager.root_path()

            if not self.str_replace_client.is_path_in_directory(
                str(root_path), str(_ws_path)
            ):
                return ExtendedToolImplOutput(
                    f"Path {self.rel_path} is outside the workspace root directory. You can only access files within the workspace root directory.",
                    f"Path {self.rel_path} is outside the workspace root directory. You can only access files within the workspace root directory.",
                    {"success": False},
                )
            if command == "view":
                return self.view(str(_ws_path), view_range)
            elif command == "create":
                if file_text is None:
                    raise ToolError(
                        "Parameter `file_text` is required for command: create"
                    )
                self.write_file(str(_ws_path), file_text)
                return ExtendedToolImplOutput(
                    f"File created successfully at: {self.rel_path}",
                    f"File created successfully at: {self.rel_path}",
                    {"success": True},
                )
            elif command == "str_replace":
                if old_str is None:
                    raise ToolError(
                        "Parameter `old_str` is required for command: str_replace"
                    )
                return self.str_replace(str(_ws_path), old_str, new_str)
            elif command == "insert":
                if insert_line is None:
                    raise ToolError(
                        "Parameter `insert_line` is required for command: insert"
                    )
                if new_str is None:
                    raise ToolError(
                        "Parameter `new_str` is required for command: insert"
                    )
                return self.insert(str(_ws_path), insert_line, new_str)
            elif command == "undo_edit":
                return self.undo_edit(str(_ws_path))
            raise ToolError(
                f"Unrecognized command {command}. The allowed commands for the {self.name} tool are: {', '.join(get_args(Command))}"
            )
        except Exception as e:
            return ExtendedToolImplOutput(
                str(e),  # pyright: ignore[reportAttributeAccessIssue]
                str(e),  # pyright: ignore[reportAttributeAccessIssue]
                {"success": False},
            )

    def view(
        self, path: str, view_range: Optional[list[int]] = None
    ) -> ExtendedToolImplOutput:
        response = self.str_replace_client.view(
            path, view_range, display_path=self.rel_path
        )
        if not response.success:
            return ExtendedToolImplOutput(
                response.file_content,
                response.file_content,
                {"success": False},
            )

        return ExtendedToolImplOutput(
            response.file_content, "Displayed file content", {"success": True}
        )

    def str_replace(
        self, path: str, old_str: str, new_str: str | None
    ) -> ExtendedToolImplOutput:
        """Replace old_str with new_str in content, ignoring indentation."""
        response = self.str_replace_client.str_replace(
            path, old_str, new_str, display_path=self.rel_path
        )
        if not response.success:
            return ExtendedToolImplOutput(
                response.file_content,
                response.file_content,
                {"success": False},
            )

        new_file_response = self.str_replace_client.read_file(
            path, display_path=self.rel_path
        )
        if new_file_response.success:
            self._send_file_update(path, new_file_response.file_content)

        return ExtendedToolImplOutput(
            response.file_content,
            f"The file {self.rel_path} has been edited.",
            {"success": True},
        )

    def insert(
        self, path: str, insert_line: int, new_str: str
    ) -> ExtendedToolImplOutput:
        """Implement the insert command, which inserts new_str at the specified line in the file content."""
        response = self.str_replace_client.insert(
            path, insert_line, new_str, display_path=self.rel_path
        )
        if not response.success:
            return ExtendedToolImplOutput(
                response.file_content,
                response.file_content,
                {"success": False},
            )

        new_file_response = self.str_replace_client.read_file(
            path, display_path=self.rel_path
        )
        if new_file_response.success:
            self._send_file_update(path, new_file_response.file_content)

        return ExtendedToolImplOutput(
            response.file_content,
            "Insert successful",
            {"success": True},
        )

    def undo_edit(self, path: str) -> ExtendedToolImplOutput:
        """Implement the undo_edit command."""

        response = self.str_replace_client.undo_edit(path, display_path=self.rel_path)
        if not response.success:
            return ExtendedToolImplOutput(
                response.file_content,
                response.file_content,
                {"success": False},
            )

        self._send_file_update(path, response.file_content)  # Send update after undo

        return ExtendedToolImplOutput(
            response.file_content,
            "Undo successful",
            {"success": True},
        )

    def read_file(self, path: str):
        """Read the content of a file from a given path; raise a ToolError if an error occurs."""
        response = self.str_replace_client.read_file(path, display_path=self.rel_path)
        if not response.success:
            raise ToolError(response.file_content)
        return response.file_content

    def write_file(self, path: str, file: str):
        """Write the content of a file to a given path; raise a ToolError if an error occurs."""
        response = self.str_replace_client.write_file(
            path, file, display_path=self.rel_path
        )
        if not response.success:
            raise ToolError(response.file_content)
        self._send_file_update(path, file)  # Send update after write

    def get_tool_start_message(self, tool_input: dict[str, Any]) -> str:
        return f"Editing file {tool_input['path']}"

    def _send_file_update(self, path: str, content: str):
        """Send file content update through message queue if available."""
        if self.message_queue:
            self.message_queue.put_nowait(
                RealtimeEvent(
                    type=EventType.FILE_EDIT,
                    content={
                        "path": str(path),
                        "content": content,
                        "total_lines": len(content.splitlines()),
                    },
                )
            )
