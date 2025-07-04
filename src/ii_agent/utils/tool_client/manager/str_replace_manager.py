import asyncio
from collections import defaultdict
from pathlib import Path
from typing import Optional, Any
from ..helper.indent_utils import match_indent, match_indent_by_first_line
import subprocess
from .model import StrReplaceResponse, StrReplaceToolError

SNIPPET_LINES: int = 4

TRUNCATED_MESSAGE: str = "<response clipped><NOTE>To save on context only part of this file has been shown to you. You should retry this tool after you have searched inside the file with `grep -n` in order to find the line numbers of what you are looking for.</NOTE>"
# original value from Anthropic code
# MAX_RESPONSE_LEN: int = 16000
MAX_RESPONSE_LEN: int = 200000

EXCLUDED_DIRS = {
    "node_modules",
    "dist",
    "build",
}

exclusion_args = " ".join([f"-not -path '*/{d}/*'" for d in EXCLUDED_DIRS])


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
        raise StrReplaceToolError(
            f"Command '{cmd}' timed out after {timeout} seconds"
        ) from exc


def run_sync_subprocess(cmd: str, timeout: float = 120.0):
    """Run a shell command synchronously using subprocess."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return (
            result.returncode,
            maybe_truncate(result.stdout),
            maybe_truncate(result.stderr),
        )
    except subprocess.TimeoutExpired as exc:
        raise StrReplaceToolError(
            f"Command '{cmd}' timed out after {timeout} seconds"
        ) from exc


def maybe_truncate(content: str, truncate_after: int | None = MAX_RESPONSE_LEN):
    """Truncate content and append a notice if content exceeds the specified length."""
    return (
        content
        if not truncate_after or len(content) <= truncate_after
        else content[:truncate_after] + TRUNCATED_MESSAGE
    )


class StrReplaceManager:
    _file_history = defaultdict(list)
    HOME_DIR = ".WORKING_DIR"  # TODO: Refactor to use constant

    def __init__(
        self,
        ignore_indentation_for_str_replace: bool = False,
        expand_tabs: bool = False,
        use_relative_path: bool = False,
        cwd: str = None,
    ):
        self._file_history = defaultdict(list)
        self.ignore_indentation_for_str_replace = ignore_indentation_for_str_replace
        self.expand_tabs = expand_tabs
        self.use_relative_path = use_relative_path
        self.cwd = cwd

    def _validate_path(self, command: str, path_str: str, display_path: str):
        """
        Check that the path/command combination is valid.
        """
        path = Path(path_str)
        # Check if path exists
        if not path.exists() and command != "create":
            raise StrReplaceToolError(
                f"The path {display_path} does not exist. Please provide a valid path."
            )
        if path.exists() and command == "create":
            content = self._read_file(path, display_path=display_path)
            if content.strip():
                raise StrReplaceToolError(
                    f"File already exists and is not empty at: {display_path}. Cannot overwrite non empty files using command `create`."
                )
        if path.is_dir():
            if command != "view":
                raise StrReplaceToolError(
                    f"The path {display_path} is a directory and only the `view` command can be used on directories"
                )

    def read_file(self, path_str: str, display_path: str = None) -> StrReplaceResponse:
        if display_path is None:
            display_path = path_str
        try:
            path = Path(path_str)
            content = self._read_file(path, display_path)
            return StrReplaceResponse(
                success=True,
                file_content=content,
            )
        except StrReplaceToolError as e:
            return StrReplaceResponse(
                success=False,
                file_content=str(e),
            )

    def _read_file(self, path: Path, display_path: str) -> str:
        try:
            return path.read_text()
        except Exception as e:
            raise StrReplaceToolError(
                f"Ran into {e} while trying to read {display_path}"
            ) from None

    def validate_path(self, command: str, path_str: str, display_path: str = None):
        """
        Check that the path/command combination is valid.
        """
        if display_path is None:
            display_path = path_str
        try:
            self._validate_path(command, path_str, display_path)
            return StrReplaceResponse(
                success=True,
                file_content="",
            )
        except StrReplaceToolError as e:
            return StrReplaceResponse(
                success=False,
                file_content=str(e),
            )

    def view(
        self,
        path_str: str,
        view_range: Optional[list[int]] = None,
        display_path: str = None,
    ):
        if display_path is None:
            display_path = path_str
        try:
            path = Path(path_str)
            if path.is_dir():
                if view_range:
                    raise StrReplaceToolError(
                        "The `view_range` parameter is not allowed when `path` points to a directory."
                    )

                _, stdout, stderr = run_sync_subprocess(
                    rf"find {path} -maxdepth 2 -not -path '*/\.*' {exclusion_args}"
                )
                if not stderr:
                    output = f"Here's the files and directories up to 2 levels deep in {display_path}, excluding hidden items:\n{stdout}\n"
                else:
                    output = f"stderr: {stderr}\nstdout: {stdout}\n"
                if self.use_relative_path:
                    output = output.replace(
                        self.cwd, self.HOME_DIR
                    )  # Quick fix for relative path
                return StrReplaceResponse(
                    success=not stderr,
                    file_content=output,
                )

            file_content = self._read_file(path, display_path)
            file_lines = file_content.split("\n")  # Split into lines
            init_line = 1
            if view_range:
                if len(view_range) != 2 or not all(
                    isinstance(i, int) for i in view_range
                ):
                    raise StrReplaceToolError(
                        "Invalid `view_range`. It should be a list of two integers."
                    )
                n_lines_file = len(file_lines)
                init_line, final_line = view_range
                if init_line < 1 or init_line > n_lines_file:
                    raise StrReplaceToolError(
                        f"Invalid `view_range`: {view_range}. Its first element `{init_line}` should be within the range of lines of the file: {[1, n_lines_file]}"
                    )
                if final_line > n_lines_file:
                    raise StrReplaceToolError(
                        f"Invalid `view_range`: {view_range}. Its second element `{final_line}` should be smaller than the number of lines in the file: `{n_lines_file}`"
                    )
                if final_line != -1 and final_line < init_line:
                    raise StrReplaceToolError(
                        f"Invalid `view_range`: {view_range}. Its second element `{final_line}` should be larger or equal than its first `{init_line}`"
                    )

                if final_line == -1:
                    file_content = "\n".join(file_lines[init_line - 1 :])
                else:
                    file_content = "\n".join(file_lines[init_line - 1 : final_line])

            file_content = self._make_output(
                file_content, display_path, len(file_lines), init_line
            )

            return StrReplaceResponse(
                success=True,
                file_content=file_content,
            )
        except StrReplaceToolError as e:
            return StrReplaceResponse(
                success=False,
                file_content=str(e),
            )

    def str_replace(
        self, path_str: str, old_str: str, new_str: str | None, display_path: str = None
    ) -> StrReplaceResponse:
        if display_path is None:
            display_path = path_str
        try:
            path = Path(path_str)
            if self.ignore_indentation_for_str_replace:
                return self._str_replace_ignore_indent(
                    path, old_str, new_str, display_path
                )
            else:
                return self._str_replace(path, old_str, new_str, display_path)
        except StrReplaceToolError as e:
            return StrReplaceResponse(
                success=False,
                file_content=str(e),
            )

    def _str_replace_ignore_indent(
        self, path: Path, old_str: str, new_str: str | None, display_path: str
    ) -> StrReplaceResponse:
        """Replace old_str with new_str in content, ignoring indentation.

        Finds matches in stripped version of text and uses those line numbers
        to perform replacements in original indented version.
        """
        try:
            if new_str is None:
                new_str = ""

            content = self._read_file(path, display_path)
            if self.expand_tabs:
                content = content.expandtabs()
                old_str = old_str.expandtabs()
                new_str = new_str.expandtabs()

            new_str = match_indent(new_str, content)

            if new_str is None:
                raise StrReplaceToolError(
                    "new_str should not be None after match_indent"
                )

            # Split into lines for processing
            content_lines = content.splitlines()
            stripped_content_lines = [line.strip() for line in content.splitlines()]
            stripped_old_str_lines = [line.strip() for line in old_str.splitlines()]

            # Find all potential starting line matches
            matches = []
            for i in range(
                len(stripped_content_lines) - len(stripped_old_str_lines) + 1
            ):
                is_match = True
                for j, pattern_line in enumerate(stripped_old_str_lines):
                    if j == len(stripped_old_str_lines) - 1:
                        if stripped_content_lines[i + j].startswith(pattern_line):
                            # it's a match but last line in old_str is not the full line
                            # we need to append the rest of the line to new_str
                            new_str += stripped_content_lines[i + j][
                                len(pattern_line) :
                            ]
                        else:
                            is_match = False
                            break
                    elif stripped_content_lines[i + j] != pattern_line:
                        is_match = False
                        break
                if is_match:
                    matches.append(i)

            if not matches:
                raise StrReplaceToolError(
                    f"No replacement was performed, old_str \n ```\n{old_str}\n```\n did not appear in {display_path}."
                )
            if len(matches) > 1:
                # Add 1 to convert to 1-based line numbers for error message
                match_lines = [idx + 1 for idx in matches]
                raise StrReplaceToolError(
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
            if indented_new_str is None:
                raise StrReplaceToolError("indented_new_str should not be None")

            # Create new content by replacing the matched lines
            new_content = [
                *content_lines[:match_start],
                *indented_new_str.splitlines(),
                *content_lines[match_end:],
            ]
            new_content_str = "\n".join(new_content)

            self._file_history[path].append(content)  # Save old content for undo
            self._write_file(path, new_content_str, display_path)

            # Create a snippet of the edited section
            start_line = max(0, match_start - SNIPPET_LINES)
            end_line = match_start + SNIPPET_LINES + new_str.count("\n")
            snippet = "\n".join(new_content[start_line : end_line + 1])

            # Prepare thoe success message
            success_msg = f"The file {display_path} has been edited. "
            success_msg += self._make_output(
                file_content=snippet,
                file_descriptor=f"a snippet of {display_path}",
                total_lines=len(new_content),
                init_line=start_line + 1,
            )
            success_msg += "Review the changes and make sure they are as expected. Edit the file again if necessary."
            return StrReplaceResponse(
                success=True,
                file_content=success_msg,
            )
        except StrReplaceToolError as e:
            return StrReplaceResponse(success=False, file_content=str(e))

    def _str_replace(
        self, path: Path, old_str: str, new_str: str | None, display_path: str
    ) -> StrReplaceResponse:
        try:
            if new_str is None:
                new_str = ""

            content = self._read_file(path, display_path)
            if self.expand_tabs:
                content = content.expandtabs()
                old_str = old_str.expandtabs()
                new_str = new_str.expandtabs()

            if not old_str.strip():
                if content.strip():
                    raise StrReplaceToolError(
                        f"No replacement was performed, old_str is empty which is only allowed when the file is empty. The file {display_path} is not empty."
                    )
                else:
                    # replace the whole file with new_str
                    new_content = new_str
                    self._file_history[path].append(
                        content
                    )  # Save old content for undo
                    self._write_file(path, new_content, display_path)
                    success_msg = f"The file {display_path} has been edited. Here's the new content:\n{new_content}"
                    success_msg += self._make_output(
                        file_content=new_content,
                        file_descriptor=f"{display_path}",
                        total_lines=len(new_content.split("\n")),
                    )
                    success_msg += "Review the changes and make sure they are as expected. Edit the file again if necessary."
                    return StrReplaceResponse(
                        success=True,
                        file_content=success_msg,
                    )

            occurrences = content.count(old_str)

            if occurrences == 0:
                raise StrReplaceToolError(
                    f"No replacement was performed, old_str \n ```\n{old_str}\n```\n did not appear verbatim in {display_path}."
                )
            elif occurrences > 1:
                file_content_lines = content.split("\n")
                lines = [
                    idx + 1
                    for idx, line in enumerate(file_content_lines)
                    if old_str in line
                ]
                raise StrReplaceToolError(
                    f"No replacement was performed. Multiple occurrences of old_str \n ```\n{old_str}\n```\n in lines {lines}. Please ensure it is unique"
                )

            new_content = content.replace(old_str, new_str)
            self._file_history[path].append(content)  # Save old content for undo
            self._write_file(path, new_content, display_path)

            # Create a snippet of the edited section
            replacement_line = content.split(old_str)[0].count("\n")
            start_line = max(0, replacement_line - SNIPPET_LINES)
            end_line = replacement_line + SNIPPET_LINES + new_str.count("\n")
            snippet = "\n".join(new_content.split("\n")[start_line : end_line + 1])

            success_msg = f"The file {display_path} has been edited. "
            success_msg += self._make_output(
                file_content=snippet,
                file_descriptor=f"a snippet of {display_path}",
                total_lines=len(new_content.split("\n")),
                init_line=start_line + 1,
            )
            success_msg += "Review the changes and make sure they are as expected. Edit the file again if necessary."
            return StrReplaceResponse(
                success=True,
                file_content=success_msg,
            )
        except StrReplaceToolError as e:
            return StrReplaceResponse(success=False, file_content=str(e))

    def insert(
        self, path_str: str, insert_line: int, new_str: str, display_path: str = None
    ) -> StrReplaceResponse:
        """Implement the insert command, which inserts new_str at the specified line in the file content."""
        if display_path is None:
            display_path = path_str
        try:
            path = Path(path_str)
            file_text = self._read_file(path, display_path)
            if self.expand_tabs:
                file_text = file_text.expandtabs()
                new_str = new_str.expandtabs()
            file_text_lines = file_text.split("\n")
            n_lines_file = len(file_text_lines)

            if insert_line < 0 or insert_line > n_lines_file:
                raise StrReplaceToolError(
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

            self._file_history[path].append(file_text)
            self._write_file(path, new_file_text, display_path)

            success_msg = f"The file {display_path} has been edited. "
            success_msg += self._make_output(
                file_content=snippet,
                file_descriptor="a snippet of the edited file",
                total_lines=len(new_file_text_lines),
                init_line=max(1, insert_line - SNIPPET_LINES + 1),
            )
            success_msg += "Review the changes and make sure they are as expected (correct indentation, no duplicate lines, etc). Edit the file again if necessary."
            return StrReplaceResponse(
                success=True,
                file_content=success_msg,
            )
        except StrReplaceToolError as e:
            return StrReplaceResponse(success=False, file_content=str(e))

    def undo_edit(self, path_str: str, display_path: str = None) -> StrReplaceResponse:
        """Implement the undo_edit command."""
        if display_path is None:
            display_path = path_str
        try:
            path = Path(path_str)
            if not self._file_history[path]:
                raise StrReplaceToolError(f"No edit history found for {display_path}.")

            old_text = self._file_history[path].pop()
            self._write_file(path, old_text, display_path)
            success_msg = f"Last edit to {display_path} undone successfully.\n"
            success_msg += self._make_output(
                file_content=old_text,
                file_descriptor=display_path,
                total_lines=len(old_text.split("\n")),
            )
            return StrReplaceResponse(
                success=True,
                file_content=success_msg,
            )
        except StrReplaceToolError as e:
            return StrReplaceResponse(success=False, file_content=str(e))

    def write_file(self, path_str: str, file: str, display_path: str = None):
        """Write the content of a file to a given path; raise a StrReplaceToolError if an error occurs."""
        if display_path is None:
            display_path = path_str
        try:
            path = Path(path_str)
            # Save old content before writing new content
            if path.exists():
                old_content = self._read_file(path, display_path)
                self._file_history[path].append(old_content)
            self._write_file(path, file, display_path)
            return StrReplaceResponse(
                success=True,
                file_content=file,
            )
        except StrReplaceToolError as e:
            return StrReplaceResponse(success=False, file_content=str(e))

    def _write_file(self, path: Path, file: str, display_path: str):
        """Write the content of a file to a given path; raise a StrReplaceToolError if an error occurs."""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(file)
        except Exception as e:
            raise StrReplaceToolError(
                f"Ran into {e} while trying to write to {display_path}"
            ) from None

    def is_path_in_directory(self, directory_str: str, path_str: str) -> bool:
        directory = Path(directory_str).resolve()
        path = Path(path_str).resolve()
        try:
            path.relative_to(directory)
            return True
        except ValueError:
            return False

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
        display_path = tool_input.get("display_path", tool_input["path"])
        return f"Editing file {display_path}"
