"""Client for file system operations that can work locally or remotely."""

import logging
from abc import ABC, abstractmethod
from typing import Optional, Any, List, Dict
import httpx

from ii_agent.core.config.client_config import ClientConfig
from ii_agent.core.storage.models.settings import Settings
from ii_agent.utils.constants import WorkSpaceMode
from ii_agent.utils.tool_client.manager import FileSystemResponse, FileSystemManager

logger = logging.getLogger(__name__)


class FileSystemClientBase(ABC):
    """Abstract base class for file system clients."""

    @abstractmethod
    def read_file(
        self, file_path: str, limit: Optional[int] = None, offset: Optional[int] = None
    ) -> FileSystemResponse:
        """Read file contents."""
        pass

    @abstractmethod
    def edit_file(
        self, file_path: str, old_string: str, new_string: str, replace_all: bool = False
    ) -> FileSystemResponse:
        """Edit file contents."""
        pass

    @abstractmethod
    def write_file(self, file_path: str, content: str) -> FileSystemResponse:
        """Write file contents."""
        pass

    @abstractmethod
    def multi_edit(self, file_path: str, edits: List[Dict[str, Any]]) -> FileSystemResponse:
        """Perform multiple edits on a file."""
        pass

    @abstractmethod
    def ls(self, path: str, ignore: Optional[List[str]] = None) -> FileSystemResponse:
        """List directory contents."""
        pass

    @abstractmethod
    def glob(self, pattern: str, path: Optional[str] = None) -> FileSystemResponse:
        """Search for files using glob patterns."""
        pass

    @abstractmethod
    def grep(
        self, pattern: str, path: Optional[str] = None, include: Optional[str] = None
    ) -> FileSystemResponse:
        """Search for content using regex patterns."""
        pass


class LocalFileSystemClient(FileSystemClientBase):
    """Local implementation using FileSystemManager directly."""

    def __init__(self, config: ClientConfig):
        self.config = config
        workspace_path = config.cwd or "/workspace"
        self.manager = FileSystemManager(workspace_path=workspace_path)

    def read_file(
        self, file_path: str, limit: Optional[int] = None, offset: Optional[int] = None
    ) -> FileSystemResponse:
        return self.manager.read_file(file_path, limit, offset)

    def edit_file(
        self, file_path: str, old_string: str, new_string: str, replace_all: bool = False
    ) -> FileSystemResponse:
        return self.manager.edit_file(file_path, old_string, new_string, replace_all)

    def write_file(self, file_path: str, content: str) -> FileSystemResponse:
        return self.manager.write_file(file_path, content)

    def multi_edit(self, file_path: str, edits: List[Dict[str, Any]]) -> FileSystemResponse:
        return self.manager.multi_edit(file_path, edits)

    def ls(self, path: str, ignore: Optional[List[str]] = None) -> FileSystemResponse:
        return self.manager.ls(path, ignore)

    def glob(self, pattern: str, path: Optional[str] = None) -> FileSystemResponse:
        return self.manager.glob(pattern, path)

    def grep(
        self, pattern: str, path: Optional[str] = None, include: Optional[str] = None
    ) -> FileSystemResponse:
        return self.manager.grep(pattern, path, include)


