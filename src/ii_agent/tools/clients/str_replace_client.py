"""Client for string replacement operations that can work locally or remotely."""

import logging
from abc import ABC, abstractmethod
from typing import Optional, Any
import httpx

from ii_agent.core.config.client_config import ClientConfig
from ii_agent.core.storage.models.settings import Settings
from ii_agent.utils.constants import WorkSpaceMode
from ii_agent.utils.tool_client.manager import StrReplaceResponse, StrReplaceManager

logger = logging.getLogger(__name__)


class StrReplaceClientBase(ABC):
    """Abstract base class for string replacement clients."""

    @abstractmethod
    def validate_path(
        self, command: str, path_str: str, display_path: str = None
    ) -> StrReplaceResponse:
        """Validate that the path/command combination is valid."""
        pass

    @abstractmethod
    def view(
        self,
        path_str: str,
        view_range: Optional[list[int]] = None,
        display_path: str = None,
    ) -> StrReplaceResponse:
        """View file or directory contents."""
        pass

    @abstractmethod
    def str_replace(
        self, path_str: str, old_str: str, new_str: str | None, display_path: str = None
    ) -> StrReplaceResponse:
        """Replace old_str with new_str in the file."""
        pass

    @abstractmethod
    def insert(
        self, path_str: str, insert_line: int, new_str: str, display_path: str = None
    ) -> StrReplaceResponse:
        """Insert new_str after the specified line."""
        pass

    @abstractmethod
    def undo_edit(self, path_str: str, display_path: str = None) -> StrReplaceResponse:
        """Undo the last edit to the file."""
        pass

    @abstractmethod
    def read_file(self, path_str: str, display_path: str = None) -> StrReplaceResponse:
        """Read the contents of a file."""
        pass

    @abstractmethod
    def write_file(
        self, path_str: str, file: str, display_path: str = None
    ) -> StrReplaceResponse:
        """Write content to a file."""
        pass

    @abstractmethod
    def is_path_in_directory(self, directory_str: str, path_str: str) -> bool:
        """Check if path is within the specified directory."""
        pass


class LocalStrReplaceClient(StrReplaceClientBase):
    """Local implementation using StrReplaceManager directly."""

    def __init__(self, config: ClientConfig):
        self.config = config
        self.manager = StrReplaceManager(
            ignore_indentation_for_str_replace=config.ignore_indentation_for_str_replace,
            expand_tabs=config.expand_tabs,
            use_relative_path=True,
            cwd=config.cwd,
        )

    def validate_path(
        self, command: str, path_str: str, display_path: str = None
    ) -> StrReplaceResponse:
        return self.manager.validate_path(command, path_str, display_path)

    def view(
        self,
        path_str: str,
        view_range: Optional[list[int]] = None,
        display_path: str = None,
    ) -> StrReplaceResponse:
        return self.manager.view(path_str, view_range, display_path)

    def str_replace(
        self, path_str: str, old_str: str, new_str: str | None, display_path: str = None
    ) -> StrReplaceResponse:
        return self.manager.str_replace(path_str, old_str, new_str, display_path)

    def insert(
        self, path_str: str, insert_line: int, new_str: str, display_path: str = None
    ) -> StrReplaceResponse:
        return self.manager.insert(path_str, insert_line, new_str, display_path)

    def undo_edit(self, path_str: str, display_path: str = None) -> StrReplaceResponse:
        return self.manager.undo_edit(path_str, display_path)

    def read_file(self, path_str: str, display_path: str = None) -> StrReplaceResponse:
        return self.manager.read_file(path_str, display_path)

    def write_file(
        self, path_str: str, file: str, display_path: str = None
    ) -> StrReplaceResponse:
        return self.manager.write_file(path_str, file, display_path)

    def is_path_in_directory(self, directory_str: str, path_str: str) -> bool:
        return self.manager.is_path_in_directory(directory_str, path_str)


