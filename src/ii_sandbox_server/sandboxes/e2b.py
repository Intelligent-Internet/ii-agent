from datetime import datetime, timezone
from functools import wraps
import logging
from typing import IO, AsyncIterator, Literal, Optional, TYPE_CHECKING

from e2b import CommandResult
from e2b_code_interpreter import AsyncSandbox
from e2b.sandbox_async.sandbox_api import SandboxListQuery
from ii_sandbox_server.config import SandboxConfig
from ii_sandbox_server.sandboxes.base import BaseSandbox
from ii_sandbox_server.models.exceptions import (
    SandboxAuthenticationError,
    SandboxNotFoundException,
    SandboxTimeoutException,
    SandboxNotInitializedError,
    SandboxGeneralException,
)
from e2b.exceptions import NotFoundException, AuthenticationException, TimeoutException

if TYPE_CHECKING:
    from ii_sandbox_server.lifecycle.queue import SandboxQueueScheduler

logger = logging.getLogger(__name__)

TIMEOUT_AFTER_PAUSE_SECONDS = 600
DEFAULT_TIMEOUT = 3600


def e2b_exception_handler(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except NotFoundException:
            raise SandboxNotFoundException(args[0])
        except AuthenticationException as e:
            raise SandboxAuthenticationError(e.args[0])
        except TimeoutException:
            raise SandboxTimeoutException(args[0], func.__name__)
        except Exception as e:
            raise SandboxGeneralException(
                f"Failed to {func.__name__} for sandbox {args[0]}: {e}"
            )

    return wrapper


class E2BSandbox(BaseSandbox):
    """E2B sandbox provider for managing remote code execution environments."""

    def __init__(
        self,
        sandbox: AsyncSandbox,
        sandbox_id: str,
        queue: Optional["SandboxQueueScheduler"],
    ):
        super().__init__()
        self._sandbox = sandbox
        self._sandbox_id = sandbox_id
        self._queue = queue

    def _ensure_sandbox(self):
        if not self._sandbox and not self._sandbox_id:
            raise SandboxNotInitializedError(
                f"Sandbox not initialized: {self._sandbox_id}"
            )

    @property
    def provider_sandbox_id(self):
        self._ensure_sandbox()
        return self._sandbox.sandbox_id

    @property
    def sandbox_id(self):
        return self._sandbox_id

    @classmethod
    def _ensure_credentials(cls, config: SandboxConfig):
        if not config.e2b_api_key or not config.e2b_template_id:
            raise SandboxAuthenticationError("E2B API key and template ID are required")

    @classmethod
    @e2b_exception_handler
    async def create(
        cls,
        config: SandboxConfig,
        queue: Optional["SandboxQueueScheduler"],
        sandbox_id: str,
        metadata: Optional[dict] = None,
        sandbox_template_id: Optional[str] = None,
    ):
        cls._ensure_credentials(config)
        sandbox = await AsyncSandbox.create(
            sandbox_template_id if sandbox_template_id else config.e2b_template_id,
            api_key=config.e2b_api_key,
            metadata=metadata,
        )
        instance = cls(
            sandbox,
            sandbox_id=sandbox_id,
            queue=queue,
        )
        await instance._set_timeout(
            config.timeout_seconds, config.pause_before_timeout_seconds
        )
        return instance

    @classmethod
    async def resume(
        cls,
        provider_sandbox_id: str,
        config: SandboxConfig,
        queue: Optional["SandboxQueueScheduler"],
        sandbox_id: str,
    ):
        cls._ensure_credentials(config)
        sandbox = await AsyncSandbox.resume(
            provider_sandbox_id,
            api_key=config.e2b_api_key,
        )
        instance = cls(
            sandbox,
            sandbox_id=sandbox_id,
            queue=queue,
        )
        await instance._set_timeout(config.timeout_seconds)
        return instance

    @classmethod
    @e2b_exception_handler
    async def delete(
        cls,
        provider_sandbox_id: str,
        config: SandboxConfig,
        queue: Optional["SandboxQueueScheduler"],
        sandbox_id: str,
    ):
        """Delete a sandbox instance."""
        cls._ensure_credentials(config)
        if await cls.is_paused(config, sandbox_id):
            logger.info(f"Resuming sandbox {sandbox_id} for deletion")
            sandbox = await AsyncSandbox.resume(
                provider_sandbox_id, api_key=config.e2b_api_key
            )
        else:
            sandbox = await AsyncSandbox.connect(
                provider_sandbox_id, api_key=config.e2b_api_key
            )
        await sandbox.kill()
        if queue:
            await queue.cancel_message(sandbox_id)

    @classmethod
    @e2b_exception_handler
    async def stop(
        cls,
        provider_sandbox_id: str,
        config: SandboxConfig,
        queue: Optional["SandboxQueueScheduler"],
        sandbox_id: str,
    ):
        cls._ensure_credentials(config)
        if not await cls.is_paused(config, sandbox_id):
            sandbox = await AsyncSandbox.connect(
                provider_sandbox_id, api_key=config.e2b_api_key
            )
            await sandbox.pause()
            if queue:
                await queue.cancel_message(sandbox_id)
        else:
            logger.info(f"Sandbox {sandbox_id} is already paused, skipping pause")

    @classmethod
    @e2b_exception_handler
    async def schedule_timeout(
        cls,
        provider_sandbox_id: str,
        sandbox_id: str,
        config: SandboxConfig,
        queue: Optional["SandboxQueueScheduler"],
        timeout_seconds: int,
    ):
        cls._ensure_credentials(config)
        if not await cls.is_paused(config, sandbox_id):
            sandbox = cls(
                await AsyncSandbox.connect(
                    provider_sandbox_id, api_key=config.e2b_api_key
                ),
                sandbox_id=sandbox_id,
                queue=queue,
            )
            await sandbox._set_timeout(timeout_seconds)
        else:
            logger.info(
                f"Sandbox {sandbox_id} is already paused, skipping timeout scheduling"
            )

    @classmethod
    @e2b_exception_handler
    async def connect(
        cls,
        provider_sandbox_id: str,
        config: SandboxConfig,
        queue: Optional["SandboxQueueScheduler"],
        sandbox_id: str,
    ) -> "E2BSandbox":
        """Connect to an existing sandbox instance.

        Returns:
            Sandbox instance
        """
        cls._ensure_credentials(config)
        sandbox = cls(
            await AsyncSandbox.connect(
                provider_sandbox_id,
                api_key=config.e2b_api_key,
            ),
            sandbox_id=sandbox_id,
            queue=queue,
        )
        await sandbox._set_timeout(config.timeout_seconds)
        return sandbox

    @e2b_exception_handler
    async def _set_timeout(
        self,
        timeout: int = DEFAULT_TIMEOUT,
        pause_before_timeout: int = TIMEOUT_AFTER_PAUSE_SECONDS,
    ):
        # Actual timeout and delete the sandbox
        await self._sandbox.set_timeout(timeout + pause_before_timeout)

        # Schedule timeout with queue if available
        if self._queue and self._sandbox_id:
            # PAUSE BEFORE TIMEOUT WITH QUEUE
            await self._queue.schedule_message(
                sandbox_id=self._sandbox_id,
                action="pause",
                delay_seconds=timeout,
                metadata={
                    "reason": "idle",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            logger.info(
                f"Scheduled timeout for sandbox {self._sandbox_id} in {timeout // 60} minutes"
            )

    async def get_host(self) -> str:
        self._ensure_sandbox()
        return f"{self.provider_sandbox_id}.{self._sandbox.connection_config.domain}"

    async def expose_port(self, port: int, external: bool = False) -> str:
        """E2B sandboxes always expose ports externally via HTTPS."""
        self._ensure_sandbox()
        return f"https://{self._sandbox.get_host(port)}"

    @e2b_exception_handler
    async def read_file(self, file_path: str) -> str:
        """Read a file from the sandbox.

        Args:
            file_path: Path to the file in the sandbox

        Returns:
            File content as string
        """
        self._ensure_sandbox()
        return await self._sandbox.files.read(file_path, format="text")

    @e2b_exception_handler
    async def write_file(self, file_content: str | bytes | IO, file_path: str):
        """Write content to a file in the sandbox.

        Args:
            file_content: Content to write
            file_path: Path to the file in the sandbox

        Returns:
            True if written successfully
        """
        self._ensure_sandbox()
        await self._sandbox.files.write(file_path, file_content)
        return True

    @e2b_exception_handler
    async def upload_file(
        self, file_content: str | bytes | IO, remote_file_path: str
    ) -> bool:
        """Upload a file to the sandbox.

        Args:
            file_content: Content of the file
            remote_file_path: Path to the file in the sandbox

        Returns:
            True if uploaded successfully
        """
        self._ensure_sandbox()
        if await self._sandbox.files.exists(remote_file_path):
            logger.error(f"File {remote_file_path} already exists")
            return False
        await self._sandbox.files.write(remote_file_path, file_content)
        return True

    @e2b_exception_handler
    async def delete_file(self, file_path: str) -> bool:
        """Delete a file from the sandbox.

        Args:
            file_path: Path to the file in the sandbox

        Returns:
            True if deleted successfully
        """
        self._ensure_sandbox()
        await self._sandbox.files.remove(file_path)
        return True

    @e2b_exception_handler
    async def download_file(
        self, remote_file_path: str, format: Literal["text", "bytes"] = "text"
    ) -> Optional[str | bytes | AsyncIterator[bytes]]:
        """Download a file from the sandbox.

        Args:
            remote_file_path: Path to the file in the sandbox
            format: Format of the file content ("text", "bytes", or "stream")

        Returns:
            File content as string, bytes, or iterator of bytes
        """
        self._ensure_sandbox()
        content = await self._sandbox.files.read(path=remote_file_path, format=format)
        if isinstance(content, bytes):
            return content
        elif isinstance(content, bytearray):
            return bytes(content)
        elif isinstance(content, str):
            return content.encode('utf-8')
        else:
            raise ValueError(f"Unsupported file content type: {type(content)}")

    async def download_file_stream(self, remote_file_path: str) -> AsyncIterator[bytes]:
        """Download a file from the sandbox."""
        self._ensure_sandbox()
        return await self._sandbox.files.read(path=remote_file_path, format="stream")

    @e2b_exception_handler
    async def run_cmd(self, command: str, background: bool = False) -> str:
        """Run a command in the sandbox.
        """
        self._ensure_sandbox()
        result = await self._sandbox.commands.run(command, background=background)
        if not isinstance(result, CommandResult):
            raise Exception(f"Command {command} failed: {result.error}")
        if result.exit_code != 0:
            raise Exception(f"Command {command} failed: {result.error}")
        return result.stdout

    @e2b_exception_handler
    async def cancel_timeout(self):
        """Cancel any scheduled timeout for this sandbox."""
        if self._queue and self._sandbox_id:
            await self._queue.cancel_message(self._sandbox_id)

    @e2b_exception_handler
    async def create_directory(
        self, directory_path: str, exist_ok: bool = False
    ) -> bool:
        """Create a directory in the sandbox.

        Args:
            directory_path: Path to the directory in the sandbox

        Returns:
            True if created successfully
        """
        self._ensure_sandbox()
        exist = await self._sandbox.files.make_dir(directory_path)
        if not exist and not exist_ok:
            raise Exception(f"Directory {directory_path} already exists")
        return True

    @classmethod
    @e2b_exception_handler
    async def is_paused(cls, config: SandboxConfig, sandbox_id: str) -> bool:
        paginator = AsyncSandbox.list(
            api_key=config.e2b_api_key,
            query=SandboxListQuery(
                state=["paused"],
                # Bad pattern as this use controlled sandbox id
                metadata={
                    "ii_sandbox_id": sandbox_id,
                },
            ),
        )
        if paginator.has_next:
            sandbox = await paginator.next_items()
            print(sandbox)
            if sandbox:
                return True
            else:
                return False
        return False
