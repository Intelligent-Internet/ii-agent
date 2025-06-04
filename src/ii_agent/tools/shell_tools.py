from typing import Any, Optional
from ii_agent.tools.base import (
    ToolImplOutput,
    LLMTool,
)
from ii_agent.llm.message_history import MessageHistory
from ii_agent.tools.terminal_manager import PexpectSessionManager


class ShellExecTool(LLMTool):
    """Tool for executing commands in a shell session"""

    name = "shell_exec"
    description = "Execute commands in a specified shell session. Use for running code, installing packages, or managing files."

    input_schema = {
        "type": "object",
        "properties": {
            "session_id": {
                "type": "string",
                "description": "Unique identifier of the target shell session; automatically creates new session if not exists",
            },
            "command": {
                "type": "string",
                "description": "Shell command to execute",
            },
            "exec_dir": {
                "type": "string",
                "description": "Working directory for command execution (must use absolute path)",
            },
        },
        "required": ["session_id", "command", "exec_dir"],
    }

    def __init__(self, session_manager: PexpectSessionManager):
        super().__init__()
        self.session_manager = session_manager

    def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        session_id = tool_input["session_id"]
        command = tool_input["command"]
        exec_dir = tool_input["exec_dir"]

        result = self.session_manager.shell_exec(
            session_id, command, exec_dir, timeout=30
        )
        if result.success:
            return ToolImplOutput(
                result.output,
                f"Command {command} executed successfully in session {session_id}",
            )
        else:
            return ToolImplOutput(
                result.output,
                f"Failed to execute command {command} in session {session_id}: {result.output}",
            )


class ShellViewTool(LLMTool):
    """Tool for viewing the current state of a shell session"""

    name = "shell_view"
    description = "View the content of a specified shell session. Use for checking command execution results or monitoring output."

    input_schema = {
        "type": "object",
        "properties": {
            "session_id": {
                "type": "string",
                "description": "Unique identifier of the target shell session",
            },
        },
        "required": ["session_id"],
    }

    def __init__(self, session_manager: PexpectSessionManager):
        super().__init__()
        self.session_manager = session_manager

    def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        session_id = tool_input["session_id"]

        result = self.session_manager.shell_view(session_id)
        if result.success:
            return ToolImplOutput(
                result.output,
                f"View of session {session_id} retrieved successfully",
            )
        else:
            return ToolImplOutput(
                result.output,
                f"Failed to retrieve view of session {session_id}: {result.output}",
            )


class ShellWaitTool(LLMTool):
    """Tool for waiting for a specified number of seconds in a shell session"""

    name = "shell_wait"
    description = "Wait for a specified number of seconds in a shell session"
    input_schema = {
        "type": "object",
        "properties": {
            "session_id": {
                "type": "string",
                "description": "Unique identifier of the target shell session",
            },
            "seconds": {
                "type": "number",
                "description": "Number of seconds to wait",
            },
        },
        "required": ["session_id", "seconds"],
    }

    def __init__(self, session_manager: PexpectSessionManager):
        super().__init__()
        self.session_manager = session_manager

    def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        session_id = tool_input["session_id"]
        seconds = tool_input["seconds"]

        result = self.session_manager.shell_wait(session_id, seconds)
        if result.success:
            return ToolImplOutput(
                f"Waited for {seconds} seconds in session {session_id}",
                result.output,
            )
        else:
            return ToolImplOutput(
                f"Failed to wait for {seconds} seconds in session {session_id}: {result.output}",
                result.output,
            )


class ShellKillProcessTool(LLMTool):
    """Tool for killing a process in a shell session"""

    name = "shell_kill_process"
    description = "Terminate a running process in a specified shell session. Use for stopping long-running processes or handling frozen commands."
    input_schema = {
        "type": "object",
        "properties": {
            "session_id": {
                "type": "string",
                "description": "Unique identifier of the target shell session",
            },
        },
        "required": ["session_id"],
    }

    def __init__(self, session_manager: PexpectSessionManager):
        super().__init__()
        self.session_manager = session_manager

    def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        session_id = tool_input["session_id"]
        result = self.session_manager.shell_kill_process(session_id)
        if result.success:
            return ToolImplOutput(
                result.output,
                f"Successfully killed process in session {session_id}",
            )
        else:
            return ToolImplOutput(
                result.output,
                f"Failed to kill process in session {session_id}: {result.output}",
            )


class ShellWriteToProcessTool(LLMTool):
    """Tool for writing to a process in a shell session"""

    name = "shell_write_to_process"
    description = "Write to a process in a specified shell session. Use for interacting with running processes."
    input_schema = {
        "type": "object",
        "properties": {
            "session_id": {
                "type": "string",
                "description": "Unique identifier of the target shell session",
            },
            "input": {
                "type": "string",
                "description": "Text to write to the process",
            },
            "enter": {
                "type": "boolean",
                "description": "Whether to press enter after writing the text",
            },
        },
        "required": ["session_id", "input", "enter"],
    }

    def __init__(self, session_manager: PexpectSessionManager):
        super().__init__()
        self.session_manager = session_manager

    def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        session_id = tool_input["session_id"]
        input_text = tool_input["input"]
        enter = tool_input["enter"]
        result = self.session_manager.shell_write_to_process(
            session_id, input_text, enter
        )
        if result.success:
            return ToolImplOutput(
                result.output,
                f"Successfully wrote to process in session {session_id}",
            )
        else:
            return ToolImplOutput(
                result.output,
                f"Failed to write to process in session {session_id}: {result.output}",
            )

    if __name__ == "__main__":
        session_manager = PexpectSessionManager(container_id="f85f9314eb4b")
        result = session_manager.shell_exec("session_1", "ls", exec_dir="/", timeout=5)
        result = session_manager.shell_view("session_1")
