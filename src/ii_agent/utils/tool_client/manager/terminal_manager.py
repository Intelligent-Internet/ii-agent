import pexpect
import time
import logging
import re
from typing import Dict, Optional, List
from dataclasses import dataclass, field
from enum import Enum

from .model import SessionResult

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SessionState(Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"
    READY = "ready"
    IDLE = "idle"


@dataclass
class PexpectSession:
    """Represents a pexpect terminal session"""

    id: str
    child: Optional[pexpect.spawn] = None
    state: SessionState = SessionState.IDLE
    last_command: str = None
    history: List[str] = field(default_factory=list)
    current_directory: str = None


class PexpectSessionManager:
    """Session manager for pexpect-based terminal sessions"""

    HOME_DIR = ".WORKING_DIR"  # TODO: Refactor to use constant

    def __init__(
        self,
        default_shell: str = "/bin/bash",
        default_timeout: int = 10,
        cwd: str = None,
        container_id: Optional[str] = None,
        use_relative_path: bool = False,
    ):
        self.default_shell = default_shell
        self.default_timeout = default_timeout
        self.sessions: Dict[str, PexpectSession] = {}
        self.use_relative_path = use_relative_path
        self.work_dir = None
        self.prompt_setup = (
            'export PS1="[CMD_BEGIN]\\n\\u@\\h:\\w\\n[CMD_END]"; export PS2=""'
        )
        self.start_pattern = r"\[CMD_BEGIN\]"
        self.end_pattern = r"\[CMD_END\]"
        self.base_cmd = None
        self.container_id = container_id
        self.cwd = cwd
        # ANSI escape sequence regex pattern
        self.ansi_escape = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")

    def _clean_ansi_escape_sequences(self, text: str) -> str:
        """Remove ANSI escape sequences from text"""
        clean_text = self.ansi_escape.sub("", text)
        # Remove carriage return if it's at the beginning
        if clean_text.startswith("\r"):
            clean_text = clean_text[1:]
        return clean_text

    def _extract_current_directory_from_prompt(
        self, prompt_output: str
    ) -> Optional[str]:
        """Extract current directory from the new prompt after command execution"""
        lines = prompt_output.split("[CMD_BEGIN]")
        out = lines[1].replace("\n", "").replace("\r", "")
        return out

    def _format_output(
        self,
        raw_output: str,
        command: str,
        session: PexpectSession,
        timeout: int,
        view: bool = False,
    ) -> str:
        formated_output = self._format_output_raw(
            raw_output, command, session, timeout, view
        )
        if self.use_relative_path:
            return formated_output.replace(self.cwd, self.HOME_DIR).replace(
                self.work_dir, self.HOME_DIR
            )
        else:
            return formated_output

    def _format_output_raw(
        self,
        raw_output: str,
        command: str,
        session: PexpectSession,
        timeout: int,
        view=False,
    ) -> str:
        """
        Format the raw output from pexpect session

        Args:
            raw_output: Raw output from pexpect child.before
            command: The command that was executed
            session: The PexpectSession object
            timeout: Timeout value used for timeout message
            view: Whether this is called from shell_view (unused in current implementation)

        Returns:
            Formatted output string
        """
        # Clean ANSI escape sequences from raw output
        raw_output = self._clean_ansi_escape_sequences(raw_output)

        # Split the raw output to separate command output from the new prompt
        new_directory = None
        if "[CMD_BEGIN]" in raw_output:
            # Split at [CMD_BEGIN] to separate output from new directory info
            parts = raw_output.split("[CMD_BEGIN]")
            command_output = parts[0].strip()

            # Extract new directory from the part after [CMD_BEGIN]
            if len(parts) > 1:
                new_directory = parts[1].replace("\n", "").replace("\r", "").strip()
        else:
            # If no [CMD_BEGIN] found, it means the process timed out
            command_output = raw_output.strip()

            # Remove the echoed command from the beginning of output if present
            lines = command_output.split("\n")
            if lines and lines[0].strip() == command.strip():
                # Remove the first line (echoed command)
                command_output = "\n".join(lines[1:])

            # Truncate to last 5000 characters
            if len(command_output) > 5000:
                command_output = "[Content Truncated]" + command_output[-5000:]

            # Format timeout message
            formatted_command = f"{session.current_directory}$ {command}"
            if view:
                timeout_message = "Process running. Output so far:"
            else:
                timeout_message = f"The command is still running after {timeout} seconds. Output so far:"

            if command_output:
                return f"{formatted_command}\n{timeout_message}\n{command_output}"
            else:
                return f"{formatted_command}\n{timeout_message}"

        # Normal case - command completed successfully
        # Remove the echoed command from the beginning of output if present
        lines = command_output.split("\n")
        if lines and lines[0].strip() == command.strip():
            # Remove the first line (echoed command)
            command_output = "\n".join(lines[1:])

        # Truncate to last 5000 characters
        if len(command_output) > 5000:
            command_output = "[Content Truncated]" + command_output[-5000:]

        # Format: current_dir + command, then output
        formatted_command = f"{session.current_directory}$ {command}"
        if new_directory:
            if self.use_relative_path:
                session.current_directory = new_directory.replace(
                    self.cwd, self.HOME_DIR
                ).replace(self.work_dir, self.HOME_DIR)
            else:
                session.current_directory = new_directory

        if command_output:
            return f"{formatted_command}\n{command_output}"
        else:
            return formatted_command

    def _execute_command_in_session(
        self, session: PexpectSession, command: str, timeout: int
    ) -> bool:
        try:
            session.child.sendline(command)
            session.last_command = command
            session.state = SessionState.RUNNING
            session.child.expect(self.end_pattern, timeout=timeout)
            session.state = SessionState.COMPLETED
            raw_output = session.child.before
            formatted_output = self._format_output(
                raw_output, command, session, timeout
            )
            session.history.append(formatted_output)
            session.state = SessionState.COMPLETED
            return SessionResult(
                success=True,
                output=formatted_output + f"\n{session.current_directory}$",
            )
        except pexpect.TIMEOUT:
            session.state = SessionState.RUNNING
            raw_output = session.child.before
            formatted_output = self._format_output(
                raw_output, command, session, timeout
            )
            return SessionResult(success=False, output=formatted_output)
        except pexpect.EOF as e:
            return SessionResult(success=False, output=f"Shell process ended: {str(e)}")

    def create_session(self, session_id: str) -> PexpectSession:
        """
        Create a new terminal session

        Args:
            session_id: Optional custom session ID

        Returns:
            Session ID string
        """
        session = PexpectSession(
            id=session_id,
        )
        try:
            if self.container_id:
                # Create persistent shell session inside Docker container
                docker_cmd = f"docker exec -it {self.container_id} {self.default_shell}"
                if self.cwd:
                    docker_cmd += f" -c {self.cwd}"
                child = pexpect.spawn(
                    docker_cmd,
                    encoding="utf-8",
                    echo=False,
                    timeout=self.default_timeout,
                )
            else:
                # Create local shell session
                child = pexpect.spawn(
                    self.default_shell,
                    encoding="utf-8",
                    echo=False,
                    timeout=self.default_timeout,
                    cwd=self.cwd,
                )

            time.sleep(0.2)
            prompt_setup = self.prompt_setup
            if not self.container_id:
                child.sendline(prompt_setup)
                child.expect(self.end_pattern, timeout=self.default_timeout)
            else:
                child.expect(self.end_pattern, timeout=self.default_timeout)
            current_directory = self._extract_current_directory_from_prompt(
                child.before
            )
            self.work_dir = current_directory.split(":")[-1].strip()
            if self.use_relative_path:
                session.current_directory = current_directory.replace(
                    self.cwd, self.HOME_DIR
                ).replace(self.work_dir, self.HOME_DIR)
            else:
                session.current_directory = current_directory

            session.child = child
            self.sessions[session_id] = session
            session.state = SessionState.READY
            # self.shell_exec(session_id, "export TERM=xterm-256color")
        except Exception as e:
            logger.error(f"Error initializing session {session.id}: {e}")
            session.state = SessionState.ERROR
        return session

    def shell_exec(
        self, id: str, command: str, exec_dir: str = None, timeout=30, **kwargs
    ) -> SessionResult:
        """
        Execute a shell command in a session

        Args:
            id: Session identifier
            command: Command to execute
            exec_dir: Working directory for command execution
            timeout: Timeout for command execution
            kwargs: Additional keyword arguments

        Returns: SessionResult containing execution result and current view
            output: root@host: previous_dir$ command\noutput\nroot@host: current_dir$
            success: True or False
        """
        if exec_dir:
            command = f"cd {exec_dir} && {command}"
        session = self.sessions.get(id)
        if not session:
            session = self.create_session(id)

        if session.state == SessionState.RUNNING:
            try:
                session.child.expect(self.end_pattern, timeout=1)
                session.state = SessionState.COMPLETED
                final_output = session.child.before
                formatted_output = self._format_output(
                    final_output, session.last_command, session, 1
                )
                session.history.append(formatted_output)
            except pexpect.exceptions.TIMEOUT:
                session.state = SessionState.RUNNING
                raw_output = session.child.before
                formatted_output = self._format_output(
                    raw_output, session.last_command, session, 1, True
                )
                return SessionResult(
                    success=False,
                    output=f"Previous command {session.last_command} is still running. Ensure it's done or run on a new session.\n{formatted_output}",
                )

        while (
            session.state != SessionState.READY
            and session.state != SessionState.COMPLETED
        ):
            time.sleep(0.1)
            session = self.sessions.get(id)
            if not session:
                return SessionResult(success=False, output=f"Session {id} not ready")

        return self._execute_command_in_session(session, command, timeout)

    def shell_view(self, id: str) -> SessionResult:
        """
        Get current view of a shell session

        Args:
            id: Session identifier

        Returns:
            SessionResult containing current view of shell history
            output: Full view of shell history concatenated with current directory
            success: True or False
        """
        session = self.sessions.get(id)
        if not session:
            return SessionResult(success=False, output=f"Session {id} not found")

        if (
            session.state == SessionState.COMPLETED
            or session.state == SessionState.READY
        ):
            return SessionResult(
                success=True,
                output="\n".join(session.history) + f"\n{session.current_directory}$",
            )
        else:
            try:
                session.child.expect(self.end_pattern, timeout=1)
                session.state = SessionState.COMPLETED
                final_output = session.child.before
                formatted_output = self._format_output(
                    final_output, session.last_command, session, 1
                )
                session.history.append(formatted_output)
                return SessionResult(
                    success=True,
                    output="\n".join(session.history)
                    + f"\n{session.current_directory}$",
                )
            except pexpect.exceptions.TIMEOUT:
                session.state = SessionState.RUNNING
                raw_output = session.child.before
                formatted_output = self._format_output(
                    raw_output, session.last_command, session, 1, True
                )
                return SessionResult(
                    success=True, output="\n".join(session.history + [formatted_output])
                )

    def shell_wait(self, id: str, seconds: int = 30) -> str:
        """
        Wait for a shell session to complete current command

        Args:
            id: Session identifier
            seconds: Maximum seconds to wait

        Returns:
            Dict containing final session state
        """
        session = self.sessions.get(id)
        if not session:
            return
        time.sleep(seconds)
        return SessionResult(
            success=True, output=f"Finished waiting for {seconds} seconds"
        )

    def shell_write_to_process(
        self, id: str, input_text: str, press_enter: bool = False
    ) -> SessionResult:
        """
        Write text to a running process in a shell session

        Args:
            id: Session identifier
            input_text: Text to write to the process
            press_enter: Whether to press enter after writing the text

        Returns:
            SessionResult containing success status and output
        """
        session = self.sessions.get(id)
        if not session:
            return SessionResult(success=False, output=f"Session {id} not found")

        if not session.child:
            return SessionResult(
                success=False, output=f"No active process in session {id}"
            )

        try:
            # Write the input text to the process
            if press_enter:
                session.child.sendline(input_text)
            else:
                session.child.send(input_text)

            # Give the process a moment to process the input
            time.sleep(0.1)
            session.child.expect(self.end_pattern, timeout=3)
            session.state = SessionState.COMPLETED
            final_output = session.child.before
            formatted_output = self._format_output(
                final_output, session.last_command, session, 3
            )
            session.history.append(formatted_output)

            return SessionResult(
                success=True,
                output=formatted_output + f"\n{session.current_directory}$",
            )

        except pexpect.exceptions.TIMEOUT:
            session.state = SessionState.RUNNING
            raw_output = session.child.before
            formatted_output = self._format_output(
                raw_output, session.last_command, session, 3
            )
            return SessionResult(success=False, output=formatted_output)

    def shell_kill_process(self, id: str) -> SessionResult:
        if id not in self.sessions:
            return SessionResult(success=False, output=f"Session {id} not found")
        session = self.sessions[id]
        if session.child:
            try:
                session.child.kill(9)  # SIGKILL
                session.child.close()
                session.child = None
                self.sessions.pop(id)
            except Exception as e:
                logger.error(f"Error killing process in session {id}: {str(e)}")
                return SessionResult(
                    success=False, output=f"Error killing process: {str(e)}"
                )
        return SessionResult(success=True, output=f"Killed process in session {id}")
