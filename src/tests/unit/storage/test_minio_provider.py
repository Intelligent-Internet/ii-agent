"""Comprehensive unit tests for ``MinIOProvider``.

The provider wraps the synchronous ``minio-py`` SDK in a thread pool. We
mock the underlying ``Minio`` client so these tests stay hermetic — no
real MinIO server is required.

These tests exercise the public ``StorageProvider`` interface for the
local-storage path (the prod path goes through ``GCSProvider`` which is
covered separately). Coverage targets every public method including the
proxy-URL alternate flow used by single-binary local deployments.
"""

from __future__ import annotations

import datetime
import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from minio.error import S3Error

from ii_agent.core.storage.exceptions import (
    StorageObjectNotFoundError,
    StoragePermissionError,
)
from ii_agent.core.storage.providers.minio import MinIOProvider


pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_s3_error(code: str, message: str = "") -> S3Error:
    """Build a minio S3Error with the given .code attribute.

    The real ``S3Error`` constructor takes 8 positional args; rather than
    fighting that signature we synthesise a stand-in with the only
    attribute the production code reads.
    """
    err = S3Error.__new__(S3Error)
    err.code = code  # type: ignore[attr-defined]
    err.message = message or code
    err.args = (message or code,)
    return err


def _make_provider(
    *,
    bucket_exists: bool = True,
    proxy_base_url: str | None = None,
    custom_domain: str | None = None,
    secure: bool = False,
) -> tuple[MinIOProvider, MagicMock]:
    """Construct a MinIOProvider with its underlying Minio client mocked."""

    fake_client = MagicMock(name="MinioClient")
    fake_client.bucket_exists.return_value = bucket_exists
    fake_client.make_bucket = MagicMock()

    with patch(
        "ii_agent.core.storage.providers.minio.Minio",
        return_value=fake_client,
    ):
        provider = MinIOProvider(
            endpoint="minio:9000",
            access_key="ak",
            secret_key="sk",
            bucket_name="ii-bucket",
            secure=secure,
            custom_domain=custom_domain,
            proxy_base_url=proxy_base_url,
        )
    return provider, fake_client


# ---------------------------------------------------------------------------
# Construction & bucket bootstrap
# ---------------------------------------------------------------------------


class TestConstructionAndBucketBootstrap:
    def test_existing_bucket_is_not_recreated(self):
        _, client = _make_provider(bucket_exists=True)
        client.bucket_exists.assert_called_once_with("ii-bucket")
        client.make_bucket.assert_not_called()

    def test_missing_bucket_is_created_at_init(self):
        _, client = _make_provider(bucket_exists=False)
        client.make_bucket.assert_called_once_with("ii-bucket")

    def test_proxy_base_url_is_normalised(self):
        provider, _ = _make_provider(proxy_base_url="http://proxy/storage/")
        # trailing slash stripped
        assert provider._proxy_base_url == "http://proxy/storage"

    def test_no_proxy_base_url_stored_as_none(self):
        provider, _ = _make_provider(proxy_base_url=None)
        assert provider._proxy_base_url is None


# ---------------------------------------------------------------------------
# write
# ---------------------------------------------------------------------------


class TestWrite:
    @pytest.mark.asyncio
    async def test_writes_bytes_with_explicit_content_type(self):
        provider, client = _make_provider()
        buf = io.BytesIO(b"hello world")

        path = await provider.write("foo/bar.txt", buf, "text/plain")

        assert path == "foo/bar.txt"
        client.put_object.assert_called_once()
        args, kwargs = client.put_object.call_args
        assert args[0] == "ii-bucket"
        assert args[1] == "foo/bar.txt"
        assert kwargs["length"] == len(b"hello world")
        assert kwargs["content_type"] == "text/plain"

    @pytest.mark.asyncio
    async def test_default_content_type_is_octet_stream(self):
        provider, client = _make_provider()
        await provider.write("a.bin", io.BytesIO(b"\x00"))
        assert client.put_object.call_args.kwargs["content_type"] == "application/octet-stream"

    @pytest.mark.asyncio
    async def test_seeks_to_start_before_reading(self):
        """If caller passed an already-consumed buffer, write must reset it."""
        provider, client = _make_provider()
        buf = io.BytesIO(b"payload")
        buf.read()  # exhaust
        assert buf.tell() == len(b"payload")

        await provider.write("file.txt", buf, "text/plain")

        assert client.put_object.call_args.kwargs["length"] == len(b"payload")

    @pytest.mark.asyncio
    async def test_s3_error_is_translated(self):
        provider, client = _make_provider()
        client.put_object.side_effect = _make_s3_error("AccessDenied")

        with pytest.raises(StoragePermissionError):
            await provider.write("p.txt", io.BytesIO(b"x"))


