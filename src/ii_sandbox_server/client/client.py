"""Client for communicating with the sandbox server."""

import logging
from functools import wraps
from typing import IO, AsyncIterator, Literal, Optional
from ii_sandbox_server.models.payload import (
    CreateSandboxResponse,
    ConnectSandboxResponse,
    ScheduleTimeoutResponse,
    SandboxStatusResponse,
    SandboxInfo,
    PauseSandboxResponse,
    DeleteSandboxResponse,
    ExposePortResponse,
    FileOperationResponse,
    RunCommandRequest,
    RunCommandResponse,
)

from ii_sandbox_server.models.exceptions import (
    SandboxNotFoundException,
    SandboxNotInitializedError,
    SandboxAuthenticationError,
    SandboxGeneralException,
)

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_log,
    after_log,
)


logger = logging.getLogger(__name__)


# Define retryable exceptions
RETRYABLE_EXCEPTIONS = (
    httpx.RequestError,
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
)

# Create retry decorator with exponential backoff
retry_decorator = retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
    before=before_log(logger, logging.DEBUG),
    after=after_log(logger, logging.DEBUG),
)


def handle_http_error(func):
    """Handle HTTP errors with retry logic."""

    @wraps(func)
    @retry_decorator
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except httpx.HTTPStatusError as e:
            # Non-retryable HTTP errors
            if e.response.status_code == 401:
                raise SandboxAuthenticationError(
                    f"Authentication failed: {e.response.text}"
                )
            elif e.response.status_code == 404:
                raise SandboxNotFoundException(f"Resource not found: {e.response.text}")
            elif e.response.status_code == 408:
                # Timeout is retryable - let tenacity handle it
                raise httpx.TimeoutException(
                    f"Request timed out: {e.response.text}"
                )
            elif e.response.status_code == 422:
                raise SandboxNotInitializedError(f"Validation error: {e.response.text}")
            else:
                raise SandboxGeneralException(f"Server error: {e.response.status_code}")
        except httpx.RequestError as e:
            logger.error(f"Request error (will retry if attempts remain): {e}")
            raise  # Let tenacity handle the retry
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            raise Exception(f"Unexpected error: {str(e)}")

    return wrapper


