from pydantic_settings import BaseSettings
from pydantic import model_validator
from typing import Literal, Optional


class StorageConfig(BaseSettings):
    storage_provider: Literal["gcs", "local"] = "local"  # Default to local for easy setup

    # GCS settings (only required if storage_provider == "gcs")
    gcs_bucket_name: Optional[str] = None
    gcs_project_id: Optional[str] = None

    # Local storage settings
    local_storage_path: str = "/.ii_agent/storage"

    @model_validator(mode="after")
    def validate_provider_settings(self) -> "StorageConfig":
        """Validate that required fields are set for the chosen provider."""
        if self.storage_provider == "gcs":
            if not self.gcs_bucket_name or not self.gcs_project_id:
                raise ValueError(
                    "gcs_bucket_name and gcs_project_id are required when using GCS storage. "
                    "Set STORAGE_PROVIDER=local to use local filesystem storage instead."
                )
        return self