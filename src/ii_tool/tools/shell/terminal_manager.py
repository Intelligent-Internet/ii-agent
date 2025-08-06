import libtmux
import time
import shlex
from pathlib import Path

from libtmux._internal.query_list import ObjectDoesNotExist
from libtmux.exc import TmuxSessionExists
from enum import Enum
from abc import ABC, abstractmethod
from typing import List

# This is a marker that indicates the end of the command output
_DEFAULT_TIMEOUT = 30
_POLL_INTERVAL = 0.5
_DEFAULT_PROMPT_PREFIX = "root@sandbox:"
_PROMPT_FORMAT = f"{_DEFAULT_PROMPT_PREFIX}$(pwd)\\$ "
_PREFIX_SESSION_NAME = "II-AGENT-"

# Shell error
class ShellError(Exception):
    pass

class ShellBusyError(ShellError):
    pass

class ShellInvalidSessionNameError(ShellError):
    pass

class ShellSessionNotFoundError(ShellError):
    pass

class ShellSessionExistsError(ShellError):
    pass

class ShellRunDirNotFoundError(ShellError):
    pass

class ShellCommandTimeoutError(ShellError):
    pass

class ShellOperationError(ShellError):
    pass

class SessionState(Enum):
    BUSY = "busy"
    IDLE = "idle"

# Base class for shell managers
class BaseShellManager(ABC):
    @abstractmethod
    def get_all_sessions(self) -> List[str]:
        pass

    @abstractmethod
    def create_session(self, session_name: str, base_dir: str, timeout: int = _DEFAULT_TIMEOUT):
        pass

    @abstractmethod
    def delete_session(self, session_name: str):
        pass

    @abstractmethod
    def run_command(self, session_name: str, command: str, run_dir: str | None = None, timeout: int = _DEFAULT_TIMEOUT, wait_for_output: bool = True):
        pass

    @abstractmethod
    def kill_current_command(self, session_name: str):
        pass

    @abstractmethod
    def get_session_state(self, session_name: str) -> SessionState:
        pass

    @abstractmethod
    def get_session_output(self, session_name: str):
        pass


