import shlex
import subprocess
import time
import logging
import re
from typing import Dict, Optional
from dataclasses import dataclass

from .model import SessionResult

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class TmuxSession:
    """Represents a tmux terminal session"""

    id: str
    last_command: str = None


class TmuxSessionManager:
    """Session manager for tmux-based terminal sessions"""

    HOME_DIR = ".WORKING_DIR"  # TODO: Refactor to use constant
    START_PATTERN = "\nTMUX_EXECUTION_STARTED>>"
    END_PATTERN = "\nTMUX_EXECUTION_FINISHED>>"
    SPLIT_PATTERN = f"{END_PATTERN}\n{START_PATTERN}\n"
    COMMAND_START_PATTERN = "\n--- Command sent ---\n"

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
        self.sessions: Dict[str, TmuxSession] = {}
        self.use_relative_path = use_relative_path
        self.container_id = container_id
        self.cwd = cwd
        self.work_dir = None

    def run_command(self, cmd: str) -> str:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return result.stdout

    def is_session_running(self, id: str) -> bool:
        current_view = self.run_command(f"tmux capture-pane -t {id} -p -S - -E -")
        last_output_raw = current_view.split(self.SPLIT_PATTERN)[-1]
        return self.COMMAND_START_PATTERN in last_output_raw

    def get_last_output_raw(self, id: str) -> str:
        current_view = self.run_command(f"tmux capture-pane -t {id} -p -S - -E -")
        if self.is_session_running(id):
            return current_view.split(self.SPLIT_PATTERN)[-1]
        else:
            blocks = current_view.split(self.SPLIT_PATTERN)
            if len(blocks) >= 2:
                return blocks[-2] + self.SPLIT_PATTERN + blocks[-1]
            else:
                return blocks[-1]

    def process_output(self, output: str) -> str:
        if self.use_relative_path:
            output = output.replace(self.cwd, self.HOME_DIR).replace(
                self.work_dir, self.HOME_DIR
            )
        else:
            output = output
        pattern = (
            re.escape(self.COMMAND_START_PATTERN)
            + r"(.*?)"
            + re.escape(self.END_PATTERN)
        )

        def truncate_match(match):
            content = match.group(1)
            if len(content) > 5000:
                truncated_content = content[-5000:]
                return f"{self.COMMAND_START_PATTERN}\n[Content Truncated] {truncated_content}{self.END_PATTERN}"
            else:
                return match.group(0)

        output = re.sub(pattern, truncate_match, output, flags=re.DOTALL)

        # Remove the markers and the command that marks the execution finished and started
        output = (
            output.replace(self.END_PATTERN + "\n", "")
            .replace(self.START_PATTERN + "\n", "")
            .replace(self.COMMAND_START_PATTERN + "\n", "")
            .strip("\n")
        )
        return output

    def create_session(self, session_id: str, start_dir: str = None) -> TmuxSession:
        """
        Create a new terminal session

        Args:
            session_id: Optional custom session ID

        Returns:
            Session ID string
        """
        session = TmuxSession(
            id=session_id,
        )
        try:
            self.run_command(
                f"tmux new-session -d -s {session_id} -c {start_dir} -x 100  /bin/bash"
            )
            # Disable history expansion to allow string !
            self.run_command("set +H")
            self.run_command(
                f"""tmux send-keys -t {session_id} {shlex.quote("set +H")} Enter"""
            )
            quoted_ps1 = shlex.quote(f"PS1='{self.START_PATTERN}\n\\u@\\h:\\w\\$  '")
            self.run_command(f"""tmux send-keys -t {session_id} {quoted_ps1} Enter""")
            self.run_command(
                f"""tmux send-keys -t {session_id} {shlex.quote("PS2=")} Enter"""
            )
            bash_setup = f"""
command_chain_active=false

capture_and_show() {{
    if [[ $BASH_COMMAND != $PROMPT_COMMAND && $BASH_COMMAND != "capture_and_show" ]]; then
        if [[ "$command_chain_active" == false ]]; then
            echo "{self.COMMAND_START_PATTERN}"
            command_chain_active=true
        fi
    fi
}}

reset_and_end() {{
    command_chain_active=false
    echo "{self.END_PATTERN}"
}}
trap 'capture_and_show' DEBUG
PROMPT_COMMAND='reset_and_end'
"""
            self.run_command(
                f"""tmux send-keys -t {session_id} {shlex.quote(bash_setup)} Enter"""
            )
            # Clear tmux history
            self.run_command(f"tmux send-keys -t {session_id} 'clear' Enter")
            while self.is_session_running(session_id):
                time.sleep(0.1)
            self.run_command(f"tmux clear-history -t {session_id}:0")

            current_directory = (
                self.run_command(f"tmux capture-pane -t {session_id}  -p -S - -E -")
                .split(self.SPLIT_PATTERN)[-1]
                .strip("\n")
            )

            # Wrong working directory: Fix it
            self.work_dir = current_directory.split(":")[-1].strip()[:-1]
            self.sessions[session_id] = session
        except Exception as e:
            logger.error(f"Error initializing session {session.id}: {e}")
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
            session = self.create_session(id, start_dir=self.cwd)

        if self.is_session_running(id):
            previous_output = self.get_last_output_raw(id)
            previous_output = self.process_output(previous_output)
            return SessionResult(
                success=False,
                output=f"Previous command {session.last_command} is still running. Ensure it's done or run on a new session.\n{previous_output}",
            )

        wrapped_command = shlex.quote(command)
        self.run_command(f"""tmux send-keys -t {id} {wrapped_command}  Enter """)
        session.last_command = command

        start_time = time.time()
        while self.is_session_running(id) and (time.time() - start_time) < timeout:
            time.sleep(0.1)

        output = self.get_last_output_raw(id)
        output = self.process_output(output)
        if (time.time() - start_time) >= timeout:
            return SessionResult(
                success=False,
                output=f"Command {command} still running after {timeout} seconds. Output so far:\n{output}",
            )

        return SessionResult(success=True, output=output)

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
        try:
            if not self.sessions.get(id):
                return SessionResult(success=False, output=f"Session {id} not found")
            shell_view = self.run_command(f"tmux capture-pane -t {id} -p -S - -E -")
            shell_view = self.process_output(shell_view)
            return SessionResult(success=True, output=shell_view)
        except Exception as e:
            return SessionResult(
                success=False, output=f"Error viewing session {id}: {e}"
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
            return SessionResult(success=False, output=f"Session {id} not found")
        time.sleep(seconds)
        last_output = self.get_last_output_raw(id)
        last_output = self.process_output(last_output)
        return SessionResult(
            success=True,
            output=f"Finished waiting for {seconds} seconds. Previous execution view:\n {last_output}",
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

        if not press_enter:
            self.run_command(f"""tmux send-keys -t {id} {shlex.quote(input_text)} """)
        else:
            self.run_command(
                f"""tmux send-keys -t {id} {shlex.quote(input_text)} Enter"""
            )

        # Give the process a moment to process the input
        time.sleep(0.1)
        output = self.get_last_output_raw(id)
        start_time = time.time()
        while self.is_session_running(id) and (time.time() - start_time) < 3:
            time.sleep(0.1)
            output = self.get_last_output_raw(id)

        output = self.process_output(output)
        return SessionResult(
            success=True,
            output=output,
        )

    def shell_kill_process(self, id: str) -> SessionResult:
        self.run_command(f"tmux kill-session -t {id}")
        if id in self.sessions:
            self.sessions.pop(id)
        return SessionResult(success=True, output=f"Killed session {id}")


if __name__ == "__main__":
    manager = TmuxSessionManager()
    manager.shell_kill_process("test")
    command = "pwd"
    manager.shell_exec("test", "pwd")
    while True and command != "exit":
        out = manager.shell_exec("test", command, timeout=5)
        print(out.output)
        command = input("Enter command: ")
    print("Viewing session")
    print("--------------------------------")
    out = manager.shell_view("test")
    print(out.output)
