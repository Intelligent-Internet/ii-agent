"""Bash tool for executing shell commands.

This completes the implementation specified in Anthropic's blogpost:
https://www.anthropic.com/engineering/swe-bench-sonnet.

This tool allows the agent to execute bash commands in a controlled environment.
It provides a simple interface for running shell commands and getting their output.
It also supports command filters for transforming commands before execution.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

import pexpect
import re
from abc import ABC, abstractmethod

from ii_agent.llm.message_history import MessageHistory
from ii_agent.tools.base import LLMTool, ToolImplOutput


def start_persistent_shell(timeout: int):
    # Start a new Bash shell
    child = pexpect.spawn("/bin/bash", encoding="utf-8", echo=False, timeout=timeout)
    # Set a known, unique prompt
    # We use a random string that is unlikely to appear otherwise
    # so we can detect the prompt reliably.
    custom_prompt = "PEXPECT_PROMPT>> "
    child.sendline("stty -onlcr")
    child.sendline("unset PROMPT_COMMAND")
    child.sendline(f"PS1='{custom_prompt}'")
    # Force an initial read until the newly set prompt shows up
    child.expect(custom_prompt)
    return child, custom_prompt


def run_command(child, custom_prompt, cmd):
    # Send the command
    child.sendline(cmd)
    # Wait until we see the prompt again
    child.expect(custom_prompt)
    # Output is everything printed before the prompt minus the command itself
    # pexpect puts the matched prompt in child.after and everything before it in child.before.

    raw_output = child.before.strip()
    ansi_escape = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
    clean_output = ansi_escape.sub("", raw_output)

    if clean_output.startswith("\r"):
        clean_output = clean_output[1:]

    return clean_output


class CommandFilter(ABC):
    """Abstract base class for command filters.

    Command filters transform commands before they are executed.
    They can be used to implement remote execution, sandboxing, etc.
    """

    @abstractmethod
    def filter_command(self, command: str) -> str:
        """Transform a command before execution.

        Args:
            command: The original command

        Returns:
            The transformed command
        """
        pass


class SSHCommandFilter(CommandFilter):
    """Filter that wraps commands for execution over SSH."""

    def __init__(
        self,
        host: str,
        user: Optional[str] = None,
        port: int = 22,
        identity_file: Optional[Path] = None,
    ):
        """Initialize the SSH command filter.

        Args:
            host: Remote host to connect to
            user: Username for SSH connection
            port: SSH port number
            identity_file: Path to SSH identity file
        """
        self.host = host
        self.user = user
        self.port = port
        self.identity_file = identity_file

    def filter_command(self, command: str) -> str:
        """Wrap a command for execution over SSH.

        Args:
            command: Command to execute remotely

        Returns:
            SSH command string
        """
        ssh_parts: List[str] = ["ssh"]

        if self.port != 22:
            ssh_parts.extend(["-p", str(self.port)])

        if self.identity_file:
            ssh_parts.extend(["-i", str(self.identity_file)])

        # Build the host string (user@host or just host)
        host_str = f"{self.user}@{self.host}" if self.user else self.host
        ssh_parts.append(host_str)

        # Wrap the command in quotes and escape any existing quotes
        escaped_cmd = command.replace('"', '\\"')
        ssh_parts.append(f'"{escaped_cmd}"')

        return " ".join(ssh_parts)


class DockerCommandFilter(CommandFilter):
    """Filter that wraps commands for execution in a Docker container."""

    def __init__(
        self,
        container: str,
        user: Optional[str] = None,
    ):
        """Initialize the Docker command filter.

        Args:
            container: Container ID or name
            user: Username to run commands as in the container
        """
        self.container = container
        self.user = user

    def filter_command(self, command: str) -> str:
        """Wrap a command for execution in a Docker container.

        Args:
            command: Command to execute in container

        Returns:
            Docker exec command string
        """
        docker_parts = ["docker", "exec"]

        if self.user:
            docker_parts.extend(["-u", self.user])

        docker_parts.append(self.container)

        # For docker exec, we use the shell to handle command properly
        escaped_cmd = command.replace('"', '\\"')
        docker_parts.extend(["/bin/bash", "-l", "-c", f'"{escaped_cmd}"'])

        return " ".join(docker_parts)


class BashTool(LLMTool):
    """A tool for executing bash commands.

    This tool allows the agent to run shell commands and get their output.
    Commands are executed in a controlled environment with appropriate safeguards.
    Command filters can be added to transform commands before execution.
    """

    name = "bash"
    description = """\
