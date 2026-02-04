"""
Storage Helper for Skills

Provides a simplified interface for skills to upload files to cloud storage
and track outputs in the database.

Integrates with:
- ii-agent GCS storage infrastructure
- DataStore for output tracking
"""

import io
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, BinaryIO, Dict, Any, Tuple

logger = logging.getLogger(__name__)

# Content type mappings
CONTENT_TYPES = {
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pdf": "application/pdf",
    ".json": "application/json",
    ".html": "text/html",
    ".csv": "text/csv",
    ".txt": "text/plain",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
}

# Output type mappings
OUTPUT_TYPES = {
    ".xlsx": "excel",
    ".xls": "excel",
    ".pptx": "powerpoint",
    ".ppt": "powerpoint",
    ".pdf": "pdf",
    ".json": "json",
    ".html": "html",
    ".csv": "csv",
    ".txt": "text",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
}


class SkillStorage:
    """
    Storage helper for skill outputs.

    Handles uploading files to GCS and tracking in the database.

    Usage:
        from ii_skills.shared.storage import get_skill_storage

        storage = get_skill_storage()

        # Upload an Excel file
        result = await storage.upload_file(
            user_id="...",
            skill_name="ib_toolkit",
            file_path="/path/to/model.xlsx",
            module_name="lbo_model",
            company_symbol="TOU.TO",
        )

        print(result["storage_url"])  # Public URL to the file
    """

    def __init__(self):
        """Initialize the storage helper."""
        self._storage_client = None
        self._datastore = None
        self._config_loaded = False
        self._load_config()

    def _load_config(self):
        """Load storage configuration."""
        try:
            from ii_agent.core.config.ii_agent_config import II_AGENT_CONFIG

            self._project_id = getattr(II_AGENT_CONFIG, "GCP_PROJECT_ID", None)
            self._bucket_name = getattr(II_AGENT_CONFIG, "GCS_BUCKET_NAME", None)
            self._custom_domain = getattr(II_AGENT_CONFIG, "GCS_CUSTOM_DOMAIN", None)
            self._config_loaded = True

            if self._bucket_name:
                logger.info(f"Storage configured with bucket: {self._bucket_name}")
            else:
                logger.warning("GCS bucket not configured - storage will use local files only")
        except ImportError:
            logger.warning("ii-agent config not available - running in standalone mode")
            self._config_loaded = False

    @property
    def is_available(self) -> bool:
        """Check if cloud storage is available."""
        return self._config_loaded and self._bucket_name is not None

    def _get_storage_client(self):
        """Get or create the storage client."""
        if self._storage_client is None and self.is_available:
            try:
                from ii_agent.storage import create_storage_client

                self._storage_client = create_storage_client(
                    storage_provider="gcs",
                    project_id=self._project_id,
                    bucket_name=self._bucket_name,
                    custom_domain=self._custom_domain,
                )
            except Exception as e:
                logger.error(f"Failed to create storage client: {e}")
                return None
        return self._storage_client

    def _get_datastore(self):
        """Get the datastore for output tracking."""
        if self._datastore is None:
            try:
                from ii_skills.shared.datastore import get_datastore
                self._datastore = get_datastore()
            except ImportError:
                logger.warning("DataStore not available")
        return self._datastore

    def _get_content_type(self, file_path: str) -> str:
        """Get content type from file extension."""
        ext = Path(file_path).suffix.lower()
        return CONTENT_TYPES.get(ext, "application/octet-stream")

    def _get_output_type(self, file_path: str) -> str:
        """Get output type from file extension."""
        ext = Path(file_path).suffix.lower()
        return OUTPUT_TYPES.get(ext, "file")

    def _generate_storage_path(
        self,
        user_id: str,
        skill_name: str,
        file_name: str,
        module_name: Optional[str] = None,
    ) -> str:
        """
        Generate a storage path for the file.

        Format: skills/{skill_name}/{user_id}/{YYYY-MM}/{module_name}/{filename}
        """
        now = datetime.utcnow()
        date_folder = now.strftime("%Y-%m")

        parts = ["skills", skill_name, user_id, date_folder]
        if module_name:
            parts.append(module_name)
        parts.append(file_name)

        return "/".join(parts)

    async def upload_file(
        self,
        user_id: str,
        skill_name: str,
        file_path: str,
        module_name: Optional[str] = None,
        company_symbol: Optional[str] = None,
        session_id: Optional[str] = None,
        input_parameters: Optional[Dict] = None,
        metadata: Optional[Dict] = None,
        tags: Optional[list] = None,
        track_output: bool = True,
    ) -> Dict[str, Any]:
        """
        Upload a file to storage and optionally track it in the database.

        Args:
            user_id: User ID
            skill_name: Name of the skill (e.g., "ib_toolkit")
            file_path: Local path to the file
            module_name: Specific module (e.g., "lbo_model")
            company_symbol: Related company symbol
            session_id: Session ID for tracking
            input_parameters: Parameters used to generate the file
            metadata: Additional metadata
            tags: Tags for searching
            track_output: Whether to track in database

        Returns:
            Dict with storage_path, storage_url, local_path, output_id
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        file_name = file_path.name
        file_size = file_path.stat().st_size
        output_type = self._get_output_type(str(file_path))
        content_type = self._get_content_type(str(file_path))

        result = {
            "local_path": str(file_path),
            "file_name": file_name,
            "file_size": file_size,
            "output_type": output_type,
            "storage_path": None,
            "storage_url": None,
            "output_id": None,
        }

        # Upload to cloud storage if available
        storage_client = self._get_storage_client()
        if storage_client:
            try:
                storage_path = self._generate_storage_path(
                    user_id, skill_name, file_name, module_name
                )

                with open(file_path, "rb") as f:
                    storage_url = storage_client.upload_and_get_permanent_url(
                        content=f,
                        path=storage_path,
                        content_type=content_type,
                    )

                result["storage_path"] = storage_path
                result["storage_url"] = storage_url
                logger.info(f"Uploaded {file_name} to {storage_path}")

            except Exception as e:
                logger.error(f"Failed to upload to storage: {e}")
                # Continue without cloud storage

        # Track in database if enabled
        if track_output:
            datastore = self._get_datastore()
            if datastore and datastore.is_connected:
                try:
                    output_id = await datastore.save_output(
                        user_id=user_id,
                        skill_name=skill_name,
                        output_type=output_type,
                        file_name=file_name,
                        file_size=file_size,
                        storage_path=result.get("storage_path"),
                        storage_url=result.get("storage_url"),
                        local_path=str(file_path),
                        module_name=module_name,
                        session_id=session_id,
                        input_parameters=input_parameters,
                        company_symbol=company_symbol,
                        metadata=metadata,
                        tags=tags,
                    )
                    result["output_id"] = output_id
                    logger.info(f"Tracked output with ID: {output_id}")
                except Exception as e:
                    logger.error(f"Failed to track output: {e}")

        return result

    async def upload_bytes(
        self,
        user_id: str,
        skill_name: str,
        content: bytes,
        file_name: str,
        module_name: Optional[str] = None,
        company_symbol: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Upload bytes directly to storage.

        Args:
            user_id: User ID
            skill_name: Name of the skill
            content: File content as bytes
            file_name: Name for the file
            module_name: Specific module
            company_symbol: Related company symbol
            **kwargs: Additional arguments passed to upload tracking

        Returns:
            Dict with storage_path, storage_url, output_id
        """
        output_type = self._get_output_type(file_name)
        content_type = self._get_content_type(file_name)
        file_size = len(content)

        result = {
            "file_name": file_name,
            "file_size": file_size,
            "output_type": output_type,
            "storage_path": None,
            "storage_url": None,
            "output_id": None,
        }

        # Upload to cloud storage if available
        storage_client = self._get_storage_client()
        if storage_client:
            try:
                storage_path = self._generate_storage_path(
                    user_id, skill_name, file_name, module_name
                )

                content_io = io.BytesIO(content)
                storage_url = storage_client.upload_and_get_permanent_url(
                    content=content_io,
                    path=storage_path,
                    content_type=content_type,
                )

                result["storage_path"] = storage_path
                result["storage_url"] = storage_url

            except Exception as e:
                logger.error(f"Failed to upload to storage: {e}")

        # Track in database
        datastore = self._get_datastore()
        if datastore and datastore.is_connected:
            try:
                output_id = await datastore.save_output(
                    user_id=user_id,
                    skill_name=skill_name,
                    output_type=output_type,
                    file_name=file_name,
                    file_size=file_size,
                    storage_path=result.get("storage_path"),
                    storage_url=result.get("storage_url"),
                    module_name=module_name,
                    company_symbol=company_symbol,
                    **kwargs,
                )
                result["output_id"] = output_id
            except Exception as e:
                logger.error(f"Failed to track output: {e}")

        return result

    def get_download_url(
        self,
        storage_path: str,
        expiration_seconds: int = 3600,
    ) -> Optional[str]:
        """
        Get a signed download URL for a file.

        Args:
            storage_path: Path in storage
            expiration_seconds: URL expiration time

        Returns:
            Signed URL or None
        """
        storage_client = self._get_storage_client()
        if storage_client:
            try:
                return storage_client.get_download_signed_url(
                    storage_path, expiration_seconds
                )
            except Exception as e:
                logger.error(f"Failed to get download URL: {e}")
        return None

    def download_file(
        self,
        storage_path: str,
        local_path: str,
    ) -> bool:
        """
        Download a file from storage to local path.

        Args:
            storage_path: Path in storage
            local_path: Local destination path

        Returns:
            True if successful
        """
        storage_client = self._get_storage_client()
        if storage_client:
            try:
                content = storage_client.read(storage_path)

                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                with open(local_path, "wb") as f:
                    f.write(content.read())

                return True
            except Exception as e:
                logger.error(f"Failed to download file: {e}")
        return False


# Global storage instance
_storage_instance: Optional[SkillStorage] = None


def get_skill_storage() -> SkillStorage:
    """Get or create the global SkillStorage instance."""
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = SkillStorage()
    return _storage_instance