class RemoteStrReplaceClient(StrReplaceClientBase):
    """Remote implementation using HTTP API calls."""

    def __init__(self, config: ClientConfig):
        self.config = config
        if not config.server_url:
            raise ValueError("server_url is required for remote mode")
        self.server_url = config.server_url.rstrip("/")
        self.timeout = config.timeout

    def _make_request(self, endpoint: str, data: dict[str, Any]) -> StrReplaceResponse:
        """Make an HTTP request to the remote server."""
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    f"{self.server_url}/api/str_replace/{endpoint}",
                    json=data,
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()
                result = response.json()
                return StrReplaceResponse(
                    success=result.get("success", False),
                    file_content=result.get("file_content", ""),
                )
        except httpx.RequestError as e:
            logger.error(f"Request error for {endpoint}: {e}")
            return StrReplaceResponse(
                success=False, file_content=f"Request error: {str(e)}"
            )
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error for {endpoint}: {e}")
            return StrReplaceResponse(
                success=False,
                file_content=f"HTTP error {e.response.status_code}: {e.response.text}",
            )
        except Exception as e:
            logger.error(f"Unexpected error for {endpoint}: {e}")
            return StrReplaceResponse(
                success=False, file_content=f"Unexpected error: {str(e)}"
            )

    def validate_path(
        self, command: str, path_str: str, display_path: str = None
    ) -> StrReplaceResponse:
        return self._make_request(
            "validate_path",
            {"command": command, "path_str": path_str, "display_path": display_path},
        )

    def view(
        self,
        path_str: str,
        view_range: Optional[list[int]] = None,
        display_path: str = None,
    ) -> StrReplaceResponse:
        return self._make_request(
            "view",
            {
                "path_str": path_str,
                "view_range": view_range,
                "display_path": display_path,
            },
        )

    def str_replace(
        self, path_str: str, old_str: str, new_str: str | None, display_path: str = None
    ) -> StrReplaceResponse:
        return self._make_request(
            "str_replace",
            {
                "path_str": path_str,
                "old_str": old_str,
                "new_str": new_str,
                "display_path": display_path,
            },
        )

    def insert(
        self, path_str: str, insert_line: int, new_str: str, display_path: str = None
    ) -> StrReplaceResponse:
        return self._make_request(
            "insert",
            {
                "path_str": path_str,
                "insert_line": insert_line,
                "new_str": new_str,
                "display_path": display_path,
            },
        )

    def undo_edit(self, path_str: str, display_path: str = None) -> StrReplaceResponse:
        return self._make_request(
            "undo_edit", {"path_str": path_str, "display_path": display_path}
        )

    def read_file(self, path_str: str, display_path: str = None) -> StrReplaceResponse:
        return self._make_request(
            "read_file", {"path_str": path_str, "display_path": display_path}
        )

    def write_file(
        self, path_str: str, file: str, display_path: str = None
    ) -> StrReplaceResponse:
        return self._make_request(
            "write_file",
            {"path_str": path_str, "file": file, "display_path": display_path},
        )

    def is_path_in_directory(self, directory_str: str, path_str: str) -> bool:
        """Check if path is within the specified directory."""
        response = self._make_request(
            "is_path_in_directory",
            {"directory_str": directory_str, "path_str": path_str},
        )
        if response.success:
            # Assuming the server returns the boolean result in file_content
            return response.file_content.lower() == "true"
        return False


class StrReplaceClient:
    """Factory class for creating the appropriate client based on configuration."""

    def __init__(self, settings: Settings):
        self.config = settings.client_config
        if settings.sandbox_config.mode == WorkSpaceMode.LOCAL:
            self._client = LocalStrReplaceClient(self.config)
        elif (
            settings.sandbox_config.mode == WorkSpaceMode.DOCKER
            or settings.sandbox_config.mode == WorkSpaceMode.E2B
        ):
            self._client = RemoteStrReplaceClient(self.config)
        else:
            raise ValueError(
                f"Unsupported mode: {settings.sandbox_config.mode}. Must be 'local' or 'remote' or 'e2b'"
            )

    def validate_path(
        self, command: str, path_str: str, display_path: str = None
    ) -> StrReplaceResponse:
        return self._client.validate_path(command, path_str, display_path)

    def view(
        self,
        path_str: str,
        view_range: Optional[list[int]] = None,
        display_path: str = None,
    ) -> StrReplaceResponse:
        return self._client.view(path_str, view_range, display_path)

    def str_replace(
        self, path_str: str, old_str: str, new_str: str | None, display_path: str = None
    ) -> StrReplaceResponse:
        return self._client.str_replace(path_str, old_str, new_str, display_path)

    def insert(
        self, path_str: str, insert_line: int, new_str: str, display_path: str = None
    ) -> StrReplaceResponse:
        return self._client.insert(path_str, insert_line, new_str, display_path)

    def undo_edit(self, path_str: str, display_path: str = None) -> StrReplaceResponse:
        return self._client.undo_edit(path_str, display_path)

    def read_file(self, path_str: str, display_path: str = None) -> StrReplaceResponse:
        return self._client.read_file(path_str, display_path)

    def write_file(
        self, path_str: str, file: str, display_path: str = None
    ) -> StrReplaceResponse:
        return self._client.write_file(path_str, file, display_path)

    def is_path_in_directory(self, directory_str: str, path_str: str) -> bool:
        return self._client.is_path_in_directory(directory_str, path_str)