Run commands in a bash shell
* When invoking this tool, the contents of the \"command\" parameter does NOT need to be XML-escaped.
* You don't have access to the internet via this tool.
* You do have access to a mirror of common linux and python packages via apt and pip.
* State is persistent across command calls and discussions with the user.
* To inspect a particular line range of a file, e.g. lines 10-25, try 'sed -n 10,25p /path/to/the/file'.
* Please avoid commands that may produce a very large amount of output.
* Please run long lived commands in the background, e.g. 'sleep 10 &' or start a server in the background."""

    input_schema = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The bash command to run.",
            },
        },
        "required": ["command"],
    }

    def __init__(
        self,
        workspace_root: Optional[Path] = None,
        require_confirmation: bool = True,
        command_filters: Optional[List[CommandFilter]] = None,
        timeout: int = 60,
        additional_banned_command_strs: Optional[List[str]] = None,
    ):
        """Initialize the BashTool.

        Args:
            workspace_root: Root directory of the workspace
            require_confirmation: Whether to require user confirmation before executing commands
            command_filters: Optional list of command filters to apply before execution
        """
        super().__init__()
        self.workspace_root = workspace_root
        self.require_confirmation = require_confirmation
        self.command_filters = command_filters or []
        self.timeout = timeout

        self.banned_command_strs = [
            "git init",
            "git commit",
            "git add",
        ]
        if additional_banned_command_strs is not None:
            self.banned_command_strs.extend(additional_banned_command_strs)

        self.child, self.custom_prompt = start_persistent_shell(timeout=timeout)
        if self.workspace_root:
            run_command(self.child, self.custom_prompt, f"cd {self.workspace_root}")

    def add_command_filter(self, command_filter: CommandFilter) -> None:
        """Add a command filter to the filter chain.

        Args:
            command_filter: The filter to add
        """
        self.command_filters.append(command_filter)

    def apply_filters(self, command: str) -> str:
        """Apply all command filters to a command.

        Args:
            command: The original command

        Returns:
            The transformed command after applying all filters
        """
        filtered_command = command
        for filter in self.command_filters:
            filtered_command = filter.filter_command(filtered_command)
        return filtered_command

    async def run_impl(
        self,
        tool_input: Dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        """Execute a bash command and return its output.

        Args:
            tool_input: Dictionary containing the command to execute
            message_history: Optional dialog messages for context

        Returns:
            ToolImplOutput containing the command output
        """
        original_command = tool_input["command"]

        # Apply all command filters
        command = self.apply_filters(original_command)
        aux_data = {
            "original_command": original_command,
            "executed_command": command,
        }

        # Show the original command in the confirmation prompt
        display_command = original_command
        # If the command was transformed, also show the transformed version
        if command != original_command:
            display_command = f"{original_command}\nTransformed to: {command}"

        for banned_str in self.banned_command_strs:
            if banned_str in command:
                return ToolImplOutput(
                    f"Command not executed due to banned string in command: {banned_str} found in {command}.",
                    f"Command not executed due to banned string in command: {banned_str} found in {command}.",
                    aux_data | {"success": False, "reason": "Banned command"},
                )

        if self.require_confirmation:
            confirmation = input(
                f"Do you want to execute the command: {display_command}? (y/n): "
            )
            if confirmation.lower() != "y":
                return ToolImplOutput(
                    "Command not executed due to lack of user confirmation.",
                    "Command execution cancelled",
                    aux_data | {"success": False, "reason": "User did not confirm"},
                )

        # confirm no bad stuff happened
        try:
            echo_result = run_command(self.child, self.custom_prompt, "echo hello")
            assert echo_result.strip() == "hello"
        except Exception:
            self.child, self.custom_prompt = start_persistent_shell(self.timeout)

        # Execute the command and capture output
        try:
            result = run_command(self.child, self.custom_prompt, command)
        except Exception as e:
            # self.child, self.custom_prompt = start_persistent_shell(self.timeout)
            if "Timeout exceeded." in str(e):
                return ToolImplOutput(
                    "Command timed out. Please try again.",
                    "Command timed out. Please try again.",
                    aux_data | {"success": False},
                )
            return ToolImplOutput(
                f"Error executing command: {str(e)}",
                f"Failed to execute command '{original_command}'",
                aux_data
                | {
                    "success": False,
                    "error": str(e),
                },
            )

        return ToolImplOutput(
            result,
            f"Command '{command}' executed.",
            aux_data | {"success": True},
        )

    def get_tool_start_message(self, tool_input: Dict[str, Any]) -> str:
        """Get a message to display when the tool starts.

        Args:
            tool_input: Dictionary containing the command to execute

        Returns:
            A message describing the command being executed
        """
        return f"Executing bash command: {tool_input['command']}"


def create_bash_tool(
    ask_user_permission: bool = True,
    cwd: Optional[Path] = None,
    command_filters: Optional[List[CommandFilter]] = None,
    additional_banned_command_strs: Optional[List[str]] = None,
) -> BashTool:
    """Create a bash tool for executing bash commands.

    Args:
        ask_user_permission: Whether to ask user permission for commands
        cwd: Default working directory for commands
        command_filters: Optional list of command filters to apply before execution

    Returns:
        BashTool instance configured with the provided parameters
    """
    return BashTool(
        workspace_root=cwd,
        require_confirmation=ask_user_permission,
        command_filters=command_filters,
        additional_banned_command_strs=additional_banned_command_strs,
    )


def create_ssh_bash_tool(
    host: str,
    user: Optional[str] = None,
    port: int = 22,
    identity_file: Optional[Path] = None,
    ask_user_permission: bool = True,
    cwd: Optional[Path] = None,
) -> BashTool:
    """Create a bash tool that executes commands over SSH.

    Args:
        host: Remote host to connect to
        user: Username for SSH connection
        port: SSH port number
        identity_file: Path to SSH identity file
        ask_user_permission: Whether to ask user permission for commands
        cwd: Default working directory for commands

    Returns:
        BashTool instance configured with SSH command filter
    """
    ssh_filter = SSHCommandFilter(
        host=host,
        user=user,
        port=port,
        identity_file=identity_file,
    )

    return create_bash_tool(
        ask_user_permission=ask_user_permission,
        cwd=cwd,
        command_filters=[ssh_filter],
    )


def create_docker_bash_tool(
    container: str,
    user: Optional[str] = None,
    ask_user_permission: bool = True,
    cwd: Optional[Path] = None,
    additional_banned_command_strs: Optional[List[str]] = None,
) -> BashTool:
    """Create a bash tool that executes commands in a Docker container.

    Args:
        container: Container ID or name
        user: Username to run commands as in the container
        ask_user_permission: Whether to ask user permission for commands
        cwd: Default working directory for commands

    Returns:
        BashTool instance configured with Docker command filter
    """
    docker_filter = DockerCommandFilter(
        container=container,
        user=user,
    )

    return create_bash_tool(
        ask_user_permission=ask_user_permission,
        cwd=cwd,
        command_filters=[docker_filter],
        additional_banned_command_strs=additional_banned_command_strs,
    )