class SandboxClient:
    """Client for communicating with the sandbox server."""

    def __init__(self, base_url: str = "http://localhost:8100", timeout: float = 120.0):
        """Initialize the sandbox client.

        Args:
            base_url: The base URL of the sandbox server
            timeout: Default timeout in seconds (extended from 60 to 120)
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        # Configure httpx client with extended timeouts
        timeout_config = httpx.Timeout(
            connect=30.0,
            read=timeout,
            write=30.0,
            pool=30.0
        )
        self.client = httpx.AsyncClient(timeout=timeout_config)

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
    )
    async def health_check(self) -> bool:
        """Check if the server is healthy with retry logic."""
        try:
            response = await self.client.get(f"{self.base_url}/health")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    @handle_http_error
    async def create_sandbox(
        self,
        user_id: str,
        sandbox_template_id: str | None = None,
    ) -> str:
        """Create a new sandbox."""
        request = {
            "user_id": user_id,
            "sandbox_template_id": sandbox_template_id,
        }

        response = await self.client.post(
            f"{self.base_url}/sandboxes/create", json=request
        )
        response.raise_for_status()

        result = CreateSandboxResponse(**response.json())
        return result.sandbox_id

    @handle_http_error
    async def connect_sandbox(self, sandbox_id: str) -> ConnectSandboxResponse:
        """Connect to or resume a sandbox."""
        request = {"sandbox_id": sandbox_id}

        response = await self.client.post(
            f"{self.base_url}/sandboxes/connect", json=request
        )
        response.raise_for_status()

        result = ConnectSandboxResponse(**response.json())
        return result

    @handle_http_error
    async def schedule_timeout(
        self, sandbox_id: str, timeout_seconds: int
    ) -> ScheduleTimeoutResponse:
        """Schedule a timeout for a sandbox."""
        request = {"sandbox_id": sandbox_id, "timeout_seconds": timeout_seconds}

        response = await self.client.post(
            f"{self.base_url}/sandboxes/schedule-timeout", json=request
        )
        response.raise_for_status()

        result = ScheduleTimeoutResponse(**response.json())
        return result

    @handle_http_error
    async def get_sandbox_status(self, sandbox_id: str) -> SandboxStatusResponse:
        """Get the status of a sandbox."""
        response = await self.client.get(
            f"{self.base_url}/sandboxes/{sandbox_id}/status"
        )
        response.raise_for_status()

        result = SandboxStatusResponse(**response.json())
        return result

    @handle_http_error
    async def get_sandbox_info(self, sandbox_id: str) -> Optional[SandboxInfo]:
        """Get detailed information about a sandbox with retry logic."""
        response = await self.client.get(f"{self.base_url}/sandboxes/{sandbox_id}/info")

        if response.status_code == 404:
            return None

        response.raise_for_status()
        return SandboxInfo(**response.json())

    @handle_http_error
    async def pause_sandbox(
        self, sandbox_id: str, reason: str = "manual"
    ) -> PauseSandboxResponse:
        """Pause a sandbox."""
        response = await self.client.post(
            f"{self.base_url}/sandboxes/{sandbox_id}/pause", params={"reason": reason}
        )
        response.raise_for_status()

        result = PauseSandboxResponse(**response.json())
        return result

    @handle_http_error
    async def delete_sandbox(self, sandbox_id: str) -> DeleteSandboxResponse:
        """Delete a sandbox."""
        response = await self.client.delete(f"{self.base_url}/sandboxes/{sandbox_id}")
        response.raise_for_status()

        result = DeleteSandboxResponse(**response.json())
        return result

    @handle_http_error
    async def expose_port(self, sandbox_id: str, port: int, external: bool = False) -> str:
        """Expose a port from a sandbox.

        Args:
            sandbox_id: Sandbox identifier
            port: Port to expose
            external: If True, return host-accessible URL (for browser access)
        """
        request = {"sandbox_id": sandbox_id, "port": port, "external": external}

        response = await self.client.post(
            f"{self.base_url}/sandboxes/expose-port", json=request
        )
        response.raise_for_status()

        result = ExposePortResponse(**response.json())
        return result.url

    @handle_http_error
    async def write_file(
        self, sandbox_id: str, file_path: str, content: str | bytes | IO
    ) -> FileOperationResponse:
        """Write a file to a sandbox."""
        # Handle IO objects
        if isinstance(content, IO):
            file_content = content.read()
        else:
            file_content = content

        if isinstance(file_content, bytes):
            # Use upload-file endpoint for binary data
            form_data = {
                "sandbox_id": sandbox_id,
                "file_path": file_path,
            }
            files = {
                "file": ("file", file_content, "application/octet-stream")
            }

            response = await self.client.post(
                f"{self.base_url}/sandboxes/upload-file",
                data=form_data,
                files=files
            )
        else:
            # Use write-file endpoint for text content
            request = {
                "sandbox_id": sandbox_id,
                "file_path": file_path,
                "content": file_content,
            }

            response = await self.client.post(
                f"{self.base_url}/sandboxes/write-file", json=request
            )

        response.raise_for_status()
        result = FileOperationResponse(**response.json())
        return result

    @handle_http_error
    async def read_file(self, sandbox_id: str, file_path: str) -> FileOperationResponse:
        """Read a file from a sandbox."""
        request = {"sandbox_id": sandbox_id, "file_path": file_path}

        response = await self.client.post(
            f"{self.base_url}/sandboxes/read-file", json=request
        )
        response.raise_for_status()

        result = FileOperationResponse(**response.json())
        return result

    @handle_http_error
    async def download_file(
        self,
        sandbox_id: str,
        file_path: str,
        format: Literal["text", "bytes", "stream"] = "text",
    ) -> Optional[str | bytes | AsyncIterator[bytes]]:
        """Download a file from a sandbox."""
        request = {"sandbox_id": sandbox_id, "file_path": file_path, "format": format}

        if format == "stream":
            response = await self.client.post(
                f"{self.base_url}/sandboxes/download-file-stream", json=request
            )
            response.raise_for_status()
            return response.aiter_bytes()
        elif format == "bytes":
            # For bytes format, expect raw binary response
            response = await self.client.post(
                f"{self.base_url}/sandboxes/download-file", json=request
            )
            response.raise_for_status()
            return response.content
        else:
            # For text format, expect JSON response
            response = await self.client.post(
                f"{self.base_url}/sandboxes/download-file", json=request
            )
            response.raise_for_status()
            data = response.json()
            return data.get("content")

    @handle_http_error
    async def upload_file(
        self, sandbox_id: str, local_path: str, remote_path: str
    ) -> FileOperationResponse:
        """Upload a file to a sandbox."""
        response = await self.client.post(
            f"{self.base_url}/sandboxes/upload-file",
            params={
                "sandbox_id": sandbox_id,
                "local_path": local_path,
                "remote_path": remote_path,
            },
        )
        response.raise_for_status()

        result = FileOperationResponse(**response.json())
        return result

    @handle_http_error
    async def upload_file_from_url(
        self, sandbox_id: str, file_path: str, url: str
    ) -> FileOperationResponse:
        """Upload a file to a sandbox by downloading it from a URL."""
        from ii_sandbox_server.models.payload import UploadFileFromUrlRequest

        request_data = UploadFileFromUrlRequest(
            sandbox_id=sandbox_id,
            file_path=file_path,
            url=url
        )

        response = await self.client.post(
            f"{self.base_url}/sandboxes/upload-file-from-url",
            json=request_data.model_dump(),
        )
        response.raise_for_status()

        result = FileOperationResponse(**response.json())
        return result

    @handle_http_error
    async def download_to_presigned_url(
        self, sandbox_id: str, sandbox_path: str, presigned_url: str, format: Literal["text", "bytes"] = "bytes"
    ) -> FileOperationResponse:
        """Download a file from sandbox to a presigned URL."""
        from ii_sandbox_server.models.payload import DownloadToPresignedUrlRequest

        request_data = DownloadToPresignedUrlRequest(
            sandbox_id=sandbox_id,
            sandbox_path=sandbox_path,
            format=format,
            presigned_url=presigned_url
        )

        response = await self.client.post(
            f"{self.base_url}/sandboxes/download-to-presigned-url",
            json=request_data.model_dump(),
        )
        response.raise_for_status()

        result = FileOperationResponse(**response.json())
        return result

    @handle_http_error
    async def run_cmd(
        self, sandbox_id: str, command: str, background: bool = False
    ) -> str:
        """Run a command in a sandbox."""

        request = RunCommandRequest(
            sandbox_id=sandbox_id,
            command=command,
            background=background
        )

        response = await self.client.post(
            f"{self.base_url}/sandboxes/run-cmd",
            json=request.model_dump()
        )
        response.raise_for_status()

        result = RunCommandResponse(**response.json())
        return result.output

    @handle_http_error
    async def create_directory(
        self, sandbox_id: str, directory_path: str, exist_ok: bool = False
    ) -> bool:
        """Create a directory in a sandbox."""
        params = {
            "sandbox_id": sandbox_id,
            "directory_path": directory_path,
            "exist_ok": exist_ok,
        }

        response = await self.client.post(
            f"{self.base_url}/sandboxes/create-directory", params=params
        )
        response.raise_for_status()

        result = FileOperationResponse(**response.json())
        return result.success
