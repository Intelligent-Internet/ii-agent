"""Slide content processor for replacing local file paths with permanent URLs."""

import asyncio
import io
import re
import hashlib
import mimetypes
from pathlib import Path
from typing import Optional, Dict
import logging
from urllib.parse import unquote

import httpx

from ii_agent.storage.base import BaseStorage
from ii_agent.storage.local import LocalStorage
from ii_agent.sandbox import IISandbox

logger = logging.getLogger(__name__)

# Timeout for upload requests (in seconds)
UPLOAD_TIMEOUT = 60


class SlideContentProcessor:
    """Processes slide HTML content to replace local file paths with permanent URLs."""

    def __init__(self, storage: BaseStorage, sandbox: IISandbox):
        self.storage = storage
        self.sandbox = sandbox
        # Session-level cache: {content_hash: permanent_url}
        self.url_cache: Dict[str, str] = {}

    async def process_html_content(
        self, html_content: str, slide_file_path: str
    ) -> str:
        """
        Process HTML content to replace local file paths with permanent URLs.

        Args:
            html_content: The HTML content containing local file references
            slide_file_path: Path to the slide file in sandbox (e.g., "/home/user/presentation.html")

        Returns:
            Modified HTML content with permanent URLs
        """
        logger.info("Processing slide HTML content for file path replacement")
        try:
            # Find all file references in HTML
            file_patterns = [
                r'src=["\']([^"\']+)["\']',  # src attributes
                r'href=["\']([^"\']+)["\']',  # href attributes
                r'url\(["\']?([^"\')\s]+)["\']?\)',  # CSS url() references
            ]

            modified_content = html_content

            for pattern in file_patterns:
                matches = re.finditer(pattern, html_content)
                for match in matches:
                    file_path = match.group(1)

                    logger.info(f"Found file reference: {file_path}")

                    # Skip if already a URL or data URI
                    if self._is_external_url(file_path):
                        continue

                    # Convert local path to permanent URL
                    permanent_url = await self._upload_and_get_url(
                        file_path, slide_file_path
                    )

                    if permanent_url:
                        # Replace the file path with permanent URL
                        old_reference = match.group(0)
                        new_reference = old_reference.replace(file_path, permanent_url)
                        modified_content = modified_content.replace(
                            old_reference, new_reference
                        )
                        logger.info(f"Replaced {file_path} with {permanent_url}")

            return modified_content

        except Exception as e:
            logger.error(f"Error processing slide content: {e}")
            return html_content  # Return original on error

    def _is_external_url(self, path: str) -> bool:
        """Check if path is already an external URL or data URI."""
        return (
            path.startswith(("http://", "https://", "data:", "//", "mailto:", "tel:"))
            or path.startswith("#")  # Fragment links
        )

    async def _upload_and_get_url(
        self, file_path: str, slide_file_path: str
    ) -> Optional[str]:
        """
        Upload a file from sandbox and get its permanent URL with efficient caching.

        Args:
            file_path: File path from HTML (relative to slide or absolute)
            slide_file_path: Path to the slide file in sandbox

        Returns:
            Permanent URL or None if file not found/upload failed
        """
        try:
            file_path = unquote(file_path)
            # Resolve the actual file path in sandbox
            resolved_path = self._resolve_sandbox_file_path(file_path, slide_file_path)
            if not resolved_path:
                logger.warning(f"Could not resolve file path: {file_path}")
                return None

            # Try to read file content from sandbox
            try:
                file_content_bytes = await self.sandbox.download_file(
                    resolved_path, format="bytes"
                )
                if not file_content_bytes:
                    logger.warning(f"File not found in sandbox: {resolved_path}")
                    return None

                file_content = bytes(file_content_bytes)
            except Exception as e:
                logger.warning(f"Failed to read file from sandbox {resolved_path}: {e}")
                return None

            # Generate content-based hash for true deduplication
            content_hash = hashlib.md5(file_content).hexdigest()

            # Check session cache first (fastest)
            if content_hash in self.url_cache:
                logger.info(f"Found cached URL for {file_path}")
                return self.url_cache[content_hash]

            # Generate storage path based on content hash
            storage_path = self._generate_storage_path_from_content(
                content_hash, Path(resolved_path)
            )

            # Check if file already exists in storage (fast)
            if self.storage.is_exists(storage_path):
                logger.info(f"File already exists in storage: {storage_path}")
                permanent_url = self.storage.get_permanent_url(storage_path)
                # Cache for session reuse
                self.url_cache[content_hash] = permanent_url
                return permanent_url

            # Upload using signed URL workflow for better performance
            permanent_url = await self._upload_via_signed_url(
                file_content, storage_path, resolved_path
            )

            if permanent_url:
                # Cache the result
                self.url_cache[content_hash] = permanent_url
                logger.info(
                    f"Uploaded {resolved_path} to {storage_path}, URL: {permanent_url}"
                )

            return permanent_url

        except Exception as e:
            logger.error(f"Failed to upload file {file_path}: {e}")
            return None

    def _resolve_sandbox_file_path(
        self, file_path: str, slide_file_path: str
    ) -> Optional[str]:
        """
        Resolve a file path to sandbox absolute path, relative to slide location.

        Args:
            file_path: File path from HTML (relative or absolute)
            slide_file_path: Path to the slide file in sandbox (e.g., "/home/user/slides/presentation.html")

        Returns:
            Resolved sandbox path string or None if invalid
        """
        try:
            slide_dir = str(Path(slide_file_path).parent)

            if file_path.startswith("/"):
                # Absolute path - use as-is (assume it's valid sandbox path)
                return file_path
            else:
                # Relative path - resolve relative to slide directory
                # Use posixpath-style joining and normalization for sandbox paths
                import posixpath

                resolved = posixpath.join(slide_dir, file_path)
                # Normalize path (remove . and .. components) using posixpath
                normalized = posixpath.normpath(resolved)
                return normalized

        except Exception as e:
            logger.error(f"Error resolving sandbox file path {file_path}: {e}")
            return None

    def _generate_storage_path_from_content(
        self, content_hash: str, local_path: Path
    ) -> str:
        """
        Generate a storage path for the file based on content hash.

        Args:
            content_hash: MD5 hash of file content
            local_path: Local file path (for extension)

        Returns:
            Storage path for the file
        """
        # Get file extension
        extension = local_path.suffix or ""

        # Create storage path: slides/assets/{content_hash}{extension}
        return f"slides/assets/{content_hash}{extension}"

    async def _upload_via_signed_url(
        self, file_content: bytes, storage_path: str, original_path: str
    ) -> Optional[str]:
        """
        Upload file content using the most efficient method for the storage type.

        For LocalStorage: Direct write to avoid self-request deadlock.
        For external storage (GCS, S3): Async HTTP PUT with timeout.

        Args:
            file_content: File content as bytes
            storage_path: Target storage path
            original_path: Original file path for content type detection

        Returns:
            Permanent URL or None if upload failed
        """
        try:
            # Determine content type
            content_type = (
                mimetypes.guess_type(original_path)[0] or "application/octet-stream"
            )

            # For LocalStorage, use direct write to avoid self-request deadlock
            # (The backend can't HTTP request itself while processing an agent request)
            if isinstance(self.storage, LocalStorage):
                return await self._upload_direct(file_content, storage_path, content_type)

            # For external storage (GCS, S3), use async HTTP with timeout
            return await self._upload_via_http(file_content, storage_path, content_type)

        except Exception as e:
            logger.error(f"Failed to upload via signed URL: {e}")
            return None

    async def _upload_direct(
        self, file_content: bytes, storage_path: str, content_type: str
    ) -> Optional[str]:
        """
        Upload directly to storage (for LocalStorage).

        Runs in thread pool to avoid blocking the event loop on I/O.
        """
        try:
            def _do_write():
                self.storage.write(io.BytesIO(file_content), storage_path, content_type)
                return self.storage.get_permanent_url(storage_path)

            # Run blocking I/O in thread pool
            loop = asyncio.get_event_loop()
            permanent_url = await loop.run_in_executor(None, _do_write)
            return permanent_url

        except Exception as e:
            logger.error(f"Failed to upload directly to storage: {e}")
            return None

    async def _upload_via_http(
        self, file_content: bytes, storage_path: str, content_type: str
    ) -> Optional[str]:
        """
        Upload via HTTP to signed URL (for external storage like GCS).

        Uses async httpx client with timeout to avoid blocking.
        """
        try:
            # Get upload signed URL
            upload_url = self.storage.get_upload_signed_url(
                storage_path, content_type, expiration_seconds=3600
            )

            # Use async HTTP client with timeout
            async with httpx.AsyncClient(timeout=UPLOAD_TIMEOUT) as client:
                response = await client.put(
                    upload_url,
                    content=file_content,
                    headers={"Content-Type": content_type}
                )

            if response.status_code not in (200, 201):
                logger.error(
                    f"Failed to upload to signed URL: {response.status_code} {response.text}"
                )
                return None

            # Get permanent URL for the uploaded file
            permanent_url = self.storage.get_permanent_url(storage_path)
            return permanent_url

        except httpx.TimeoutException:
            logger.error(f"Upload timed out after {UPLOAD_TIMEOUT}s for {storage_path}")
            return None
        except Exception as e:
            logger.error(f"Failed to upload via HTTP: {e}")
            return None

    def _generate_storage_path(self, local_path: Path) -> str:
        """
        Legacy method - Generate a storage path for the file based on path hash.

        Args:
            local_path: Local file path

        Returns:
            Storage path for the file
        """
        # Generate hash from file path for uniqueness
        path_hash = hashlib.md5(str(local_path).encode()).hexdigest()[:12]

        # Get file extension
        extension = local_path.suffix

        # Create storage path: slides/assets/{hash}{extension}
        return f"slides/assets/{path_hash}{extension}"
