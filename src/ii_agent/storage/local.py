"""Local filesystem storage provider for ii_agent backend."""

import os
import shutil
import io
import hashlib
import time
from typing import BinaryIO
from urllib.parse import urljoin, quote, unquote

import httpx

from .base import BaseStorage


class LocalStorage(BaseStorage):
    """Local filesystem storage provider for the backend.

    Stores files in a local directory. For local development and
    air-gapped environments.
    """

    def __init__(
        self,
        base_path: str = "/.ii_agent/storage",
        custom_domain: str | None = None,
        serve_url_base: str = "/files",
        internal_url_base: str | None = None
    ):
        """Initialize local storage.

        Args:
            base_path: Base directory for file storage
            custom_domain: Optional custom domain for URLs (not used in local mode)
            serve_url_base: Base URL path for serving files (for browser/external access)
            internal_url_base: Base URL for internal/container-to-container access
                             (e.g., http://backend:8000/files). If not set, uses serve_url_base.
        """
        self.base_path = os.path.abspath(base_path)
        self.custom_domain = custom_domain
        self.serve_url_base = serve_url_base
        self.internal_url_base = internal_url_base or serve_url_base
        os.makedirs(self.base_path, exist_ok=True)

    def _get_full_path(self, path: str) -> str:
        """Get the full filesystem path for a storage path."""
        normalized = os.path.normpath(path).lstrip("/")
        full_path = os.path.join(self.base_path, normalized)

        # Security: ensure we don't escape base_path
        if not os.path.abspath(full_path).startswith(self.base_path):
            raise ValueError(f"Path traversal detected: {path}")

        return full_path

    def write(self, content: BinaryIO, path: str, content_type: str | None = None):
        """Write binary content to a file."""
        full_path = self._get_full_path(path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        with open(full_path, "wb") as f:
            shutil.copyfileobj(content, f)

        if content_type:
            meta_path = full_path + ".meta"
            with open(meta_path, "w") as f:
                f.write(content_type)

    def write_from_url(self, url: str, path: str, content_type: str | None = None) -> str:
        """Download content from URL and store it."""
        full_path = self._get_full_path(path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        with httpx.Client() as client:
            response = client.get(url, follow_redirects=True)
            response.raise_for_status()

            with open(full_path, "wb") as f:
                f.write(response.content)

            if not content_type:
                content_type = response.headers.get("content-type")

            if content_type:
                meta_path = full_path + ".meta"
                with open(meta_path, "w") as f:
                    f.write(content_type)

        return self.get_public_url(path)

    def read(self, path: str) -> BinaryIO:
        """Read a file and return as file-like object."""
        full_path = self._get_full_path(path)

        with open(full_path, "rb") as f:
            content = f.read()

        return io.BytesIO(content)

    def get_download_signed_url(self, path: str, expiration_seconds: int = 3600, internal: bool = False) -> str | None:
        """Get a signed download URL.

        For local storage, we generate a simple token-based URL.
        In production, you'd want a proper signed URL implementation.

        Args:
            path: The storage path to the file
            expiration_seconds: URL expiration time in seconds
            internal: If True, use internal URL base for container-to-container access
        """
        full_path = self._get_full_path(path)
        if not os.path.exists(full_path):
            return None

        # Simple token for local dev (not secure for production!)
        expiry = int(time.time()) + expiration_seconds
        token = hashlib.sha256(f"{path}:{expiry}:local-secret".encode()).hexdigest()[:16]

        url_base = self.internal_url_base if internal else self.serve_url_base
        return f"{url_base}/{path}?token={token}&expires={expiry}"

    def get_upload_signed_url(
        self, path: str, content_type: str, expiration_seconds: int = 3600, internal: bool = True
    ) -> str:
        """Get a signed upload URL.

        For local storage, returns a simple upload endpoint.
        The path may contain URL-encoded characters (e.g., %3A from timestamps).
        We decode it for token generation since the server will receive
        the decoded version after the browser makes the request.

        Args:
            path: The storage path for the file
            content_type: The MIME type of the content
            expiration_seconds: URL expiration time in seconds
            internal: If True (default), use internal URL base for server-to-server uploads.
                     If False, use serve_url_base for browser uploads.
        """
        expiry = int(time.time()) + expiration_seconds
        # Decode any URL-encoded chars in the path for token generation
        # This matches what the server receives after the browser sends the request
        decoded_path = unquote(path)
        token = hashlib.sha256(f"{decoded_path}:{expiry}:local-secret".encode()).hexdigest()[:16]

        # Don't re-encode the path - it may already contain encoded chars like %3A
        # Just encode spaces as %20 for URL safety
        url_path = path.replace(' ', '%20')

        # Use internal URL for server-to-server communication (default),
        # or serve URL for browser-based uploads
        url_base = self.internal_url_base if internal else self.serve_url_base
        return f"{url_base}/upload/{url_path}?token={token}&expires={expiry}&content_type={quote(content_type, safe='')}"

    def is_exists(self, path: str) -> bool:
        """Check if a file exists."""
        full_path = self._get_full_path(path)
        return os.path.exists(full_path)

    def get_file_size(self, path: str) -> int:
        """Get the size of a file in bytes."""
        full_path = self._get_full_path(path)
        return os.path.getsize(full_path)

    def get_public_url(self, path: str) -> str:
        """Get a public URL for a file."""
        return f"{self.serve_url_base}/{path}"

    def get_permanent_url(self, path: str) -> str:
        """Get a permanent URL for a file.

        For local storage, this returns a signed URL with a long expiration (1 year)
        since the /files endpoint requires authentication.
        """
        # Use a 1-year expiration for "permanent" URLs
        signed_url = self.get_download_signed_url(path, expiration_seconds=365 * 24 * 3600)
        if signed_url:
            return signed_url
        # Fallback to public URL if file doesn't exist (shouldn't happen in normal use)
        return self.get_public_url(path)

    def upload_and_get_permanent_url(
        self, content: BinaryIO, path: str, content_type: str | None = None
    ) -> str:
        """Upload content and return permanent URL."""
        self.write(content, path, content_type)
        return self.get_permanent_url(path)