# Tmux Shell Manager Based on Session
class TmuxSessionManager(BaseShellManager):
    def __init__(self):
        self.server = libtmux.Server()
        # Test server connection
        self.server.sessions
    
    def _validate_directory(self, directory: str) -> str:
        """Validate and normalize directory path."""
        if not directory.strip():
            raise ShellRunDirNotFoundError("Directory path cannot be empty")
        
        try:
            path = Path(directory).resolve()
            if not path.exists():
                raise ShellRunDirNotFoundError(f"Directory does not exist: {directory}")
            if not path.is_dir():
                raise ShellRunDirNotFoundError(f"Path is not a directory: {directory}")
            return str(path)
        except (OSError, RuntimeError) as e:
            raise ShellRunDirNotFoundError(f"Invalid directory path: {e}")
    
    def get_all_sessions(self) -> List[str]:
        return [session.name for session in self.server.sessions if session and session.name]

    def create_session(self, session_name: str, start_directory: str, timeout: int = _DEFAULT_TIMEOUT):
        """Create a new session with the given name and start directory."""
        if not session_name or not session_name.replace('_', '').replace('-', '').isalnum():
            raise ShellInvalidSessionNameError("Invalid session name. Only alphanumeric characters, hyphens, and underscores are allowed.")
        
        start_directory = self._validate_directory(start_directory)
        
        try:
            # Create session with bash shell and maximize the window
            self.server.new_session(session_name, start_directory=start_directory, shell="/bin/bash", x=999, y=999)

            # Customize the prompt for easier getting the state of the session
            pane = self._get_active_pane(session_name)
            pane.send_keys(f"export PS1='{_PROMPT_FORMAT}'; clear")
            self._wait_for_session_idle(session_name, timeout=timeout)

        except TmuxSessionExists:
            raise ShellSessionExistsError(f"Session '{session_name}' already exists")

    def delete_session(self, session_name: str):        
        try:
            session = self.server.sessions.get(name=session_name)
            if not session:
                raise ShellSessionNotFoundError(f"Session '{session_name}' not found")
            session.kill()
        except ObjectDoesNotExist:
            raise ShellSessionNotFoundError(f"Session '{session_name}' not found")

    def get_session_output(self, session_name: str) -> str:
        pane = self._get_active_pane(session_name)

        capture = pane.capture_pane(start="-", end="-")
        if not isinstance(capture, list):
            return ""
        
        full_output = "\n".join(capture)
        
        return full_output

    def get_session_state(self, session_name: str) -> SessionState:        
        pane = self._get_active_pane(session_name)
        current_view = pane.capture_pane(start="-", end="-")
        
        if not isinstance(current_view, list):
            return SessionState.IDLE
            
        last_line = current_view[-1]
        if _DEFAULT_PROMPT_PREFIX in last_line and last_line.endswith("$"):
            return SessionState.IDLE
        return SessionState.BUSY

    def run_command(self, session_name: str, command: str, run_dir: str | None = None, 
                   timeout: int = _DEFAULT_TIMEOUT, wait_for_output: bool = True):        
        # Validate and normalize the run directory
        if run_dir:
            run_dir = self._validate_directory(run_dir)
        
        pane = self._get_active_pane(session_name)

        # Check if session is busy
        if self.get_session_state(session_name) == SessionState.BUSY:
            raise ShellBusyError("Session is busy, the last command is not finished.")

        # Change directory
        if run_dir:
            escaped_dir = shlex.quote(run_dir)
            pane.send_keys(f"cd {escaped_dir}")
            time.sleep(0.1)

        # Clear before running the actual command
        pane.send_keys("clear")
        time.sleep(0.1)

        pane.send_keys(command)
        time.sleep(0.1)

        if wait_for_output:
            self._wait_for_session_idle(session_name, timeout=timeout)

        return self.get_session_output(session_name)

    def kill_current_command(self, session_name: str, timeout: int = _DEFAULT_TIMEOUT):
        """Kill the currently running command in the specified session by sending SIGINT (Ctrl+C)."""
        pane = self._get_active_pane(session_name)

        # Send Ctrl+C to interrupt the current command
        pane.send_keys("C-c")

        self._wait_for_session_idle(session_name, timeout=timeout)

        return self.get_session_output(session_name)

    def _get_active_pane(self, session_name: str) -> libtmux.Pane:
        try:
            session = self.server.sessions.get(name=session_name)
            if not session:
                raise ShellSessionNotFoundError(f"Session '{session_name}' not found")
            
            window = session.active_window
            if not window:
                raise ShellOperationError("No active window found in session")

            pane = window.active_pane
            if not pane:
                raise ShellOperationError("No active pane found in window")
            return pane
        except ObjectDoesNotExist:
            raise ShellSessionNotFoundError(f"Session '{session_name}' not found")

    def _wait_for_session_idle(self, session_name: str, poll_interval: float = _POLL_INTERVAL, timeout: int = _DEFAULT_TIMEOUT):
        """Wait for the session to be idle."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                if self.get_session_state(session_name) == SessionState.IDLE:
                    break
            except ShellSessionNotFoundError:
                raise ShellSessionNotFoundError(f"Session '{session_name}' not found while waiting for idle state")
            time.sleep(poll_interval)
        else:
            raise ShellCommandTimeoutError("Session creation timed out")


# Tmux Shell Manager Based on Window
class TmuxWindowManager(BaseShellManager):
    def __init__(self, chat_session_id: str):
        self.server = libtmux.Server()

        self._default_window_name = "main"
        self.session = self.server.new_session(
            f"{_PREFIX_SESSION_NAME}{chat_session_id}", 
            kill_session=True, 
            shell="/bin/bash", 
            x=999, 
            y=999,
            window_name=self._default_window_name) # default window name
        self._configure_session(self._default_window_name)
    
    def _validate_directory(self, directory: str) -> str:
        """Validate and normalize directory path."""
        if not directory.strip():
            raise ShellRunDirNotFoundError("Directory path cannot be empty")
        
        try:
            path = Path(directory).resolve()
            if not path.exists():
                raise ShellRunDirNotFoundError(f"Directory does not exist: {directory}")
            if not path.is_dir():
                raise ShellRunDirNotFoundError(f"Path is not a directory: {directory}")
            return str(path)
        except (OSError, RuntimeError) as e:
            raise ShellRunDirNotFoundError(f"Invalid directory path: {e}")
    
    def get_all_sessions(self) -> List[str]:
        return [window.name for window in self.session.windows if window and window.name]

    def _configure_session(self, session_name: str, timeout: int = _DEFAULT_TIMEOUT):
        pane = self._get_active_pane(session_name)
        time.sleep(0.1)
        pane.send_keys("C-m")
        time.sleep(0.2)
        pane.send_keys(f"export PS1='{_PROMPT_FORMAT}'; clear")
        self._wait_for_session_idle(session_name, timeout=timeout) # wait for the session to be idle

    def create_session(self, session_name: str, start_directory: str, timeout: int = _DEFAULT_TIMEOUT):
        """Create a new session with the given name and start directory."""
        if not session_name or not session_name.replace('_', '').replace('-', '').isalnum():
            raise ShellInvalidSessionNameError("Invalid session name. Only alphanumeric characters, hyphens, and underscores are allowed.")
        
        start_directory = self._validate_directory(start_directory)
        
        try:
            # Create session with bash shell and maximize the window
            self.session.new_window(window_name=session_name, start_directory=start_directory, attach=True)

            # Customize the prompt for easier getting the state of the session
            self._configure_session(session_name, timeout=timeout)

        except TmuxSessionExists:
            raise ShellSessionExistsError(f"Session '{session_name}' already exists")

    def delete_session(self, session_name: str):        
        try:
            window = self.session.windows.get(name=session_name)
            if not window:
                raise ShellSessionNotFoundError(f"Session '{session_name}' not found")
            window.kill()
        except ObjectDoesNotExist:
            raise ShellSessionNotFoundError(f"Session '{session_name}' not found")

    def get_session_output(self, session_name: str) -> str:
        pane = self._get_active_pane(session_name)

        capture = pane.capture_pane(start="-", end="-")
        if not isinstance(capture, list):
            return ""
        
        full_output = "\n".join(capture)
        
        return full_output

    def get_session_state(self, session_name: str) -> SessionState:        
        pane = self._get_active_pane(session_name)
        current_view = pane.capture_pane(start="-", end="-")
        
        if not isinstance(current_view, list):
            return SessionState.IDLE
            
        last_line = current_view[-1]
        if _DEFAULT_PROMPT_PREFIX in last_line and last_line.endswith("$"):
            return SessionState.IDLE
        return SessionState.BUSY

    def run_command(self, session_name: str, command: str, run_dir: str | None = None, 
                   timeout: int = _DEFAULT_TIMEOUT, wait_for_output: bool = True):        
        # Validate and normalize the run directory
        if run_dir:
            run_dir = self._validate_directory(run_dir)
        
        pane = self._get_active_pane(session_name)

        # Check if session is busy
        if self.get_session_state(session_name) == SessionState.BUSY:
            raise ShellBusyError("Session is busy, the last command is not finished.")

        # Change directory
        if run_dir:
            escaped_dir = shlex.quote(run_dir)
            pane.send_keys(f"cd {escaped_dir}")
            time.sleep(0.1)

        # Clear before running the actual command
        pane.send_keys("clear")
        time.sleep(0.1)

        pane.send_keys(command)
        time.sleep(0.1)

        if wait_for_output:
            self._wait_for_session_idle(session_name, timeout=timeout)

        return self.get_session_output(session_name)

    def write_to_process(self, session_name: str, content: str, press_enter: bool = True):
        pane = self._get_active_pane(session_name)
        pane.send_keys(content, enter=press_enter)
        time.sleep(0.1)

        return self.get_session_output(session_name)

    def kill_current_command(self, session_name: str, timeout: int = _DEFAULT_TIMEOUT):
        """Kill the currently running command in the specified session by sending SIGINT (Ctrl+C)."""
        pane = self._get_active_pane(session_name)

        # Send Ctrl+C to interrupt the current command
        pane.send_keys("C-c")

        self._wait_for_session_idle(session_name, timeout=timeout)

        return self.get_session_output(session_name)

    def _get_active_pane(self, window_name: str) -> libtmux.Pane:
        try:
            window = self.session.windows.get(name=window_name)
            if not window:
                raise ShellSessionNotFoundError(f"Session '{window_name}' not found")
            
            pane = window.active_pane
            if not pane:
                raise ShellOperationError("No active pane found in window")
            return pane
        except ObjectDoesNotExist:
            raise ShellSessionNotFoundError(f"Session '{window_name}' not found")

    def _wait_for_session_idle(self, session_name: str, poll_interval: float = _POLL_INTERVAL, timeout: int = _DEFAULT_TIMEOUT):
        """Wait for the session to be idle."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                if self.get_session_state(session_name) == SessionState.IDLE:
                    break
            except ShellSessionNotFoundError:
                raise ShellSessionNotFoundError(f"Session '{session_name}' not found while waiting for idle state")
            time.sleep(poll_interval)
        else:
            raise ShellCommandTimeoutError("Session creation timed out")