"""Local filesystem storage provider for local-only deployments."""

import os
import shutil
import aiofiles
from typing import BinaryIO
from urllib.parse import urlparse

import httpx

from .base import BaseStorage


class LocalStorage(BaseStorage):
    """Local filesystem storage provider.

    Stores files in a local directory instead of cloud storage.
    Useful for:
    - Local development
    - Air-gapped environments
    - Privacy-focused deployments
    """

    def __init__(self, base_path: str = "/.ii_agent/storage"):
        """Initialize local storage.

        Args:
            base_path: Base directory for file storage
        """
        self.base_path = os.path.abspath(base_path)
        os.makedirs(self.base_path, exist_ok=True)

    def _get_full_path(self, path: str) -> str:
        """Get the full filesystem path for a storage path."""
        # Normalize and ensure path is within base_path
        normalized = os.path.normpath(path).lstrip("/")
        full_path = os.path.join(self.base_path, normalized)

        # Security: ensure we don't escape base_path
        if not os.path.abspath(full_path).startswith(self.base_path):
            raise ValueError(f"Path traversal detected: {path}")

        return full_path

    async def write(self, content: BinaryIO, path: str, content_type: str | None = None):
        """Write binary content to a file.

        Args:
            content: Binary file-like object to write
            path: Destination path within storage
            content_type: MIME type (stored in .meta file for reference)
        """
        full_path = self._get_full_path(path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        async with aiofiles.open(full_path, "wb") as f:
            # Handle both sync and async file objects
            if hasattr(content, "read"):
                data = content.read()
                if hasattr(data, "__await__"):
                    data = await data
                await f.write(data)
            else:
                await f.write(content)

        # Store content type in a sidecar file if provided
        if content_type:
            meta_path = full_path + ".meta"
            async with aiofiles.open(meta_path, "w") as f:
                await f.write(content_type)

    async def write_from_url(self, url: str, path: str, content_type: str | None = None) -> str:
        """Download content from URL and store it.

        Args:
            url: Source URL to download from
            path: Destination path within storage
            content_type: MIME type override

        Returns:
            Local file path (as URL would be in cloud storage)
        """
        full_path = self._get_full_path(path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        # Add browser-like headers to avoid bot detection
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://www.google.com/",
            "DNT": "1",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "image",
            "Sec-Fetch-Mode": "no-cors",
            "Sec-Fetch-Site": "cross-site",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers, follow_redirects=True)
            response.raise_for_status()

            async with aiofiles.open(full_path, "wb") as f:
                await f.write(response.content)

            # Use content-type from response if not provided
            if not content_type:
                content_type = response.headers.get("content-type")

            if content_type:
                meta_path = full_path + ".meta"
                async with aiofiles.open(meta_path, "w") as f:
                    await f.write(content_type)

        return self.get_public_url(path)

    async def write_from_local_path(
        self, local_path: str, target_path: str, content_type: str | None = None
    ) -> str:
        """Copy a local file to storage.

        Args:
            local_path: Source file path on local filesystem
            target_path: Destination path within storage
            content_type: MIME type

        Returns:
            Storage URL/path for the file
        """
        full_path = self._get_full_path(target_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        # Use shutil for efficient file copy
        shutil.copy2(local_path, full_path)

        if content_type:
            meta_path = full_path + ".meta"
            async with aiofiles.open(meta_path, "w") as f:
                await f.write(content_type)

        return self.get_public_url(target_path)

    def get_local_path(self, path: str) -> str:
        """Get the local filesystem path for a storage path.

        Args:
            path: Storage path

        Returns:
            Absolute filesystem path
        """
        return self._get_full_path(path)

    def get_public_url(self, path: str) -> str:
        """Get the URL for accessing a stored file.

        For local storage, returns HTTP URL that will be served via
        the /storage endpoint in the tool server.

        Args:
            path: Storage path

        Returns:
            HTTP URL to access the file via tool server
        """
        # Normalize path and return HTTP URL
        normalized_path = path.lstrip('/')
        # Use PUBLIC_TOOL_SERVER_URL or fall back to TOOL_SERVER_URL or default
        import os
        tool_server_url = os.getenv('PUBLIC_TOOL_SERVER_URL') or os.getenv('TOOL_SERVER_URL', 'http://localhost:1236')
        return f"{tool_server_url}/storage/{normalized_path}"
