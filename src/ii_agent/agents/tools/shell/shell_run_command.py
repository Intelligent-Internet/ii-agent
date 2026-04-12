from ii_agent.agents.tools.base import ToolConfirmationDetails, ToolResult
from ii_agent.agents.tools.sandbox.base import BaseSandboxTool
from ii_agent.agents.sandboxes.shell import ShellBusyError, ShellCommandTimeoutError

DEFAULT_TIMEOUT = 60
MAX_TIMEOUT = 180
MAX_LLM_CONTENT_CHARS = 20000
NAME = "Bash"
DISPLAY_NAME = "Run bash command"
DESCRIPTION = f"""Executes a bash command in a persistent shell session

Usage notes:
- It is very helpful if you write a clear, concise description of what this command does in 5-10 words
- To run multiple commands, join them with ';' or '&&'. Do not use newlines
- For long-running tasks (e.g., deployments), set `wait_for_output` to False and monitor progress with the `BashView` tool
- You can specify an optional timeout in seconds (up to {MAX_TIMEOUT} seconds). If not specified, commands will timeout after {DEFAULT_TIMEOUT} seconds
"""
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "session_name": {
            "type": "string",
            "description": "The name of the session to execute the command in.",
        },
        "command": {"type": "string", "description": "The command to execute."},
        "description": {
            "type": "string",
            "description": "Clear, concise description of what this command does in 5-10 words. Examples:\nInput: ls\nOutput: Lists files in current directory\n\nInput: git status\nOutput: Shows working tree status\n\nInput: npm install\nOutput: Installs package dependencies\n\nInput: mkdir foo\nOutput: Creates directory 'foo'",
        },
        "timeout": {
            "type": "integer",
            "description": f"The timeout for the command in seconds. Maximum is {MAX_TIMEOUT} seconds.",
            "default": DEFAULT_TIMEOUT,
        },
        "wait_for_output": {
            "type": "boolean",
            "description": "If True, wait for the command to finish and return its output (up to the timeout). If False, run in background.",
            "default": True,
        },
    },
    "required": ["session_name", "command", "description"],
}


class ShellRunCommand(BaseSandboxTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = False

    def should_confirm_execute(
        self, tool_input: dict[str, object]
    ) -> ToolConfirmationDetails | bool:
        return ToolConfirmationDetails(
            type="bash",
            message=f"{tool_input['description']} - command: {tool_input['command']}",
        )

    def _truncate_llm_content(self, text: str) -> str:
        if len(text) <= MAX_LLM_CONTENT_CHARS:
            return text
        return f"[truncated]{text[-MAX_LLM_CONTENT_CHARS:]}"

    async def execute(self, tool_input: dict) -> ToolResult:
        session_name = tool_input.get("session_name")
        command = tool_input.get("command")
        timeout = tool_input.get("timeout", DEFAULT_TIMEOUT)
        wait_for_output = tool_input.get("wait_for_output", True)
        sandbox_service = self.get_sandbox_service()
        session_id = self.get_session_id()

        if not command:
            return ToolResult(llm_content="Command is required", is_error=True)

        if not isinstance(timeout, int) or timeout > MAX_TIMEOUT:
            return ToolResult(
                llm_content=f"Timeout must be less than {MAX_TIMEOUT} seconds",
                is_error=True,
            )

        try:
            result = await sandbox_service.run_shell_command(
                session_id,
                session_name,
                command,
                timeout=timeout,
                wait_for_output=wait_for_output,
            )
            return ToolResult(
                llm_content=self._truncate_llm_content(result.clean_output),
                user_display_content=result.ansi_output,
                is_error=False,
            )
        except ShellCommandTimeoutError:
            try:
                current_output = await sandbox_service.get_shell_session_output(
                    session_id,
                    session_name,
                )
                view = current_output.clean_output
                ansi_view = current_output.ansi_output
            except Exception:  # noqa: BLE001
                view = "(no output available)"
                ansi_view = view
            message = f"Command timed out. Current view:\n\n{view}."
            return ToolResult(
                llm_content=self._truncate_llm_content(message),
                user_display_content=(f"Command timed out. Current view:\n\n{ansi_view}."),
                is_error=True,
            )
        except ShellBusyError:
            try:
                current_output = await sandbox_service.get_shell_session_output(
                    session_id,
                    session_name,
                )
                view = current_output.clean_output
                ansi_view = current_output.ansi_output
            except Exception:  # noqa: BLE001
                view = "(no output available)"
                ansi_view = view
            message = (
                "The last command is not finished. Current view:\n\n"
                f"{view}. Use another session or wait for the last command to finish."
            )
            return ToolResult(
                llm_content=self._truncate_llm_content(message),
                user_display_content=(
                    f"The last command is not finished. Current view:\n\n{ansi_view}."
                ),
                is_error=True,
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                llm_content=f"Error running command: {exc}",
                is_error=True,
            )
