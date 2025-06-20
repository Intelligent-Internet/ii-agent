"""File editing tool.

This completes the implementation specified in Anthropic's blogpost:
https://www.anthropic.com/engineering/swe-bench-sonnet.
"""

import asyncio
from pathlib import Path
from collections import defaultdict
from ii_agent.utils import match_indent, match_indent_by_first_line, WorkspaceManager
from ii_agent.llm.message_history import MessageHistory
from ii_agent.tools.base import (
    LLMTool,
    ToolImplOutput,
)
from ii_agent.llm.base import ToolCallParameters
from ii_agent.core.event import EventType, RealtimeEvent
from asyncio import Queue
from typing import Any, Literal, Optional, get_args
import logging

logger = logging.getLogger(__name__)

Command = Literal[
    "view",
    "create",
    "str_replace",
    "insert",
    "undo_edit",
]


def is_path_in_directory(directory: Path, path: Path) -> bool:
    directory = directory.resolve()
    path = path.resolve()
    try:
        path.relative_to(directory)
        return True
    except ValueError:
        return False


def adjust_parallel_calls(
    tool_calls: list[ToolCallParameters],
) -> list[ToolCallParameters]:
    # sort by putting insert calls before str_replace calls
    # sort insert calls by line number
    tool_calls.sort(
        key=lambda x: (
            x.tool_input.get("command") != "insert",
            x.tool_input.get("insert_line", 0),
        )
    )

    # increment line numbers of insert calls after each insert call
    line_shift = 0
    for tool_call in tool_calls:
        if (
            tool_call.tool_input.get("command") == "insert"
            and "insert_line" in tool_call.tool_input
            and "new_str" in tool_call.tool_input
        ):
            tool_call.tool_input["insert_line"] += line_shift
            line_shift += len(tool_call.tool_input["new_str"].splitlines())
    return tool_calls


# Extend ToolImplOutput to add success property
class ExtendedToolImplOutput(ToolImplOutput):
    @property
    def success(self) -> bool:
        """Get success status from metadata."""
        return bool(self.auxiliary_data.get("success", False))


class ToolError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)

    def __str__(self):
        return self.message


SNIPPET_LINES: int = 4

TRUNCATED_MESSAGE: str = "<response clipped><NOTE>To save on context only part of this file has been shown to you. You should retry this tool after you have searched inside the file with `grep -n` in order to find the line numbers of what you are looking for.</NOTE>"
# original value from Anthropic code
# MAX_RESPONSE_LEN: int = 16000
MAX_RESPONSE_LEN: int = 200000


def maybe_truncate(content: str, truncate_after: int | None = MAX_RESPONSE_LEN):
    """Truncate content and append a notice if content exceeds the specified length."""
    return (
        content
        if not truncate_after or len(content) <= truncate_after
        else content[:truncate_after] + TRUNCATED_MESSAGE
    )