class RemoteFileSystemClient(FileSystemClientBase):
    """Remote implementation using HTTP API calls."""

    def __init__(self, config: ClientConfig):
        self.config = config
        if not config.server_url:
            raise ValueError("server_url is required for remote mode")
        self.server_url = config.server_url.rstrip("/")
        self.timeout = config.timeout

    def _make_request(self, endpoint: str, data: Dict[str, Any]) -> FileSystemResponse:
        """Make an HTTP request to the remote server."""
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    f"{self.server_url}/api/filesystem/{endpoint}",
                    json=data,
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()
                result = response.json()
                return FileSystemResponse(
                    success=result.get("success", False),
                    file_content=result.get("file_content", ""),
                )
        except httpx.RequestError as e:
            logger.error(f"Request error for {endpoint}: {e}")
            return FileSystemResponse(
                success=False, file_content=f"Request error: {str(e)}"
            )
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error for {endpoint}: {e}")
            return FileSystemResponse(
                success=False,
                file_content=f"HTTP error {e.response.status_code}: {e.response.text}",
            )
        except Exception as e:
            logger.error(f"Unexpected error for {endpoint}: {e}")
            return FileSystemResponse(
                success=False, file_content=f"Unexpected error: {str(e)}"
            )

    def read_file(
        self, file_path: str, limit: Optional[int] = None, offset: Optional[int] = None
    ) -> FileSystemResponse:
        return self._make_request(
            "read_file",
            {"file_path": file_path, "limit": limit, "offset": offset},
        )

    def edit_file(
        self, file_path: str, old_string: str, new_string: str, replace_all: bool = False
    ) -> FileSystemResponse:
        return self._make_request(
            "edit_file",
            {
                "file_path": file_path,
                "old_string": old_string,
                "new_string": new_string,
                "replace_all": replace_all,
            },
        )

    def write_file(self, file_path: str, content: str) -> FileSystemResponse:
        return self._make_request(
            "write_file", {"file_path": file_path, "content": content}
        )

    def multi_edit(self, file_path: str, edits: List[Dict[str, Any]]) -> FileSystemResponse:
        return self._make_request(
            "multi_edit", {"file_path": file_path, "edits": edits}
        )

    def ls(self, path: str, ignore: Optional[List[str]] = None) -> FileSystemResponse:
        return self._make_request("ls", {"path": path, "ignore": ignore})

    def glob(self, pattern: str, path: Optional[str] = None) -> FileSystemResponse:
        return self._make_request("glob", {"pattern": pattern, "path": path})

    def grep(
        self, pattern: str, path: Optional[str] = None, include: Optional[str] = None
    ) -> FileSystemResponse:
        return self._make_request(
            "grep", {"pattern": pattern, "path": path, "include": include}
        )


class FileSystemClient:
    """Factory class for creating the appropriate client based on configuration."""

    def __init__(self, settings: Settings):
        self.config = settings.client_config
        if settings.sandbox_config.mode == WorkSpaceMode.LOCAL:
            self._client = LocalFileSystemClient(self.config)
        elif (
            settings.sandbox_config.mode == WorkSpaceMode.DOCKER
            or settings.sandbox_config.mode == WorkSpaceMode.E2B
        ):
            self._client = RemoteFileSystemClient(self.config)
        else:
            raise ValueError(
                f"Unsupported mode: {settings.sandbox_config.mode}. Must be 'local', 'docker', or 'e2b'"
            )

    def read_file(
        self, file_path: str, limit: Optional[int] = None, offset: Optional[int] = None
    ) -> FileSystemResponse:
        return self._client.read_file(file_path, limit, offset)

    def edit_file(
        self, file_path: str, old_string: str, new_string: str, replace_all: bool = False
    ) -> FileSystemResponse:
        return self._client.edit_file(file_path, old_string, new_string, replace_all)

    def write_file(self, file_path: str, content: str) -> FileSystemResponse:
        return self._client.write_file(file_path, content)

    def multi_edit(self, file_path: str, edits: List[Dict[str, Any]]) -> FileSystemResponse:
        return self._client.multi_edit(file_path, edits)

    def ls(self, path: str, ignore: Optional[List[str]] = None) -> FileSystemResponse:
        return self._client.ls(path, ignore)

    def glob(self, pattern: str, path: Optional[str] = None) -> FileSystemResponse:
        return self._client.glob(pattern, path)

    def grep(
        self, pattern: str, path: Optional[str] = None, include: Optional[str] = None
    ) -> FileSystemResponse:
        return self._client.grep(pattern, path, include)