"""Storage client singleton.

One bucket, one client, subfolder routing via PathResolver::

    from ii_agent.core.storage.client import get_storage

    storage = get_storage()
    await storage.write("users/abc/uploads/file.png", data)
    url = await storage.signed_download_url("users/abc/uploads/file.png")
"""

from __future__ import annotations

import logging
from typing import Optional

from ii_agent.core.config.settings import get_settings
from ii_agent.core.storage.providers.base import StorageProvider

logger = logging.getLogger(__name__)

_storage: Optional[StorageProvider] = None


def _create_storage() -> StorageProvider:
    """Create the storage provider from settings."""
    settings = get_settings()
    s = settings.storage

    if s.provider == "gcs":
        from ii_agent.core.storage.providers.gcs import GCSProvider

        if not s.project_id or not s.bucket_name:
            raise ValueError("GCS requires STORAGE_PROJECT_ID and STORAGE_BUCKET_NAME")
        return GCSProvider(
            project_id=s.project_id,
            bucket_name=s.bucket_name,
            custom_domain=s.custom_domain,
        )

    if s.provider == "minio":
        from ii_agent.core.storage.providers.minio import MinIOProvider

        if not s.bucket_name:
            raise ValueError("MinIO requires STORAGE_BUCKET_NAME")

        proxy_base = f"{s.serve_base_url.rstrip('/')}/storage" if s.serve_base_url else None
        return MinIOProvider(
            endpoint=s.minio_endpoint,
            access_key=s.minio_access_key,
            secret_key=s.minio_secret_key,
            bucket_name=s.bucket_name,
            region=s.minio_region,
            secure=s.minio_secure,
            custom_domain=s.custom_domain,
            proxy_base_url=proxy_base,
        )

    raise ValueError(f"Unknown storage provider: {s.provider}")


def get_storage() -> StorageProvider:
    """Get the storage provider singleton."""
    global _storage
    if _storage is None:
        _storage = _create_storage()
    return _storage


def set_storage(provider: StorageProvider) -> None:
    """Inject a custom storage provider (for testing)."""
    global _storage
    _storage = provider


def reset_storage() -> None:
    """Reset the storage singleton."""
    global _storage
    _storage = None
