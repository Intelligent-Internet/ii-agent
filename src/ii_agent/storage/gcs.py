"""Google Cloud Storage provider implementation."""

import io
import requests
import datetime
from typing import BinaryIO
from google.cloud import storage
from .base import BaseStorage


class GCS(BaseStorage):
    """Google Cloud Storage provider for file storage."""

    def __init__(
        self, project_id: str, bucket_name: str, custom_domain: str | None = None
    ):
        self.client = storage.Client(project=project_id)
        self.bucket = self.client.bucket(bucket_name)
        self.custom_domain = custom_domain

    def write(
        self, content: BinaryIO, path: str, content_type: str | None = None
    ) -> str:
        # Get a reference to the blob (i.e., the file in GCS)
        blob = self.bucket.blob(path)

        # Reset file pointer to the beginning before uploading
        content.seek(0)

        blob.upload_from_file(content, content_type=content_type)

        return blob.public_url

    def write_from_url(
        self, url: str, path: str, content_type: str | None = None
    ) -> str:
        blob = self.bucket.blob(path)
        with requests.get(url, stream=True) as response:
            response.raise_for_status()
            blob.upload_from_file(response.raw, content_type=content_type)

        return blob.public_url

    def read(self, path: str) -> BinaryIO:
        blob = self.bucket.blob(path)
        if not blob.exists():
            raise FileNotFoundError(
                f"File '{path}' not found in bucket '{self.bucket.name}'."
            )

        # Create an in-memory binary stream to hold the file data.
        file_obj = io.BytesIO()

        blob.download_to_file(file_obj)

        # Reset the stream's position to the beginning so it can be read from.
        file_obj.seek(0)

        return file_obj

    def get_download_signed_url(
        self, path: str, expiration_seconds: int = 3600, **kwargs
    ) -> str | None:
        blob = self.bucket.blob(path)

        if not blob.exists():
            raise FileNotFoundError(
                f"File '{path}' not found in bucket '{self.bucket_name}'."
            )

        # Generate the signed URL
        url = blob.generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(seconds=expiration_seconds),
            method="GET",
        )

        return url

    def get_upload_signed_url(
        self, path: str, content_type: str, expiration_seconds: int = 3600
    ) -> str | None:
        blob = self.bucket.blob(path)

        # Generate the signed URL for a PUT request
        url = blob.generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(seconds=expiration_seconds),
            method="PUT",
            content_type=content_type,
        )

        return url

    def is_exists(self, path: str) -> bool:
        blob = self.bucket.blob(path)
        return blob.exists()

    def get_file_size(self, path: str) -> int:
        blob = self.bucket.blob(path)
        if not blob.exists():
            raise FileNotFoundError(
                f"File '{path}' not found in bucket '{self.bucket.name}'."
            )
        blob.reload()
        return blob.size

    def get_public_url(self, path: str) -> str:
        # NOTE: assume that the blob is already public
        blob = self.bucket.blob(path)
        if not blob.exists():
            raise FileNotFoundError(
                f"File '{path}' not found in bucket '{self.bucket.name}'."
            )

        return blob.public_url

    def get_permanent_url(self, path: str) -> str:
        """Get permanent URL using custom domain or standard public URL."""
        blob = self.bucket.blob(path)
        if not blob.exists():
            raise FileNotFoundError(
                f"File '{path}' not found in bucket '{self.bucket.name}'."
            )

        # Make blob public if it isn't already
        try:
            blob.make_public()
        except Exception:
            # If already public or permission error, continue
            pass

        if self.custom_domain:
            return f"https://{self.custom_domain}/{path}"
        else:
            return blob.public_url

    def upload_and_get_permanent_url(
        self, content: BinaryIO, path: str, content_type: str | None = None
    ) -> str:
        """Upload file and return permanent URL."""
        # Upload the file
        blob = self.bucket.blob(path)
        content.seek(0)
        blob.upload_from_file(content, content_type=content_type)

        # Set cache control for better CDN performance
        blob.cache_control = "public, max-age=31536000"  # Cache for 1 year
        blob.patch()

        # Make the file publicly accessible
        try:
            blob.make_public()
        except Exception:
            # If already public or permission error, continue
            pass

        # Return permanent URL
        if self.custom_domain:
            return f"https://{self.custom_domain}/{path}"
        else:
            return blob.public_url