# ---------------------------------------------------------------------------
# write_from_url
# ---------------------------------------------------------------------------


class TestWriteFromUrl:
    @pytest.mark.asyncio
    async def test_downloads_then_uploads(self):
        provider, client = _make_provider()

        fake_response = MagicMock()
        fake_response.content = b"remote-bytes"
        fake_response.raise_for_status = MagicMock()
        fake_get = AsyncMock(return_value=fake_response)
        fake_async_client = MagicMock()
        fake_async_client.get = fake_get
        fake_async_client.__aenter__ = AsyncMock(return_value=fake_async_client)
        fake_async_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "ii_agent.core.storage.providers.minio.httpx.AsyncClient",
            return_value=fake_async_client,
        ):
            path = await provider.write_from_url(
                "https://example.com/foo.png",
                "users/u/media/abc.png",
                "image/png",
            )

        assert path == "users/u/media/abc.png"
        fake_get.assert_awaited_once_with("https://example.com/foo.png")
        client.put_object.assert_called_once()
        kwargs = client.put_object.call_args.kwargs
        assert kwargs["length"] == len(b"remote-bytes")
        assert kwargs["content_type"] == "image/png"

    @pytest.mark.asyncio
    async def test_s3_error_during_upload_translated(self):
        provider, client = _make_provider()
        client.put_object.side_effect = _make_s3_error("NoSuchBucket")

        fake_response = MagicMock()
        fake_response.content = b"x"
        fake_response.raise_for_status = MagicMock()
        fake_async_client = MagicMock()
        fake_async_client.get = AsyncMock(return_value=fake_response)
        fake_async_client.__aenter__ = AsyncMock(return_value=fake_async_client)
        fake_async_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "ii_agent.core.storage.providers.minio.httpx.AsyncClient",
            return_value=fake_async_client,
        ):
            with pytest.raises(StorageObjectNotFoundError):
                await provider.write_from_url("https://x", "p.txt", None)


# ---------------------------------------------------------------------------
# read / exists / size / delete
# ---------------------------------------------------------------------------


class TestRead:
    @pytest.mark.asyncio
    async def test_returns_seekable_buffer_with_bytes(self):
        provider, client = _make_provider()
        fake_response = MagicMock()
        fake_response.read.return_value = b"hello"
        client.get_object.return_value = fake_response

        buf = await provider.read("a.txt")

        assert buf.read() == b"hello"
        fake_response.close.assert_called_once()
        fake_response.release_conn.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_object_raises_not_found(self):
        provider, client = _make_provider()
        client.get_object.side_effect = _make_s3_error("NoSuchKey")

        with pytest.raises(StorageObjectNotFoundError):
            await provider.read("missing")


class TestExists:
    @pytest.mark.asyncio
    async def test_returns_true_when_object_present(self):
        provider, client = _make_provider()
        client.stat_object.return_value = MagicMock()

        assert await provider.exists("a") is True

    @pytest.mark.asyncio
    async def test_returns_false_on_no_such_key(self):
        provider, client = _make_provider()
        client.stat_object.side_effect = _make_s3_error("NoSuchKey")

        assert await provider.exists("a") is False

    @pytest.mark.asyncio
    async def test_other_s3_error_propagates(self):
        provider, client = _make_provider()
        client.stat_object.side_effect = _make_s3_error("InternalError")

        with pytest.raises(S3Error):
            await provider.exists("a")


class TestSize:
    @pytest.mark.asyncio
    async def test_returns_size(self):
        provider, client = _make_provider()
        client.stat_object.return_value = MagicMock(size=4242)

        assert await provider.size("a") == 4242

    @pytest.mark.asyncio
    async def test_missing_object_raises(self):
        provider, client = _make_provider()
        client.stat_object.side_effect = _make_s3_error("NoSuchKey")

        with pytest.raises(StorageObjectNotFoundError):
            await provider.size("a")


class TestDelete:
    @pytest.mark.asyncio
    async def test_deletes_when_object_exists(self):
        provider, client = _make_provider()
        client.stat_object.return_value = MagicMock()

        await provider.delete("file.txt")

        client.remove_object.assert_called_once_with("ii-bucket", "file.txt")

    @pytest.mark.asyncio
    async def test_missing_object_raises_not_found(self):
        provider, client = _make_provider()
        client.stat_object.side_effect = _make_s3_error("NoSuchKey")

        with pytest.raises(StorageObjectNotFoundError):
            await provider.delete("file.txt")
        client.remove_object.assert_not_called()


