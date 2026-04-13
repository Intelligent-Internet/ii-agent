"""MinIO storage provider — async wrapper around sync minio-py."""

from __future__ import annotations

import datetime
import io
from typing import BinaryIO

import httpx
from fastapi.concurrency import run_in_threadpool
from minio import Minio
from minio.error import S3Error

from ii_agent.core.storage.exceptions import (
    StorageObjectNotFoundError,
    StoragePermissionError,
)
from ii_agent.core.storage.providers.base import StorageProvider


class MinIOProvider(StorageProvider):
    """Async MinIO provider using sync minio-py in a thread pool."""

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket_name: str,
        *,
        region: str = "us-east-1",
        secure: bool = False,
        custom_domain: str | None = None,
        proxy_base_url: str | None = None,
    ) -> None:
        self._client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            region=region,
            secure=secure,
        )
        self._bucket_name = bucket_name
        self._endpoint = endpoint
        self._secure = secure
        self._custom_domain = custom_domain
        self._proxy_base_url = proxy_base_url.rstrip("/") if proxy_base_url else None

        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        """Create the bucket if it doesn't already exist."""
        if not self._client.bucket_exists(self._bucket_name):
            self._client.make_bucket(self._bucket_name)

    # ------------------------------------------------------------------
    # Helper: run sync in thread
    # ------------------------------------------------------------------

    @staticmethod
    async def _run_sync(fn, *args, **kwargs):  # noqa: ANN001, ANN003
        return await run_in_threadpool(fn, *args, **kwargs)

    # ------------------------------------------------------------------
    # Exception mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _handle_s3_error(exc: S3Error, path: str) -> None:
        """Map S3Error to domain exceptions."""
        code = exc.code
        if code in ("NoSuchKey", "NoSuchBucket"):
            raise StorageObjectNotFoundError(f"Object '{path}' not found.") from exc
        if code in ("AccessDenied", "InvalidAccessKeyId", "SignatureDoesNotMatch"):
            raise StoragePermissionError(str(exc)) from exc
        raise exc

    # ------------------------------------------------------------------
    # StorageProvider interface
    # ------------------------------------------------------------------

    async def write(self, path: str, content: BinaryIO, content_type: str | None = None) -> str:
        def _upload() -> str:
            content.seek(0)
            data = content.read()
            self._client.put_object(
                self._bucket_name,
                path,
                io.BytesIO(data),
                length=len(data),
                content_type=content_type or "application/octet-stream",
            )
            return path

        try:
            return await self._run_sync(_upload)
        except S3Error as exc:
            self._handle_s3_error(exc, path)
            return path  # unreachable, satisfies type checker

    async def write_from_url(
        self, source_url: str, path: str, content_type: str | None = None
    ) -> str:
        async with httpx.AsyncClient() as client:
            response = await client.get(source_url)
            response.raise_for_status()
            data = response.content

        def _upload() -> str:
            self._client.put_object(
                self._bucket_name,
                path,
                io.BytesIO(data),
                length=len(data),
                content_type=content_type or "application/octet-stream",
            )
            return path

        try:
            return await self._run_sync(_upload)
        except S3Error as exc:
            self._handle_s3_error(exc, path)
            return path

    async def read(self, path: str) -> BinaryIO:
        def _download() -> BinaryIO:
            try:
                response = self._client.get_object(self._bucket_name, path)
                buf = io.BytesIO(response.read())
                response.close()
                response.release_conn()
                buf.seek(0)
                return buf
            except S3Error as exc:
                self._handle_s3_error(exc, path)
                raise  # unreachable

        return await self._run_sync(_download)

    async def exists(self, path: str) -> bool:
        def _exists() -> bool:
            try:
                self._client.stat_object(self._bucket_name, path)
                return True
            except S3Error as exc:
                if exc.code == "NoSuchKey":
                    return False
                raise

        return await self._run_sync(_exists)

    async def size(self, path: str) -> int:
        def _size() -> int:
            try:
                stat = self._client.stat_object(self._bucket_name, path)
                return stat.size
            except S3Error as exc:
                self._handle_s3_error(exc, path)
                return 0  # unreachable

        return await self._run_sync(_size)

    async def delete(self, path: str) -> None:
        def _delete() -> None:
            try:
                # MinIO remove_object doesn't raise on missing keys by default,
                # so we check existence first for consistent behaviour.
                self._client.stat_object(self._bucket_name, path)
                self._client.remove_object(self._bucket_name, path)
            except S3Error as exc:
                self._handle_s3_error(exc, path)

        await self._run_sync(_delete)

    async def copy(self, source_path: str, dest_path: str) -> str:
        def _copy() -> str:
            from minio.commonconfig import CopySource

            try:
                self._client.copy_object(
                    self._bucket_name,
                    dest_path,
                    CopySource(self._bucket_name, source_path),
                )
                return dest_path
            except S3Error as exc:
                self._handle_s3_error(exc, source_path)
                return dest_path  # unreachable

        return await self._run_sync(_copy)

    async def signed_download_url(self, path: str, expiry_seconds: int = 3600) -> str:
        if self._proxy_base_url:
            return f"{self._proxy_base_url}/d/{path}"

        def _sign() -> str:
            return self._client.presigned_get_object(
                self._bucket_name,
                path,
                expires=datetime.timedelta(seconds=expiry_seconds),
            )

        return await self._run_sync(_sign)

    async def signed_download_urls_batch(
        self, paths: list[str], expiry_seconds: int = 3600
    ) -> list[str | None]:
        if not paths:
            return []

        if self._proxy_base_url:
            return [f"{self._proxy_base_url}/d/{p}" for p in paths]

        def _sign_batch() -> list[str | None]:
            urls: list[str | None] = []
            for p in paths:
                try:
                    url = self._client.presigned_get_object(
                        self._bucket_name,
                        p,
                        expires=datetime.timedelta(seconds=expiry_seconds),
                    )
                    urls.append(url)
                except Exception:
                    urls.append(None)
            return urls

        return await self._run_sync(_sign_batch)

    async def signed_upload_url(
        self, path: str, content_type: str, expiry_seconds: int = 3600
    ) -> str:
        def _sign() -> str:
            return self._client.presigned_put_object(
                self._bucket_name,
                path,
                expires=datetime.timedelta(seconds=expiry_seconds),
            )

        return await self._run_sync(_sign)

    def public_url(self, path: str) -> str:
        if self._proxy_base_url:
            return f"{self._proxy_base_url}/d/{path}"
        if self._custom_domain:
            return f"https://{self._custom_domain}/{path}"
        scheme = "https" if self._secure else "http"
        return f"{scheme}://{self._endpoint}/{self._bucket_name}/{path}"
