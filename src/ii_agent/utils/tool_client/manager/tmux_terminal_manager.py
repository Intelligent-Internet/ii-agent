import shlex
import pexpect
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
    EXECUTION_FINISHED_PATTERN = "TMUX_EXECUTION_FINISHED>>"
    EXECUTION_STARTED_PATTERN = "TMUX_EXECUTION_STARTED>>"
    COMMAND_START_PATTERN = """ \\\n&& echo 'TMUX_EXECUTION_FINISHED>>' \\\n&& echo 'TMUX_EXECUTION_STARTED>>' \\\n|| (echo 'TMUX_EXECUTION_FINISHED>>' \\\n&& echo 'TMUX_EXECUTION_STARTED>>')"""
    END_PATTERN = f"\n{EXECUTION_FINISHED_PATTERN}\n{EXECUTION_STARTED_PATTERN}"

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

        self.pexpect_shell, self.pexpect_prompt = self.start_persistent_shell(
            default_shell=default_shell, default_timeout=default_timeout
        )

    def start_persistent_shell(self, default_shell: str, default_timeout: int):
        # Start a new Bash shell
        child = pexpect.spawn(
            default_shell, encoding="utf-8", echo=False, timeout=default_timeout
        )
        custom_prompt = "PEXPECT_PROMPT>> "
        child.sendline("stty -onlcr")
        child.sendline("unset PROMPT_COMMAND")
        child.sendline(f"PS1='{custom_prompt}'")
        child.expect(custom_prompt)
        return child, custom_prompt

    def run_command(self, cmd: str) -> str:
        # Send the command
        self.pexpect_shell.sendline(cmd)
        # Wait until we see the prompt again
        self.pexpect_shell.expect(self.pexpect_prompt)
        # Output is everything printed before the prompt minus the command itself
        # pexpect puts the matched prompt in child.after and everything before it in child.before.
        raw_output = self.pexpect_shell.before.strip()
        ansi_escape = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
        clean_output = ansi_escape.sub("", raw_output)

        if clean_output.startswith("\r"):
            clean_output = clean_output[1:]

        return clean_output

    def is_session_running(self, id: str) -> bool:
        current_view = self.run_command(f"tmux capture-pane -t {id} -p -S - -E -")
        if (
            self.END_PATTERN not in current_view
            and self.COMMAND_START_PATTERN not in current_view
        ):
            return False
        last_output_raw = current_view.strip("\n").split(self.COMMAND_START_PATTERN)[-1]
        return self.END_PATTERN not in last_output_raw

    def get_last_output_raw(self, id: str) -> str:
        current_view = self.run_command(f"tmux capture-pane -t {id} -p -S - -E -")
        shell_sessions = current_view.strip("\n").split(self.COMMAND_START_PATTERN)
        if len(shell_sessions) <= 2:
            return current_view
        else:
            if self.END_PATTERN in shell_sessions[-1]:
                return (
                    current_view.split(self.END_PATTERN)[-2]
                    + self.END_PATTERN
                    + current_view.split(self.END_PATTERN)[-1]
                )
            else:
                return current_view.split(self.END_PATTERN)[-1]

    def process_output(self, output: str) -> str:
        if self.use_relative_path:
            output = output.replace(self.cwd, self.HOME_DIR).replace(
                self.work_dir, self.HOME_DIR
            )
        else:
            output = output
        # Find all occurrences of content between COMMAND_START_PATTERN and END_PATTERN
        pattern = (
            re.escape(self.COMMAND_START_PATTERN)
            + r"(.*?)"
            + re.escape(self.END_PATTERN)
        )

        def truncate_match(match):
            content = match.group(1)
            if len(content) > 5000:
                truncated_content = content[:5000]
                return f"{self.COMMAND_START_PATTERN}\n[Content Truncated] {truncated_content}{self.END_PATTERN}"
            else:
                return match.group(0)

        output = re.sub(pattern, truncate_match, output, flags=re.DOTALL)

        # Remove the markers and the command that marks the execution finished and started
        output = output.replace(self.END_PATTERN, "").replace(
            self.COMMAND_START_PATTERN, ""
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
            # self.run_command(f"tmux send-keys -t {session_id} 'echo \"TMUX_EXECUTION_FINISHED>>\" && echo \"TMUX_EXECUTION_STARTED>>\"' Enter")
            # Disable history expansion to allow string !
            self.run_command("set +H")
            self.run_command(
                f"""tmux send-keys -t {session_id} {shlex.quote("set +H")} Enter"""
            )
            self.run_command(
                f"""tmux send-keys -t {session_id} {shlex.quote("PS2=")} Enter"""
            )
            current_directory = self.run_command(
                f"tmux capture-pane -t {session_id}  -p -S - -E -"
            ).strip("\n")
            self.work_dir = current_directory.split(":")[-1].strip()
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

        wrapped_command = shlex.quote(command + " \\")
        self.run_command(f"""tmux send-keys -t {id} {wrapped_command}  Enter """)
        # TODO: replace with variables
        quoted_command = shlex.quote("&& echo 'TMUX_EXECUTION_FINISHED>>' \\")
        self.run_command(f"""tmux send-keys -t {id} {quoted_command}  Enter""")
        quoted_command = shlex.quote("&& echo 'TMUX_EXECUTION_STARTED>>' \\")
        self.run_command(f"""tmux send-keys -t {id} {quoted_command}  Enter""")
        quoted_command = shlex.quote("|| (echo 'TMUX_EXECUTION_FINISHED>>' \\")
        self.run_command(f"""tmux send-keys -t {id} {quoted_command}  Enter""")
        quoted_command = shlex.quote("&& echo 'TMUX_EXECUTION_STARTED>>')")
        self.run_command(f"""tmux send-keys -t {id} {quoted_command}  Enter""")

        start_time = time.time()
        while self.is_session_running(id) and (time.time() - start_time) < timeout:
            time.sleep(1)

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
            if (
                not self.is_session_running(id) and press_enter
            ):  # Edge case where the llm use this to execute a command
                wrapped_input_text = shlex.quote(input_text + " \\")
                self.run_command(
                    f"""tmux send-keys -t {id} {wrapped_input_text}  Enter """
                )
                # TODO: replace with variables
                quoted_command = shlex.quote("&& echo 'TMUX_EXECUTION_FINISHED>>' \\")
                self.run_command(f"""tmux send-keys -t {id} {quoted_command}  Enter""")
                quoted_command = shlex.quote("&& echo 'TMUX_EXECUTION_STARTED>>' \\")
                self.run_command(f"""tmux send-keys -t {id} {quoted_command}  Enter""")
                quoted_command = shlex.quote("|| (echo 'TMUX_EXECUTION_FINISHED>>' \\")
                self.run_command(f"""tmux send-keys -t {id} {quoted_command}  Enter""")
                quoted_command = shlex.quote("&& echo 'TMUX_EXECUTION_STARTED>>')")
                self.run_command(f"""tmux send-keys -t {id} {quoted_command}  Enter""")
            else:
                self.run_command(
                    f"""tmux send-keys -t {id} {shlex.quote(input_text)} Enter"""
                )

        # Give the process a moment to process the input
        time.sleep(0.1)
        output = self.get_last_output_raw(id)
        start_time = time.time()
        while self.is_session_running(id) and (time.time() - start_time) < 3:
            time.sleep(1)
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
        out = manager.shell_exec("test", command)
        print(out.output)
        command = input("Enter command: ")
    print("Viewing session")
    print("--------------------------------")
    out = manager.shell_view("test")
    print(out.output)