# ---------------------------------------------------------------------------
# copy
# ---------------------------------------------------------------------------


class TestCopy:
    @pytest.mark.asyncio
    async def test_copies_within_bucket(self):
        provider, client = _make_provider()

        path = await provider.copy("a.txt", "b.txt")

        assert path == "b.txt"
        args, _ = client.copy_object.call_args
        assert args[0] == "ii-bucket"
        assert args[1] == "b.txt"
        # CopySource is constructed inline
        assert getattr(args[2], "bucket_name", None) == "ii-bucket"
        assert getattr(args[2], "object_name", None) == "a.txt"

    @pytest.mark.asyncio
    async def test_copy_failure_translated(self):
        provider, client = _make_provider()
        client.copy_object.side_effect = _make_s3_error("AccessDenied")

        with pytest.raises(StoragePermissionError):
            await provider.copy("a.txt", "b.txt")


# ---------------------------------------------------------------------------
# Signed URLs
# ---------------------------------------------------------------------------


class TestSignedDownloadUrl:
    @pytest.mark.asyncio
    async def test_uses_proxy_when_configured(self):
        provider, client = _make_provider(proxy_base_url="http://proxy/storage")
        url = await provider.signed_download_url("users/abc.png", expiry_seconds=10)
        assert url == "http://proxy/storage/d/users/abc.png"
        client.presigned_get_object.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_presigned_when_no_proxy(self):
        provider, client = _make_provider(proxy_base_url=None)
        client.presigned_get_object.return_value = "https://signed/?sig=xyz"

        url = await provider.signed_download_url("a.txt", expiry_seconds=120)

        assert url == "https://signed/?sig=xyz"
        client.presigned_get_object.assert_called_once()
        args, kwargs = client.presigned_get_object.call_args
        assert args[0] == "ii-bucket"
        assert args[1] == "a.txt"
        assert kwargs["expires"] == datetime.timedelta(seconds=120)


class TestSignedDownloadUrlsBatch:
    @pytest.mark.asyncio
    async def test_empty_input_returns_empty_list(self):
        provider, _ = _make_provider()
        assert await provider.signed_download_urls_batch([]) == []

    @pytest.mark.asyncio
    async def test_proxy_short_circuits_signing(self):
        provider, client = _make_provider(proxy_base_url="http://proxy/storage")

        urls = await provider.signed_download_urls_batch(["a.png", "b.png"])

        assert urls == ["http://proxy/storage/d/a.png", "http://proxy/storage/d/b.png"]
        client.presigned_get_object.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_none_when_individual_signing_fails(self):
        provider, client = _make_provider()

        def _signer(bucket: str, path: str, expires=None):
            if path == "bad":
                raise RuntimeError("nope")
            return f"https://signed/{path}"

        client.presigned_get_object.side_effect = _signer

        urls = await provider.signed_download_urls_batch(["good", "bad"])

        assert urls == ["https://signed/good", None]


class TestSignedUploadUrl:
    @pytest.mark.asyncio
    async def test_returns_presigned_put(self):
        provider, client = _make_provider()
        client.presigned_put_object.return_value = "https://signed-upload/"

        url = await provider.signed_upload_url("p.txt", "text/plain", 60)

        assert url == "https://signed-upload/"
        kwargs = client.presigned_put_object.call_args.kwargs
        assert kwargs["expires"] == datetime.timedelta(seconds=60)


# ---------------------------------------------------------------------------
# public_url
# ---------------------------------------------------------------------------


class TestPublicUrl:
    def test_proxy_takes_precedence(self):
        provider, _ = _make_provider(
            proxy_base_url="http://proxy/storage",
            custom_domain="cdn.example.com",
            secure=True,
        )
        assert provider.public_url("a.png") == "http://proxy/storage/d/a.png"

    def test_custom_domain_used_when_no_proxy(self):
        provider, _ = _make_provider(custom_domain="cdn.example.com", secure=True)
        assert provider.public_url("a.png") == "https://cdn.example.com/a.png"

    def test_falls_back_to_endpoint_url(self):
        provider, _ = _make_provider(secure=False)
        assert provider.public_url("foo/bar.png") == "http://minio:9000/ii-bucket/foo/bar.png"

    def test_secure_endpoint_uses_https(self):
        provider, _ = _make_provider(secure=True)
        assert provider.public_url("foo.png") == "https://minio:9000/ii-bucket/foo.png"
