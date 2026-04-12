"""Unit tests for MinIOProvider._handle_s3_error exception mapping."""

from __future__ import annotations

import pytest

from ii_agent.core.storage.exceptions import (
    StorageObjectNotFoundError,
    StoragePermissionError,
)
from ii_agent.core.storage.providers.minio import MinIOProvider

pytestmark = pytest.mark.unit


def _s3_error(code: str) -> Exception:
    """Create a minimal S3Error-like exception with .code attribute."""
    exc = type("S3Error", (Exception,), {"code": code})(code)
    return exc


class TestHandleS3Error:
    def test_no_such_key_raises_not_found(self):
        exc = _s3_error("NoSuchKey")
        with pytest.raises(StorageObjectNotFoundError, match="not found"):
            MinIOProvider._handle_s3_error(exc, "some/path.txt")

    def test_no_such_bucket_raises_not_found(self):
        exc = _s3_error("NoSuchBucket")
        with pytest.raises(StorageObjectNotFoundError, match="not found"):
            MinIOProvider._handle_s3_error(exc, "some/path.txt")

    def test_access_denied_raises_permission(self):
        exc = _s3_error("AccessDenied")
        with pytest.raises(StoragePermissionError):
            MinIOProvider._handle_s3_error(exc, "some/path.txt")

    def test_invalid_access_key_raises_permission(self):
        exc = _s3_error("InvalidAccessKeyId")
        with pytest.raises(StoragePermissionError):
            MinIOProvider._handle_s3_error(exc, "some/path.txt")

    def test_signature_mismatch_raises_permission(self):
        exc = _s3_error("SignatureDoesNotMatch")
        with pytest.raises(StoragePermissionError):
            MinIOProvider._handle_s3_error(exc, "some/path.txt")

    def test_unknown_code_reraises(self):
        exc = _s3_error("InternalError")
        with pytest.raises(Exception, match="InternalError"):
            MinIOProvider._handle_s3_error(exc, "some/path.txt")

    def test_not_found_includes_path_in_message(self):
        exc = _s3_error("NoSuchKey")
        with pytest.raises(StorageObjectNotFoundError, match="my/file.png"):
            MinIOProvider._handle_s3_error(exc, "my/file.png")
