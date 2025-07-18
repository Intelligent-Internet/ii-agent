"""Bash tool for executing shell commands."""

import os
import re
import shlex
import signal
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Annotated, Dict, Optional, Tuple

from pydantic import Field, field_validator

from ii_agent.mcp.tools.base import BaseTool
from ii_agent.mcp.tools.constants import DEFAULT_TIMEOUT_MS, MAX_OUTPUT_CHARS, MAX_TIMEOUT_MS


# Banned commands for security reasons
BANNED_COMMANDS = [
    'alias', 'curl', 'curlie', 'wget', 'axel', 'aria2c', 'nc', 'telnet',
    'lynx', 'w3m', 'links', 'httpie', 'xh', 'http-prompt', 'chrome',
    'firefox', 'safari'
]

DESCRIPTION = """Executes a given bash command in a persistent shell session with optional timeout, ensuring proper handling and security measures.

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


class BashToolResult:
    """Result object for bash command execution."""
    
    def __init__(self, stdout: str, stderr: str, exit_code: int, interrupted: bool = False):
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code
        self.interrupted = interrupted
        self.stdout_lines = len(stdout.split('\n')) if stdout else 0
        self.stderr_lines = len(stderr.split('\n')) if stderr else 0


def format_output(content: str) -> Tuple[str, int]:
    """
    Format output content, truncating if necessary.
    
    Returns:
        Tuple of (formatted_content, total_lines)
    """
    total_lines = len(content.split('\n'))
    
    if len(content) <= MAX_OUTPUT_CHARS:
        return content, total_lines
    
    # Truncate from the middle, keeping start and end
    half_length = MAX_OUTPUT_CHARS // 2
    start = content[:half_length]
    end = content[-half_length:]
    
    # Count truncated lines
    truncated_content = content[half_length:-half_length]
    truncated_lines = len(truncated_content.split('\n'))
    
    formatted = f"{start}\n\n... [{truncated_lines} lines truncated] ...\n\n{end}"
    return formatted, total_lines


def split_commands(command: str) -> list[str]:
    """Split a command string into individual commands."""
    # Enhanced split for &&, ;, and | operators
    commands = []
    current = ""
    
    i = 0
    in_quotes = False
    quote_char = None
    
    while i < len(command):
        char = command[i]
        
        if char in ['"', "'"] and not in_quotes:
            in_quotes = True
            quote_char = char
            current += char
        elif char == quote_char and in_quotes:
            in_quotes = False
            quote_char = None
            current += char
        elif not in_quotes and i < len(command) - 1:
            if command[i:i+2] == '&&':
                commands.append(current.strip())
                current = ""
                i += 1  # Skip the next character
            elif char == ';':
                commands.append(current.strip())
                current = ""
            elif char == '|' and command[i+1] != '|':  # Single pipe, not ||
                commands.append(current.strip())
                current = ""
            else:
                current += char
        elif not in_quotes and char == '|' and (i == len(command) - 1 or command[i+1] != '|'):
            # Handle pipe at end or single pipe
            commands.append(current.strip())
            current = ""
        else:
            current += char
        
        i += 1
    
    if current.strip():
        commands.append(current.strip())
    
    return [cmd for cmd in commands if cmd]


class TimeoutProcess:
    """Helper class to handle process execution with timeout."""
    
    def __init__(self, command: str, timeout_ms: int, cwd: Optional[str] = None):
        self.command = command
        self.timeout_ms = timeout_ms
        self.cwd = cwd or os.getcwd()
        self.process: Optional[subprocess.Popen] = None
        self.interrupted = False
        
    def _timeout_handler(self):
        """Handle timeout by terminating the process."""
        time.sleep(self.timeout_ms / 1000.0)
        if self.process and self.process.poll() is None:
            self.interrupted = True
            try:
                # Try graceful termination first
                self.process.terminate()
                time.sleep(0.1)
                if self.process.poll() is None:
                    # Force kill if still running
                    self.process.kill()
            except ProcessLookupError:
                pass  # Process already terminated
                
    def execute(self) -> BashToolResult:
        """Execute the command with timeout."""
        try:
            # Start timeout thread
            timeout_thread = threading.Thread(target=self._timeout_handler)
            timeout_thread.daemon = True
            timeout_thread.start()
            
            # Execute command
            self.process = subprocess.Popen(
                self.command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=self.cwd,
                env=os.environ.copy(),
                preexec_fn=os.setsid  # Create new process group for better cleanup
            )
            
            stdout, stderr = self.process.communicate()
            exit_code = self.process.returncode
            
            # Handle timeout case
            if self.interrupted:
                stderr += "\nCommand execution timed out"
                if exit_code == 0:  # Process was killed, so set appropriate exit code
                    exit_code = 143  # SIGTERM exit code
                    
            return BashToolResult(
                stdout=stdout or "",
                stderr=stderr or "",
                exit_code=exit_code,
                interrupted=self.interrupted
            )
            
        except Exception as e:
            return BashToolResult(
                stdout="",
                stderr=f"Command execution failed: {str(e)}",
                exit_code=1,
                interrupted=self.interrupted
            )


class BashTool(BaseTool):
    """Tool for executing bash commands in a persistent shell session."""
    
    name = "Bash"
    description = DESCRIPTION

    @field_validator('timeout')
    @classmethod
    def validate_timeout(cls, v):
        if v is not None and v > MAX_TIMEOUT_MS:
            raise ValueError(f"Timeout cannot exceed {MAX_TIMEOUT_MS}ms")
        return v

    def _validate_command(self, command: str) -> Tuple[bool, Optional[str]]:
        """
        Validate the command for security and safety.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        commands = split_commands(command)
        
        for cmd in commands:
            # Split command into parts
            try:
                parts = shlex.split(cmd)
            except ValueError:
                # If we can't parse the command, reject it
                return False, f"Invalid command syntax: {cmd}"
                
            if not parts:
                continue
                
            base_cmd = parts[0].lower()
            
            # Check banned commands
            if base_cmd in BANNED_COMMANDS:
                return False, f"Command '{base_cmd}' is not allowed for security reasons"
            
            # Check for dangerous rm commands
            if base_cmd == 'rm' and len(parts) > 1:
                # Check for dangerous rm flags and paths
                for part in parts[1:]:
                    if part.startswith('-') and ('r' in part or 'f' in part):
                        # Check if targeting dangerous paths
                        if any(dangerous_path in cmd for dangerous_path in ['/', '/usr', '/etc', '/var', '/home']):
                            return False, f"Command 'rm' with recursive/force flags targeting system paths is not allowed for security reasons"
                
            # Special validation for cd command
            if base_cmd == 'cd' and len(parts) > 1:
                target_dir = parts[1].strip('\'"')  # Remove quotes
                # Basic path validation - in a real implementation you'd want more sophisticated checks
                if '..' in target_dir or target_dir.startswith('/'):
                    # This is a simplified check - the TypeScript version has more sophisticated directory validation
                    pass
                    
        return True, None

    def run_impl(
        self,
        command: Annotated[str, Field(description="The command to execute")],
        description: Annotated[Optional[str], Field(description="Clear, concise description of what this command does in 5-10 words. Examples:\nInput: ls\nOutput: Lists files in current directory\n\nInput: git status\nOutput: Shows working tree status\n\nInput: npm install\nOutput: Installs package dependencies\n\nInput: mkdir foo\nOutput: Creates directory 'foo'")] = None,
        timeout: Annotated[Optional[int], Field(description="Optional timeout in milliseconds (max 600000)")] = None,
    ) -> Dict:
        """
        Execute a bash command and return the results.
        
        Args:
            command: The command to execute
            description: Optional description of what the command does
            timeout: Optional timeout in milliseconds
            
        Returns:
            Dictionary containing execution results
        """
        # Set default timeout
        if timeout is None:
            timeout = DEFAULT_TIMEOUT_MS
            
        # Validate timeout
        if timeout > MAX_TIMEOUT_MS:
            return {
                "stdout": "",
                "stderr": f"Timeout cannot exceed {MAX_TIMEOUT_MS}ms",
                "exit_code": 1,
                "interrupted": False,
                "stdout_lines": 0,
                "stderr_lines": 1
            }
        
        # Validate command
        is_valid, error_msg = self._validate_command(command)
        if not is_valid:
            return {
                "stdout": "",
                "stderr": error_msg,
                "exit_code": 1,
                "interrupted": False,
                "stdout_lines": 0,
                "stderr_lines": 1
            }
        
        # Execute command
        executor = TimeoutProcess(command, timeout)
        result = executor.execute()
        
        # Format output
        formatted_stdout, stdout_lines = format_output(result.stdout)
        formatted_stderr, stderr_lines = format_output(result.stderr)
        
        # Add exit code to stderr if non-zero
        if result.exit_code != 0:
            if formatted_stderr:
                formatted_stderr += f"\nExit code {result.exit_code}"
            else:
                formatted_stderr = f"Exit code {result.exit_code}"
                stderr_lines += 1
        
        return {
            "stdout": formatted_stdout,
            "stderr": formatted_stderr,
            "exit_code": result.exit_code,
            "interrupted": result.interrupted,
            "stdout_lines": stdout_lines,
            "stderr_lines": stderr_lines,
            "description": description or "Executes a bash command"
        }