async def run(
    cmd: str,
    timeout: float | None = 120.0,  # seconds
    truncate_after: int | None = MAX_RESPONSE_LEN,
):
    """Run a shell command asynchronously with a timeout."""
    process = await asyncio.create_subprocess_shell(
        cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        return (
            process.returncode or 0,
            maybe_truncate(stdout.decode(), truncate_after=truncate_after),
            maybe_truncate(stderr.decode(), truncate_after=truncate_after),
        )
    except asyncio.TimeoutError as exc:
        try:
            process.kill()
        except ProcessLookupError:
            pass
        raise TimeoutError(
            f"Command '{cmd}' timed out after {timeout} seconds"
        ) from exc


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

    # Track file edit history for undo operations
    _file_history = defaultdict(list)

    def __init__(
        self,
        workspace_manager: WorkspaceManager,
        ignore_indentation_for_str_replace: bool = False,
        expand_tabs: bool = False,
        message_queue: Queue | None = None,
    ):
        super().__init__()
        self.workspace_manager = workspace_manager
        self.ignore_indentation_for_str_replace = ignore_indentation_for_str_replace
        self.expand_tabs = expand_tabs
        self._file_history = defaultdict(list)
        self.message_queue = message_queue

    def _send_file_update(self, path: Path, content: str):
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
            _ws_path = self.workspace_manager.workspace_path(Path(path).absolute())
            self.validate_path(command, _ws_path)

            container_root = self.workspace_manager.container_path(
                self.workspace_manager.root
            )
            if not is_path_in_directory(self.workspace_manager.root, _ws_path):
                return ExtendedToolImplOutput(
                    f"Path {_ws_path} is outside the workspace root directory: {container_root}. You can only access files within the workspace root directory.",
                    f"Path {_ws_path} is outside the workspace root directory: {container_root}. You can only access files within the workspace root directory.",
                    {"success": False},
                )
            if command == "view":
                return await self.view(_ws_path, view_range)
            elif command == "create":
                if file_text is None:
                    raise ToolError(
                        "Parameter `file_text` is required for command: create"
                    )
                self.write_file(_ws_path, file_text)
                self._file_history[_ws_path].append(file_text)
                return ExtendedToolImplOutput(
                    f"File created successfully at: {self.workspace_manager.container_path(path)}",
                    f"File created successfully at: {self.workspace_manager.container_path(path)}",
                    {"success": True},
                )
            elif command == "str_replace":
                if old_str is None:
                    raise ToolError(
                        "Parameter `old_str` is required for command: str_replace"
                    )
                if self.ignore_indentation_for_str_replace:
                    return self._str_replace_ignore_indent(_ws_path, old_str, new_str)
                else:
                    try:
                        return self.str_replace(_ws_path, old_str, new_str)
                    except PermissionError:
                        return ExtendedToolImplOutput(
                            f"The file {path} could not be edited due to lack of permission. Try changing the file permissions.",
                            f"The file {path} could not be edited due to lack of permission. Try changing the file permissions.",
                            {"success": True},
                        )
            elif command == "insert":
                if insert_line is None:
                    raise ToolError(
                        "Parameter `insert_line` is required for command: insert"
                    )
                if new_str is None:
                    raise ToolError(
                        "Parameter `new_str` is required for command: insert"
                    )
                return self.insert(_ws_path, insert_line, new_str)
            elif command == "undo_edit":
                return self.undo_edit(_ws_path)
            raise ToolError(
                f"Unrecognized command {command}. The allowed commands for the {self.name} tool are: {', '.join(get_args(Command))}"
            )
        except Exception as e:
            return ExtendedToolImplOutput(
                e.message,  # pyright: ignore[reportAttributeAccessIssue]
                e.message,  # pyright: ignore[reportAttributeAccessIssue]
                {"success": False},
            )

    def validate_path(self, command: str, path: Path):
        """
        Check that the path/command combination is valid.
        """
        # Check if path exists
        if not path.exists() and command != "create":
            raise ToolError(
                f"The path {path} does not exist. Please provide a valid path."
            )
        if path.exists() and command == "create":
            content = self.read_file(path)
            if content.strip():
                raise ToolError(
                    f"File already exists and is not empty at: {path}. Cannot overwrite non empty files using command `create`."
                )
        # Check if the path points to a directory
        if path.is_dir():
            if command != "view":
                raise ToolError(
                    f"The path {path} is a directory and only the `view` command can be used on directories"
                )

    async def view(
        self, path: Path, view_range: Optional[list[int]] = None
    ) -> ExtendedToolImplOutput:
        if path.is_dir():
            if view_range:
                raise ToolError(
                    "The `view_range` parameter is not allowed when `path` points to a directory."
                )

            _, stdout, stderr = await run(
                rf"find {path} -maxdepth 2 -not -path '*/\.*'"
            )
            if not stderr:
                output = f"Here's the files and directories up to 2 levels deep in {path}, excluding hidden items:\n{stdout}\n"
            else:
                output = f"stderr: {stderr}\nstdout: {stdout}\n"
            return ExtendedToolImplOutput(
                output, "Listed directory contents", {"success": not stderr}
            )

        file_content = self.read_file(path)
        file_lines = file_content.split(
            "\n"
        )  # Split into lines early for total line count
        init_line = 1
        if view_range:
            if len(view_range) != 2 or not all(isinstance(i, int) for i in view_range):
                raise ToolError(
                    "Invalid `view_range`. It should be a list of two integers."
                )
            n_lines_file = len(file_lines)
            init_line, final_line = view_range
            if init_line < 1 or init_line > n_lines_file:
                raise ToolError(
                    f"Invalid `view_range`: {view_range}. Its first element `{init_line}` should be within the range of lines of the file: {[1, n_lines_file]}"
                )
            if final_line > n_lines_file:
                raise ToolError(
                    f"Invalid `view_range`: {view_range}. Its second element `{final_line}` should be smaller than the number of lines in the file: `{n_lines_file}`"
                )
            if final_line != -1 and final_line < init_line:
                raise ToolError(
                    f"Invalid `view_range`: {view_range}. Its second element `{final_line}` should be larger or equal than its first `{init_line}`"
                )

            if final_line == -1:
                file_content = "\n".join(file_lines[init_line - 1 :])
            else:
                file_content = "\n".join(file_lines[init_line - 1 : final_line])

        output = self._make_output(
            file_content=file_content,
            file_descriptor=str(self.workspace_manager.container_path(path)),
            total_lines=len(
                file_lines
            ),  # Use total lines in file, not just the viewed range
            init_line=init_line,
        )
        return ExtendedToolImplOutput(
            output, "Displayed file content", {"success": True}
        )

    def _str_replace_ignore_indent(self, path: Path, old_str: str, new_str: str | None):
        """Replace old_str with new_str in content, ignoring indentation.

        Finds matches in stripped version of text and uses those line numbers
        to perform replacements in original indented version.
        """
        if new_str is None:
            new_str = ""

        content = self.read_file(path)
        if self.expand_tabs:
            content = content.expandtabs()
            old_str = old_str.expandtabs()
            new_str = new_str.expandtabs()

        new_str = match_indent(new_str, content)
        assert new_str is not None, "new_str should not be None after match_indent"

        # Split into lines for processing
        content_lines = content.splitlines()
        stripped_content_lines = [line.strip() for line in content.splitlines()]
        stripped_old_str_lines = [line.strip() for line in old_str.splitlines()]

        # Find all potential starting line matches
        matches = []
        for i in range(len(stripped_content_lines) - len(stripped_old_str_lines) + 1):
            is_match = True
            for j, pattern_line in enumerate(stripped_old_str_lines):
                if j == len(stripped_old_str_lines) - 1:
                    if stripped_content_lines[i + j].startswith(pattern_line):
                        # it's a match but last line in old_str is not the full line
                        # we need to append the rest of the line to new_str
                        new_str += stripped_content_lines[i + j][len(pattern_line) :]
                    else:
                        is_match = False
                        break
                elif stripped_content_lines[i + j] != pattern_line:
                    is_match = False
                    break
            if is_match:
                matches.append(i)

        if not matches:
            raise ToolError(
                f"No replacement was performed, old_str \n ```\n{old_str}\n```\n did not appear in {self.workspace_manager.container_path(path)}."
            )
        if len(matches) > 1:
            # Add 1 to convert to 1-based line numbers for error message
            match_lines = [idx + 1 for idx in matches]
            raise ToolError(
                f"No replacement was performed. Multiple occurrences of old_str \n ```\n{old_str}\n```\n starting at lines {match_lines}. Please ensure it is unique"
            )

        # Get the matching range in the original content
        match_start = matches[0]
        match_end = match_start + len(stripped_old_str_lines)

        # Get the original indented lines
        original_matched_lines = content_lines[match_start:match_end]

        indented_new_str = match_indent_by_first_line(
            new_str, original_matched_lines[0]
        )
        assert indented_new_str is not None, "indented_new_str should not be None"

        # Create new content by replacing the matched lines
        new_content = [
            *content_lines[:match_start],
            *indented_new_str.splitlines(),
            *content_lines[match_end:],
        ]
        new_content_str = "\n".join(new_content)

        self._file_history[path].append(content)  # Save old content for undo
        path.write_text(new_content_str)
        self._send_file_update(path, new_content_str)  # Send update after write

        # Create a snippet of the edited section
        start_line = max(0, match_start - SNIPPET_LINES)
        end_line = match_start + SNIPPET_LINES + new_str.count("\n")
        snippet = "\n".join(new_content[start_line : end_line + 1])

        # Prepare the success message
        success_msg = f"The file {path} has been edited. "
        success_msg += self._make_output(
            file_content=snippet,
            file_descriptor=f"a snippet of {self.workspace_manager.container_path(path)}",
            total_lines=len(new_content),
            init_line=start_line + 1,
        )
        success_msg += "Review the changes and make sure they are as expected. Edit the file again if necessary."

        return ExtendedToolImplOutput(
            success_msg,
            f"The file {path} has been edited.",
            {"success": True},
        )

    def str_replace(
        self, path: Path, old_str: str, new_str: str | None
    ) -> ExtendedToolImplOutput:
        if new_str is None:
            new_str = ""

        content = self.read_file(path)
        if self.expand_tabs:
            content = content.expandtabs()
            old_str = old_str.expandtabs()
            new_str = new_str.expandtabs()

        if not old_str.strip():
            if content.strip():
                raise ToolError(
                    f"No replacement was performed, old_str is empty which is only allowed when the file is empty. The file {path} is not empty."
                )
            else:
                # replace the whole file with new_str
                new_content = new_str
                self._file_history[path].append(content)  # Save old content for undo
                path.write_text(new_content)
                self._send_file_update(path, new_content)  # Send update after write
                # Prepare the success message
                success_msg = f"The file {path} has been edited. "
                success_msg += self._make_output(
                    file_content=new_content,
                    file_descriptor=f"{self.workspace_manager.container_path(path)}",
                    total_lines=len(new_content.split("\n")),
                )
                success_msg += "Review the changes and make sure they are as expected. Edit the file again if necessary."

                return ExtendedToolImplOutput(
                    success_msg,
                    f"The file {path} has been edited.",
                    {"success": True},
                )

        occurrences = content.count(old_str)

        if occurrences == 0:
            raise ToolError(
                f"No replacement was performed, old_str \n ```\n{old_str}\n```\n did not appear verbatim in {path}."
            )
        elif occurrences > 1:
            file_content_lines = content.split("\n")
            lines = [
                idx + 1
                for idx, line in enumerate(file_content_lines)
                if old_str in line
            ]
            raise ToolError(
                f"No replacement was performed. Multiple occurrences of old_str \n ```\n{old_str}\n```\n in lines {lines}. Please ensure it is unique"
            )

        new_content = content.replace(old_str, new_str)
        self._file_history[path].append(content)  # Save old content for undo
        path.write_text(new_content)
        self._send_file_update(path, new_content)  # Send update after write

        # Create a snippet of the edited section
        replacement_line = content.split(old_str)[0].count("\n")
        start_line = max(0, replacement_line - SNIPPET_LINES)
        end_line = replacement_line + SNIPPET_LINES + new_str.count("\n")
        snippet = "\n".join(new_content.split("\n")[start_line : end_line + 1])

        # Prepare the success message
        success_msg = f"The file {path} has been edited. "
        success_msg += self._make_output(
            file_content=snippet,
            file_descriptor=f"a snippet of {self.workspace_manager.container_path(path)}",
            total_lines=len(new_content.split("\n")),
            init_line=start_line + 1,
        )
        success_msg += "Review the changes and make sure they are as expected. Edit the file again if necessary."

        return ExtendedToolImplOutput(
            success_msg,
            f"The file {path} has been edited.",
            {"success": True},
        )

    def insert(
        self, path: Path, insert_line: int, new_str: str
    ) -> ExtendedToolImplOutput:
        """Implement the insert command, which inserts new_str at the specified line in the file content."""
        file_text = self.read_file(path)
        if self.expand_tabs:
            file_text = file_text.expandtabs()
            new_str = new_str.expandtabs()
        file_text_lines = file_text.split("\n")
        n_lines_file = len(file_text_lines)

        if insert_line < 0 or insert_line > n_lines_file:
            raise ToolError(
                f"Invalid `insert_line` parameter: {insert_line}. It should be within the range of lines of the file: {[0, n_lines_file]}"
            )

        new_str_lines = new_str.split("\n")
        new_file_text_lines = (
            file_text_lines[:insert_line]
            + new_str_lines
            + file_text_lines[insert_line:]
        )
        snippet_lines = (
            file_text_lines[max(0, insert_line - SNIPPET_LINES) : insert_line]
            + new_str_lines
            + file_text_lines[insert_line : insert_line + SNIPPET_LINES]
        )

        new_file_text = "\n".join(new_file_text_lines)
        snippet = "\n".join(snippet_lines)

        self.write_file(path, new_file_text)
        self._file_history[path].append(file_text)
        self._send_file_update(path, new_file_text)  # Send update after write

        success_msg = f"The file {path} has been edited. "
        success_msg += self._make_output(
            file_content=snippet,
            file_descriptor="a snippet of the edited file",
            total_lines=len(new_file_text_lines),
            init_line=max(1, insert_line - SNIPPET_LINES + 1),
        )
        success_msg += "Review the changes and make sure they are as expected (correct indentation, no duplicate lines, etc). Edit the file again if necessary."

        return ExtendedToolImplOutput(
            success_msg,
            "Insert successful",
            {"success": True},
        )

    def undo_edit(self, path: Path) -> ExtendedToolImplOutput:
        """Implement the undo_edit command."""
        if not self._file_history[path]:
            raise ToolError(f"No edit history found for {path}.")

        old_text = self._file_history[path].pop()
        self.write_file(path, old_text)
        self._send_file_update(path, old_text)  # Send update after undo

        formatted_file = self._make_output(
            file_content=old_text,
            file_descriptor=str(self.workspace_manager.container_path(path)),
            total_lines=len(old_text.split("\n")),
        )
        output = f"Last edit to {path} undone successfully.\n{formatted_file}"

        return ExtendedToolImplOutput(
            output,
            "Undo successful",
            {"success": True},
        )

    def read_file(self, path: Path):
        """Read the content of a file from a given path; raise a ToolError if an error occurs."""
        try:
            return path.read_text()
        except Exception as e:
            raise ToolError(f"Ran into {e} while trying to read {path}") from None

    def write_file(self, path: Path, file: str):
        """Write the content of a file to a given path; raise a ToolError if an error occurs."""
        try:
            path.write_text(file)
            self._send_file_update(path, file)  # Send update after write
        except Exception as e:
            raise ToolError(f"Ran into {e} while trying to write to {path}") from None

    def _make_output(
        self,
        file_content: str,
        file_descriptor: str,
        total_lines: int,
        init_line: int = 1,
    ):
        """Generate output for the CLI based on the content of a file."""
        file_content = maybe_truncate(file_content)
        if self.expand_tabs:
            file_content = file_content.expandtabs()
        file_content = "\n".join(
            [
                f"{i + init_line:6}\t{line}"
                for i, line in enumerate(file_content.split("\n"))
            ]
        )
        return (
            f"Here's the result of running `cat -n` on {file_descriptor}:\n"
            + file_content
            + "\n"
            + f"Total lines in file: {total_lines}\n"
        )

    def get_tool_start_message(self, tool_input: dict[str, Any]) -> str:
        return f"Editing file {tool_input['path']}"
