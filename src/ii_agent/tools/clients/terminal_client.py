"""Client for terminal operations that can work locally or remotely."""

import logging
from abc import ABC, abstractmethod
from typing import Any
import httpx

from ii_agent.core.config.client_config import ClientConfig
from ii_agent.core.storage.models.settings import Settings
from ii_agent.utils.constants import WorkSpaceMode
from ii_agent.utils.tool_client.manager import SessionResult, PexpectSessionManager

logger = logging.getLogger(__name__)


class TerminalClientBase(ABC):
    """Abstract base class for terminal clients."""

    @abstractmethod
    def create_session(self, session_id: str) -> SessionResult:
        """Create a new terminal session."""
        pass

    @abstractmethod
    def shell_exec(
        self,
        session_id: str,
        command: str,
        exec_dir: str = None,
        timeout: int = 30,
        **kwargs,
    ) -> SessionResult:
        """Execute a shell command in a session."""
        pass

    @abstractmethod
    def shell_view(self, session_id: str) -> SessionResult:
        """Get current view of a shell session."""
        pass

    @abstractmethod
    def shell_wait(self, session_id: str, seconds: int = 30) -> SessionResult:
        """Wait for a shell session to complete current command."""
        pass

    @abstractmethod
    def shell_write_to_process(
        self, session_id: str, input_text: str, press_enter: bool = False
    ) -> SessionResult:
        """Write text to a running process in a shell session."""
        pass

    @abstractmethod
    def shell_kill_process(self, session_id: str) -> SessionResult:
        """Kill the process in a shell session."""
        pass


class LocalTerminalClient(TerminalClientBase):
    """Local implementation using PexpectSessionManager directly."""

    def __init__(self, config: ClientConfig):
        self.config = config
        self.manager = PexpectSessionManager(
            default_shell=self.config.default_shell,
            default_timeout=config.default_timeout,
            cwd=config.cwd,
            use_relative_path=True,
        )

    def create_session(self, session_id: str) -> SessionResult:
        """Create a new terminal session."""
        try:
            session = self.manager.create_session(session_id)
            if session.state.value == "error":
                return SessionResult(
                    success=False, output=f"Failed to create session {session_id}"
                )
            return SessionResult(
                success=True, output=f"Session {session_id} created successfully"
            )
        except Exception as e:
            logger.error(f"Error creating session {session_id}: {e}")
            return SessionResult(
                success=False, output=f"Error creating session: {str(e)}"
            )

    def shell_exec(
        self,
        session_id: str,
        command: str,
        exec_dir: str = None,
        timeout: int = 30,
        **kwargs,
    ) -> SessionResult:
        """Execute a shell command in a session."""
        return self.manager.shell_exec(session_id, command, exec_dir, timeout, **kwargs)

    def shell_view(self, session_id: str) -> SessionResult:
        """Get current view of a shell session."""
        return self.manager.shell_view(session_id)

    def shell_wait(self, session_id: str, seconds: int = 30) -> SessionResult:
        """Wait for a shell session to complete current command."""
        result = self.manager.shell_wait(session_id, seconds)
        # shell_wait returns a string, convert to SessionResult
        if isinstance(result, SessionResult):
            return result
        return SessionResult(success=True, output=result or f"Waited {seconds} seconds")

    def shell_write_to_process(
        self, session_id: str, input_text: str, press_enter: bool = False
    ) -> SessionResult:
        """Write text to a running process in a shell session."""
        return self.manager.shell_write_to_process(session_id, input_text, press_enter)

    def shell_kill_process(self, session_id: str) -> SessionResult:
        """Kill the process in a shell session."""
        return self.manager.shell_kill_process(session_id)


