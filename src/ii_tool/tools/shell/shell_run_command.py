from typing import Annotated
from pydantic import Field
from ii_tool.tools.shell.terminal_manager import BaseShellManager, ShellCommandTimeoutError, ShellBusyError

DEFAULT_TIMEOUT = 60

DESCRIPTION = """Executes a given bash command in a persistent shell session with optional timeout, ensuring proper handling and security measures.

Try to avoid shell commands that are likely to require user interaction (e.g. `git rebase -i`). Use non-interactive versions of commands (e.g. `npm init -y` instead of `npm init`) when available, and otherwise remind the user that interactive shell commands are not supported and may cause hangs until canceled by the user.
If you hit a command that requires user interaction, stop and re-run the non-interactive version of the command.

Before executing the command, please follow these steps:

1. Directory Verification:
   - If the command will create new directories or files, first use the LS tool to verify the parent directory exists and is the correct location
   - For example, before running "mkdir foo/bar", first use LS to check that "foo" exists and is the intended parent directory

2. Command Execution:
   - Always quote file paths that contain spaces with double quotes (e.g., cd "path with spaces/file.txt")
   - Examples of proper quoting:
     - cd "/Users/name/My Documents" (correct)
     - cd /Users/name/My Documents (incorrect - will fail)
     - python "/path/with spaces/script.py" (correct)
     - python /path/with spaces/script.py (incorrect - will fail)
   - After ensuring proper quoting, execute the command.
   - Capture the output of the command.

Usage notes:
  - The command argument is required.
  - You can specify an optional timeout in milliseconds (up to 600000ms / 10 minutes). If not specified, commands will timeout after 120000ms (2 minutes).
  - It is very helpful if you write a clear, concise description of what this command does in 5-10 words.
  - If the output exceeds 30000 characters, output will be truncated before being returned to you.
  - VERY IMPORTANT: You MUST avoid using search commands like `find` and `grep`. Instead use Grep, Glob, or Task to search. You MUST avoid read tools like `cat`, `head`, `tail`, and `ls`, and use Read and LS to read files.
  - If you _still_ need to run `grep`, STOP. ALWAYS USE ripgrep at `rg` first, which all users have pre-installed.
  - When issuing multiple commands, use the ';' or '&&' operator to separate them. DO NOT use newlines (newlines are ok in quoted strings).
  - Try to maintain your current working directory throughout the session by using absolute paths and avoiding usage of `cd`. You may use `cd` if the User explicitly requests it.
    <good-example>
    pytest /foo/bar/tests
    </good-example>
    <bad-example>
    cd /foo/bar && pytest tests
    </bad-example>"""

class ShellRunCommand:
    name = "Bash"
    description = DESCRIPTION

    def __init__(self, BaseShellManager: BaseShellManager) -> None:
        self.shell_manager = BaseShellManager

    def run_impl(
        self,
        session_name: Annotated[str, Field(description="The name of the session to execute the command in.")],
        command: Annotated[str, Field(description="The command to execute.")],
        description: Annotated[str, Field(description="Clear, concise description of what this command does in 5-10 words. Examples:\nInput: ls\nOutput: Lists files in current directory\n\nInput: git status\nOutput: Shows working tree status\n\nInput: npm install\nOutput: Installs package dependencies\n\nInput: mkdir foo\nOutput: Creates directory 'foo'")],
        timeout: Annotated[int, Field(description="The timeout for the command in seconds.")] = DEFAULT_TIMEOUT,
        wait_for_output: Annotated[bool, Field(description="Whether to wait for the command to finish and return the output within the timeout. For deployment or long running commands, it is recommended to set this to False and use `ShellView` to get the output.")] = True,
    ):
        all_current_sessions = self.shell_manager.get_all_sessions()
        if session_name not in all_current_sessions:
            return f"Session '{session_name}' is not initialized. Use `ShellInit` to initialize a session. Available sessions: {all_current_sessions}"
            
        try:
            result = self.shell_manager.run_command(session_name, command, timeout=timeout, wait_for_output=wait_for_output)
            return result
        except ShellCommandTimeoutError:
            return "Command timed out"
        except ShellBusyError:
            return f"The last command is not finished. Current view:\n\n{self.shell_manager.get_session_output(session_name)}"