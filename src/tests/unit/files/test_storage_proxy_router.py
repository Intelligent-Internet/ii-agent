"""Unit tests for files/storage_proxy_router.py."""

from __future__ import annotations

import io
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ii_agent.files.storage_proxy_router import router, _SAFE_PATH
from ii_agent.files.types import UploadStatus

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ASSET_ID = uuid.uuid4()
_STORAGE_PATH = f"users/{uuid.uuid4()}/files/{_ASSET_ID}.png"


def _make_asset(
    upload_status: UploadStatus = UploadStatus.PENDING, storage_path: str = _STORAGE_PATH
):
    return SimpleNamespace(
        id=_ASSET_ID,
        upload_status=upload_status,
        storage_path=storage_path,
    )


def _build_app(
    storage_read_result=None,
    storage_read_side_effect=None,
    storage_write_mock=None,
    file_repo_get_result=None,
):
    """Build a minimal FastAPI app with mocked dependencies."""

    mock_storage = AsyncMock()
    if storage_read_result is not None:
        mock_storage.read.return_value = storage_read_result
    if storage_read_side_effect is not None:
        mock_storage.read.side_effect = storage_read_side_effect
    if storage_write_mock is not None:
        mock_storage.write = storage_write_mock
    else:
        mock_storage.write = AsyncMock()

    mock_file_repo = AsyncMock()
    mock_file_repo.get_by_id.return_value = file_repo_get_result

    app = FastAPI()
    app.include_router(router)

    # Override FastAPI dependencies (file_repo, db session)
    from ii_agent.files.dependencies import get_file_repository
    from ii_agent.core.dependencies import _db_session_dependency

    app.dependency_overrides[get_file_repository] = lambda: mock_file_repo
    app.dependency_overrides[_db_session_dependency] = lambda: AsyncMock()

    return app, mock_storage, mock_file_repo


# ---------------------------------------------------------------------------
# _SAFE_PATH regex
# ---------------------------------------------------------------------------


class TestSafePathRegex:
    def test_allows_normal_path(self):
        assert _SAFE_PATH.match("users/abc-123/files/image.png")

    def test_rejects_path_traversal(self):
        assert not _SAFE_PATH.match("../../etc/passwd")

    def test_rejects_spaces(self):
        assert not _SAFE_PATH.match("path with spaces/file.txt")

    def test_rejects_special_chars(self):
        assert not _SAFE_PATH.match("path/<script>.txt")

    def test_allows_underscores_and_dots(self):
        assert _SAFE_PATH.match("a_b/c.d/e_f.txt")


# ---------------------------------------------------------------------------
# GET /storage/d/{path}
# ---------------------------------------------------------------------------


class TestProxyDownload:
    _PATCH_TARGET = "ii_agent.files.storage_proxy_router.get_storage"

    def test_download_returns_file_content(self):
        content = b"fake image data"
        app, mock_storage, _ = _build_app(storage_read_result=io.BytesIO(content))
        client = TestClient(app)

        with patch(self._PATCH_TARGET, return_value=mock_storage):
            resp = client.get(f"/storage/d/{_STORAGE_PATH}")

        assert resp.status_code == 200
        assert resp.content == content
        assert "image/png" in resp.headers["content-type"]
        assert resp.headers["cache-control"] == "public, max-age=86400"
        # The URL's last path segment becomes the suggested download filename.
        expected_filename = _STORAGE_PATH.rsplit("/", 1)[-1]
        disposition = resp.headers["content-disposition"]
        assert disposition.startswith("inline; ")
        assert f'filename="{expected_filename}"' in disposition
        assert f"filename*=UTF-8''{expected_filename}" in disposition
        mock_storage.read.assert_awaited_once_with(_STORAGE_PATH)

    def test_download_returns_404_for_missing_file(self):
        from ii_agent.core.storage.exceptions import StorageObjectNotFoundError

        app, mock_storage, _ = _build_app(
            storage_read_side_effect=StorageObjectNotFoundError("not found"),
        )
        client = TestClient(app)

        with patch(self._PATCH_TARGET, return_value=mock_storage):
            resp = client.get(f"/storage/d/{_STORAGE_PATH}")

        assert resp.status_code == 404

    def test_download_rejects_path_traversal(self):
        """Verify the _SAFE_PATH regex rejects '..' directly (unit-level)."""
        # HTTP clients normalize ".." before it reaches the handler, so we test
        # the regex guard directly rather than through the HTTP stack.
        assert not _SAFE_PATH.match("foo/../bar")
        assert not _SAFE_PATH.match("../../etc/passwd")

    def test_download_rejects_unsafe_path(self):
        app, _, _ = _build_app()
        client = TestClient(app)

        resp = client.get("/storage/d/a%20b/file.txt")
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# PUT /storage/upload/{asset_id}
# ---------------------------------------------------------------------------