class RemoteTerminalClient(TerminalClientBase):
    """Remote implementation using HTTP API calls."""

    def __init__(self, config: ClientConfig):
        self.config = config
        if not config.server_url:
            raise ValueError("server_url is required for remote mode")
        self.server_url = config.server_url.rstrip("/")
        self.timeout = config.timeout

    def _make_request(self, endpoint: str, data: dict[str, Any]) -> SessionResult:
        """Make an HTTP request to the remote server."""
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    f"{self.server_url}/api/terminal/{endpoint}",
                    json=data,
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()
                result = response.json()
                return SessionResult(
                    success=result.get("success", False),
                    output=result.get("output", ""),
                )
        except httpx.RequestError as e:
            logger.error(f"Request error for {endpoint}: {e}")
            return SessionResult(success=False, output=f"Request error: {str(e)}")
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error for {endpoint}: {e}")
            return SessionResult(
                success=False,
                output=f"HTTP error {e.response.status_code}: {e.response.text}",
            )
        except Exception as e:
            logger.error(f"Unexpected error for {endpoint}: {e}")
            return SessionResult(success=False, output=f"Unexpected error: {str(e)}")

    def create_session(self, session_id: str) -> SessionResult:
        """Create a new terminal session."""
        return self._make_request("create_session", {"session_id": session_id})

    def shell_exec(
        self,
        session_id: str,
        command: str,
        exec_dir: str = None,
        timeout: int = 30,
        **kwargs,
    ) -> SessionResult:
        """Execute a shell command in a session."""
        return self._make_request(
            "shell_exec",
            {
                "session_id": session_id,
                "command": command,
                "exec_dir": exec_dir,
                "timeout": timeout,
                **kwargs,
            },
        )

    def shell_view(self, session_id: str) -> SessionResult:
        """Get current view of a shell session."""
        return self._make_request("shell_view", {"session_id": session_id})

    def shell_wait(self, session_id: str, seconds: int = 30) -> SessionResult:
        """Wait for a shell session to complete current command."""
        return self._make_request(
            "shell_wait", {"session_id": session_id, "seconds": seconds}
        )

    def shell_write_to_process(
        self, session_id: str, input_text: str, press_enter: bool = False
    ) -> SessionResult:
        """Write text to a running process in a shell session."""
        return self._make_request(
            "shell_write_to_process",
            {
                "session_id": session_id,
                "input_text": input_text,
                "press_enter": press_enter,
            },
        )

    def shell_kill_process(self, session_id: str) -> SessionResult:
        """Kill the process in a shell session."""
        return self._make_request("shell_kill_process", {"session_id": session_id})


class TerminalClient:
    """Factory class for creating the appropriate client based on configuration."""

    def __init__(self, settings: Settings):
        self.config = settings.client_config
        if settings.sandbox_config.mode == WorkSpaceMode.LOCAL:
            self._client = LocalTerminalClient(self.config)
        elif (
            settings.sandbox_config.mode == WorkSpaceMode.E2B
            or settings.sandbox_config.mode == WorkSpaceMode.DOCKER
        ):
            self._client = RemoteTerminalClient(self.config)
        else:
            raise ValueError(
                f"Unsupported mode: {self.config.mode}. Must be 'local' or 'remote' or 'e2b'"
            )

    def create_session(self, session_id: str) -> SessionResult:
        """Create a new terminal session."""
        return self._client.create_session(session_id)

    def shell_exec(
        self,
        session_id: str,
        command: str,
        exec_dir: str = None,
        timeout: int = 30,
        **kwargs,
    ) -> SessionResult:
        """Execute a shell command in a session."""
        return self._client.shell_exec(session_id, command, exec_dir, timeout, **kwargs)

    def shell_view(self, session_id: str) -> SessionResult:
        """Get current view of a shell session."""
        return self._client.shell_view(session_id)

    def shell_wait(self, session_id: str, seconds: int = 30) -> SessionResult:
        """Wait for a shell session to complete current command."""
        return self._client.shell_wait(session_id, seconds)

    def shell_write_to_process(
        self, session_id: str, input_text: str, press_enter: bool = False
    ) -> SessionResult:
        """Write text to a running process in a shell session."""
        return self._client.shell_write_to_process(session_id, input_text, press_enter)

    def shell_kill_process(self, session_id: str) -> SessionResult:
        """Kill the process in a shell session."""
        return self._client.shell_kill_process(session_id)
