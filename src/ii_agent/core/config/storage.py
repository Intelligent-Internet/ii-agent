"""Storage configuration settings."""

from typing import Literal, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

StorageProvider = Literal["gcs", "minio"]


class StorageSettings(BaseSettings):
    """Single-bucket storage configuration.

    Environment variables use STORAGE_ prefix::

        STORAGE_PROVIDER=gcs
        STORAGE_PROJECT_ID=my-project
        STORAGE_BUCKET_NAME=my-bucket
        STORAGE_CUSTOM_DOMAIN=files.example.com
    """

    model_config = SettingsConfigDict(
        env_prefix="STORAGE_",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    provider: StorageProvider = Field(
        default="gcs",
        description="Storage provider (gcs, minio)",
    )

    project_id: Optional[str] = Field(
        default=None,
        description="GCS project ID",
    )

    bucket_name: Optional[str] = Field(
        default=None,
        description="GCS bucket name",
    )

    custom_domain: Optional[str] = Field(
        default=None,
        description="Custom domain for permanent file URLs",
    )

    file_upload_size_limit: int = Field(
        default=100 * 1024 * 1024,
        description="Maximum file upload size in bytes",
        gt=0,
    )

    signed_url_ttl_seconds: int = Field(
        default=7 * 24 * 3600,
        description="Signed URL time-to-live in seconds (default 7 days)",
        gt=0,
    )

    # Browser-reachable backend base URL.  When set, file upload/download
    # URLs are routed through the backend proxy instead of directly to the
    # storage provider.  Required for local Docker deployments where MinIO
    # is only reachable inside the Docker network.
    # Example: http://192.168.2.2:8000
    serve_base_url: Optional[str] = Field(
        default=None,
        description=(
            "Browser-reachable backend base URL for proxied storage. "
            "When set, file URLs route through the backend instead of "
            "directly to the storage provider."
        ),
    )

    # MinIO provider settings
    minio_endpoint: str = Field(
        default="localhost:9000",
        description="MinIO server endpoint (host:port)",
    )

    minio_access_key: str = Field(
        default="minioadmin",
        description="MinIO access key",
    )

    minio_secret_key: str = Field(
        default="minioadmin",
        description="MinIO secret key",
    )

    minio_secure: bool = Field(
        default=False,
        description="Use HTTPS for MinIO connections",
    )

    minio_region: str = Field(
        default="us-east-1",
        description="MinIO region",
    )

    def validate_for_provider(self) -> None:
        """Validate required fields for the selected provider."""
        if self.provider == "gcs":
            if not self.project_id:
                raise ValueError("GCS project ID is required. Set STORAGE_PROJECT_ID.")
            if not self.bucket_name:
                raise ValueError("GCS bucket name is required. Set STORAGE_BUCKET_NAME.")
        elif self.provider == "minio":
            if not self.bucket_name:
                raise ValueError("MinIO bucket name is required. Set STORAGE_BUCKET_NAME.")