class TestProxyUpload:
    _PATCH_TARGET = "ii_agent.files.storage_proxy_router.get_storage"

    def test_upload_succeeds_for_pending_asset(self):
        asset = _make_asset(upload_status=UploadStatus.PENDING)
        app, mock_storage, mock_repo = _build_app(file_repo_get_result=asset)
        client = TestClient(app)

        with patch(self._PATCH_TARGET, return_value=mock_storage):
            resp = client.put(
                f"/storage/upload/{_ASSET_ID}",
                content=b"file bytes",
                headers={"content-type": "image/png"},
            )

        assert resp.status_code == 200
        mock_storage.write.assert_awaited_once()
        call_args = mock_storage.write.call_args
        assert call_args[0][0] == _STORAGE_PATH

    def test_upload_returns_404_for_missing_asset(self):
        app, _, _ = _build_app(file_repo_get_result=None)
        client = TestClient(app)

        resp = client.put(
            f"/storage/upload/{uuid.uuid4()}",
            content=b"file bytes",
        )

        assert resp.status_code == 404

    def test_upload_returns_409_for_completed_asset(self):
        asset = _make_asset(upload_status=UploadStatus.COMPLETE)
        app, mock_storage, _ = _build_app(file_repo_get_result=asset)
        client = TestClient(app)

        resp = client.put(
            f"/storage/upload/{_ASSET_ID}",
            content=b"file bytes",
        )

        assert resp.status_code == 409
        mock_storage.write.assert_not_awaited()

    def test_upload_returns_409_for_failed_asset(self):
        asset = _make_asset(upload_status=UploadStatus.FAILED)
        app, _, _ = _build_app(file_repo_get_result=asset)
        client = TestClient(app)

        resp = client.put(
            f"/storage/upload/{_ASSET_ID}",
            content=b"file bytes",
        )

        assert resp.status_code == 409

    def test_upload_rejects_oversized_content_length_header(self):
        asset = _make_asset(upload_status=UploadStatus.PENDING)
        app, mock_storage, _ = _build_app(file_repo_get_result=asset)
        client = TestClient(app)

        with patch(self._PATCH_TARGET, return_value=mock_storage):
            resp = client.put(
                f"/storage/upload/{_ASSET_ID}",
                content=b"x",
                headers={"content-length": str(200 * 1024 * 1024)},  # 200 MB
            )

        assert resp.status_code == 413
        mock_storage.write.assert_not_awaited()

    def test_upload_ignores_invalid_content_length_header(self):
        """Non-numeric content-length is ignored; body size still checked."""
        asset = _make_asset(upload_status=UploadStatus.PENDING)
        app, mock_storage, _ = _build_app(file_repo_get_result=asset)
        client = TestClient(app)

        with patch(self._PATCH_TARGET, return_value=mock_storage):
            resp = client.put(
                f"/storage/upload/{_ASSET_ID}",
                content=b"small payload",
                headers={"content-length": "not-a-number"},
            )

        # Should succeed — the invalid header is ignored, body is within limits
        assert resp.status_code == 200
        mock_storage.write.assert_awaited_once()

    def test_upload_transitions_asset_to_complete(self):
        """After successful upload, asset.upload_status is set to COMPLETE."""
        asset = _make_asset(upload_status=UploadStatus.PENDING)
        app, mock_storage, _ = _build_app(file_repo_get_result=asset)
        client = TestClient(app)

        with patch(self._PATCH_TARGET, return_value=mock_storage):
            resp = client.put(
                f"/storage/upload/{_ASSET_ID}",
                content=b"file bytes",
                headers={"content-type": "image/png"},
            )

        assert resp.status_code == 200
        assert asset.upload_status == UploadStatus.COMPLETE
