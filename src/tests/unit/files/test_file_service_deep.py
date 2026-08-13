"""Deep unit tests for ii_agent.files.service covering remaining branches."""

from __future__ import annotations

import io
import uuid as _uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from ii_agent.files.exceptions import (
    FileAccessDeniedError,
    FileUploadNotFoundError,
    FileSizeLimitExceededError,
)
from ii_agent.files.service import FileService

# Stable UUIDs for test fixtures
_FILE_1 = _uuid.UUID("00000000-0000-0000-0000-000000000001")
_FILE_2 = _uuid.UUID("00000000-0000-0000-0000-000000000002")
_USER_1 = _uuid.UUID("00000000-0000-0000-0000-0000000000a1")
_SESSION_1 = _uuid.UUID("00000000-0000-0000-0000-0000000000b1")
_SESSION_2 = _uuid.UUID("00000000-0000-0000-0000-0000000000b2")
_SESSION_NEW = _uuid.UUID("00000000-0000-0000-0000-0000000000b3")
_SESSION_NONE = _uuid.UUID("00000000-0000-0000-0000-0000000000b9")

_FILE_NEW = _uuid.UUID("00000000-0000-0000-0000-000000000003")
_FILE_DONE = _uuid.UUID("00000000-0000-0000-0000-000000000004")
_FILE_NONE = _uuid.UUID("00000000-0000-0000-0000-000000000009")

_IMG_0 = _uuid.UUID("00000000-0000-0000-0000-000000000010")
_IMG_1 = _uuid.UUID("00000000-0000-0000-0000-000000000011")
_IMG_2 = _uuid.UUID("00000000-0000-0000-0000-000000000012")
_IMG_3 = _uuid.UUID("00000000-0000-0000-0000-000000000013")
_IMG_4 = _uuid.UUID("00000000-0000-0000-0000-000000000014")

_USER_WRONG = _uuid.UUID("00000000-0000-0000-0000-0000000000a9")
_USER_EXPLICIT = _uuid.UUID("00000000-0000-0000-0000-0000000000a2")
_USER_RESOLVED = _uuid.UUID("00000000-0000-0000-0000-0000000000a3")


# ---------------------------------------------------------------------------
# Helpers / Fakes
# ---------------------------------------------------------------------------


def _make_file(**kwargs):
    defaults = dict(
        id=_FILE_1,
        file_name="test.txt",
        file_size=100,
        content_type="text/plain",
        storage_path="users/u1/uploads/file-1-test.txt",
        session_id=_SESSION_1,
        user_id=_USER_1,
        signed_url=None,
        signed_url_expires_at=None,
        asset_type="other",
        source="user_upload",
        upload_status="complete",
        is_public=False,
        sandbox_path=None,
        data=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class FakeFileRepo:
    def __init__(self):
        self.files: dict = {}
        self.session_updates = []

    async def get_by_id(self, db, file_id):
        return self.files.get(file_id)

    async def get_by_id_and_user(self, db, file_id, user_id):
        f = self.files.get(file_id)
        if f and f.user_id == user_id:
            return f
        return None

    async def get_by_session_and_id(self, db, session_id, file_id):
        f = self.files.get(file_id)
        if f and f.session_id == session_id:
            return f
        return None

    async def get_by_session_id(self, db, session_id):
        return [f for f in self.files.values() if f.session_id == session_id]

    async def create(self, db, **kwargs):
        # Map file_id -> id for consistency with the model attribute name
        defaults = dict(
            signed_url=None,
            signed_url_expires_at=None,
            asset_type="other",
            source="user_upload",
            upload_status="complete",
            is_public=False,
            sandbox_path=None,
            data=None,
            created_at=None,
            updated_at=None,
        )
        defaults.update(kwargs)
        defaults["id"] = defaults.get("file_id")
        f = SimpleNamespace(**defaults)
        self.files[kwargs["file_id"]] = f
        return f

    async def update_session_id(self, db, file_id, session_id):
        f = self.files.get(file_id)
        if f:
            f.session_id = session_id
        self.session_updates.append((file_id, session_id))
        return bool(f)

    async def get_by_ids(self, db, file_ids):
        return [f for fid in file_ids if (f := self.files.get(fid))]

    async def get_by_storage_path(self, db, storage_path):
        for f in self.files.values():
            if f.storage_path == storage_path:
                return f
        return None

    async def get_by_user_and_paths(self, db, user_id, paths):
        return [f for f in self.files.values() if f.storage_path in paths]

    async def count_user_images(self, db, user_id):
        return sum(1 for f in self.files.values() if f.content_type.startswith("image/"))

    async def get_user_images(self, db, user_id, limit, offset):
        imgs = [f for f in self.files.values() if f.content_type.startswith("image/")]
        return imgs[offset : offset + limit]

    async def link_to_session(self, db, file_id, session_id):
        f = self.files.get(file_id)
        if f and getattr(f, "session_id", None) != session_id:
            self.session_updates.append((file_id, session_id))
        return SimpleNamespace(asset_id=file_id, session_id=session_id)

    async def create_asset(self, db, **kwargs):
        fid = kwargs.get("file_id")
        defaults = dict(
            signed_url=None,
            signed_url_expires_at=None,
            asset_type="other",
            source="user_upload",
            upload_status="complete",
            is_public=False,
            sandbox_path=None,
            data=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        defaults.update(kwargs)
        defaults["id"] = fid
        f = SimpleNamespace(**defaults)
        self.files[fid] = f
        return f

    async def mark_complete(self, db, file_id):
        f = self.files.get(file_id)
        if f:
            f.upload_status = "complete"
        return f

    async def mark_failed(self, db, file_id):
        f = self.files.get(file_id)
        if f:
            f.upload_status = "failed"


class FakeSessionRepo:
    def __init__(self):
        self.sessions: dict = {}

    async def get_by_id(self, db, session_id):
        return self.sessions.get(str(session_id))


def _make_storage_mock() -> MagicMock:
    """Create a mock with async StorageService-compatible interface."""
    storage = MagicMock()
    storage.signed_url = AsyncMock(side_effect=lambda path, **kw: f"signed://{path}")
    storage.signed_urls_batch = AsyncMock(
        side_effect=lambda paths, **kw: [f"signed://{p}" for p in paths]
    )
    storage.signed_upload_url = AsyncMock(side_effect=lambda path, ct, **kw: f"upload://{path}")
    storage.exists = AsyncMock(return_value=False)
    storage.write = AsyncMock(return_value="path")
    storage.write_from_url = AsyncMock(side_effect=lambda url, path, ct=None: path)
    storage.read = AsyncMock(return_value=io.BytesIO(b""))
    storage.public_url = MagicMock(side_effect=lambda path: f"public://{path}")
    return storage


def _make_service(
    *,
    file_repo=None,
    session_repo=None,
    storage=None,
) -> FileService:
    config = SimpleNamespace(
        storage=SimpleNamespace(
            media_bucket_name="media-bucket",
            file_upload_bucket_name="uploads-bucket",
            file_upload_size_limit=1_000_000,
            signed_url_ttl_seconds=3600,
            serve_base_url=None,
        )
    )
    if storage is None:
        storage = _make_storage_mock()
    return FileService(
        file_repo=file_repo or FakeFileRepo(),
        session_repo=session_repo or FakeSessionRepo(),
        storage=storage,
        config=config,
    )


# ---------------------------------------------------------------------------
# get_file_by_id
# ---------------------------------------------------------------------------


class TestGetFileById:
    @pytest.mark.asyncio
    async def test_raises_when_not_found(self):
        svc = _make_service()
        with pytest.raises(FileUploadNotFoundError):
            await svc.get_file_by_id(None, _FILE_NONE)

    @pytest.mark.asyncio
    async def test_returns_file_data_when_found(self):
        repo = FakeFileRepo()
        repo.files[_FILE_1] = _make_file(id=_FILE_1)
        svc = _make_service(file_repo=repo)
        result = await svc.get_file_by_id(None, _FILE_1)
        assert result.id == _FILE_1
        assert result.name == "test.txt"


# ---------------------------------------------------------------------------
# get_files_by_session_id
# ---------------------------------------------------------------------------


class TestGetFilesBySessionId:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_files(self):
        svc = _make_service()
        result = await svc.get_files_by_session_id(None, _SESSION_1)
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_files_for_session(self):
        repo = FakeFileRepo()
        repo.files[_FILE_1] = _make_file(id=_FILE_1, session_id=_SESSION_1)
        repo.files[_FILE_2] = _make_file(id=_FILE_2, session_id=_SESSION_2)
        svc = _make_service(file_repo=repo)
        result = await svc.get_files_by_session_id(None, _SESSION_1)
        assert len(result) == 1
        assert result[0].id == _FILE_1


# ---------------------------------------------------------------------------
# create_file_record
# ---------------------------------------------------------------------------


class TestCreateFileRecord:
    @pytest.mark.asyncio
    async def test_raises_when_session_not_found(self):
        svc = _make_service()
        from ii_agent.sessions.exceptions import SessionNotFoundError

        with pytest.raises(SessionNotFoundError):
            await svc.create_file_record(
                None,
                file_id=_FILE_1,
                file_name="test.txt",
                file_size=100,
                storage_path="path",
                content_type="text/plain",
                session_id=_SESSION_NONE,
            )

    @pytest.mark.asyncio
    async def test_creates_file_record(self):
        session_repo = FakeSessionRepo()
        session = SimpleNamespace(id=_SESSION_1, user_id=_USER_1)
        session_repo.sessions[str(_SESSION_1)] = session
        svc = _make_service(session_repo=session_repo)
        result = await svc.create_file_record(
            None,
            file_id=_FILE_NEW,
            file_name="new.txt",
            file_size=200,
            storage_path="users/u1/uploads/new.txt",
            content_type="text/plain",
            session_id=_SESSION_1,
        )
        assert result.file_id == _FILE_NEW
        assert result.user_id == _USER_1


# ---------------------------------------------------------------------------
# write_file_from_url
# ---------------------------------------------------------------------------


class TestWriteFileFromUrl:
    @pytest.mark.asyncio
    async def test_resolves_user_from_session_when_not_provided(self):
        session_repo = FakeSessionRepo()
        session = SimpleNamespace(id=_SESSION_1, user_id=_USER_RESOLVED)
        session_repo.sessions[str(_SESSION_1)] = session
        svc = _make_service(session_repo=session_repo)
        result = await svc.write_file_from_url(
            None,
            url="https://example.com/file.txt",
            file_name="file.txt",
            file_size=500,
            content_type="text/plain",
            session_id=_SESSION_1,
        )
        assert result.id is not None
        assert "file.txt" in result.name

    @pytest.mark.asyncio
    async def test_raises_when_session_not_found_and_no_user_id(self):
        svc = _make_service()
        from ii_agent.sessions.exceptions import SessionNotFoundError

        with pytest.raises(SessionNotFoundError):
            await svc.write_file_from_url(
                None,
                url="https://example.com/file.txt",
                file_name="file.txt",
                file_size=500,
                content_type="text/plain",
                session_id=_SESSION_NONE,
            )

    @pytest.mark.asyncio
    async def test_uses_provided_user_id(self):
        svc = _make_service()
        result = await svc.write_file_from_url(
            None,
            url="https://example.com/file.txt",
            file_name="file.txt",
            file_size=500,
            content_type="text/plain",
            session_id=_SESSION_1,
            user_id=_USER_EXPLICIT,
        )
        assert result.id is not None


# ---------------------------------------------------------------------------
# generate_upload_url
# ---------------------------------------------------------------------------


class TestGenerateUploadUrl:
    @pytest.mark.asyncio
    async def test_raises_when_size_exceeds_limit(self):
        svc = _make_service()
        with pytest.raises(FileSizeLimitExceededError):
            await svc.generate_upload_url(
                None,
                user_id=_USER_1,
                file_name="big.zip",
                content_type="application/zip",
                file_size=1_000_001,
            )

    @pytest.mark.asyncio
    async def test_returns_upload_url(self):
        svc = _make_service()
        result = await svc.generate_upload_url(
            None,
            user_id=_USER_1,
            file_name="photo.jpg",
            content_type="image/jpeg",
            file_size=500,
        )
        assert result.upload_url.startswith("upload://")
        assert result.id is not None


# ---------------------------------------------------------------------------
# complete_upload
# ---------------------------------------------------------------------------


class TestCompleteUpload:
    @pytest.mark.asyncio
    async def test_raises_when_blob_not_found(self):
        svc = _make_service()
        with pytest.raises(FileUploadNotFoundError):
            await svc.complete_upload(
                None,
                user_id=_USER_1,
                file_id=_FILE_1,
                file_name="test.txt",
                file_size=100,
                content_type="text/plain",
                session_id=None,
            )

    @pytest.mark.asyncio
    async def test_returns_upload_complete_response(self):
        repo = FakeFileRepo()
        repo.files[_FILE_DONE] = _make_file(
            id=_FILE_DONE,
            user_id=_USER_1,
            storage_path="users/u1/uploads/done.txt",
        )
        storage = _make_storage_mock()
        storage.exists = AsyncMock(return_value=True)
        svc = _make_service(file_repo=repo, storage=storage)
        result = await svc.complete_upload(
            None,
            user_id=_USER_1,
            file_id=_FILE_DONE,
            file_name="done.txt",
            file_size=100,
            content_type="text/plain",
            session_id=None,
        )
        assert result.file_url.startswith("signed://")


# ---------------------------------------------------------------------------
# get_file_stream
# ---------------------------------------------------------------------------


class TestGetFileStream:
    @pytest.mark.asyncio
    async def test_raises_when_access_denied(self):
        svc = _make_service()
        with pytest.raises(FileAccessDeniedError):
            await svc.get_file_stream(None, _FILE_1, user_id=_USER_WRONG)

    @pytest.mark.asyncio
    async def test_returns_streaming_response(self):
        from fastapi.responses import StreamingResponse

        repo = FakeFileRepo()
        repo.files[_FILE_1] = _make_file(id=_FILE_1, user_id=_USER_1)
        svc = _make_service(file_repo=repo)
        result = await svc.get_file_stream(None, _FILE_1, user_id=_USER_1)
        assert isinstance(result, StreamingResponse)


# ---------------------------------------------------------------------------
# get_public_file_stream
# ---------------------------------------------------------------------------


class TestGetPublicFileStream:
    @pytest.mark.asyncio
    async def test_raises_when_not_found(self):
        svc = _make_service()
        with pytest.raises(FileUploadNotFoundError):
            await svc.get_public_file_stream(None, _SESSION_1, _FILE_NONE)

    @pytest.mark.asyncio
    async def test_returns_streaming_response(self):
        from fastapi.responses import StreamingResponse

        repo = FakeFileRepo()
        repo.files[_FILE_1] = _make_file(id=_FILE_1, session_id=_SESSION_1)
        svc = _make_service(file_repo=repo)
        result = await svc.get_public_file_stream(None, _SESSION_1, _FILE_1)
        assert isinstance(result, StreamingResponse)


# ---------------------------------------------------------------------------
# upload_avatar
# ---------------------------------------------------------------------------


class TestUploadAvatar:
    @pytest.mark.asyncio
    async def test_uploads_and_returns_url(self):
        svc = _make_service()
        result = await svc.upload_avatar(
            None,
            user_id=_USER_1,
            file_content=b"image bytes",
            file_extension="jpg",
        )
        assert str(_USER_1) in result


# ---------------------------------------------------------------------------
# get_avatar_url
# ---------------------------------------------------------------------------


class TestGetAvatarUrl:
    def test_returns_public_url(self):
        svc = _make_service()
        result = svc.get_avatar_url("users/u1/profile/avatar.jpg")
        assert result == "public://users/u1/profile/avatar.jpg"


# ---------------------------------------------------------------------------
# get_files_by_ids_and_update_session
# ---------------------------------------------------------------------------


class TestGetFilesByIdsAndUpdateSession:
    @pytest.mark.asyncio
    async def test_links_file_to_session(self):
        repo = FakeFileRepo()
        repo.files[_FILE_1] = _make_file(id=_FILE_1, session_id=None)
        svc = _make_service(file_repo=repo)
        results = await svc.get_files_by_ids_and_update_session(
            None,
            file_ids=[_FILE_1],
            user_id=_USER_1,
            session_id=_SESSION_1,
        )
        assert len(results) == 1
        assert (_FILE_1, _SESSION_1) in repo.session_updates

    @pytest.mark.asyncio
    async def test_skips_missing_files(self):
        svc = _make_service()
        results = await svc.get_files_by_ids_and_update_session(
            None,
            file_ids=[_FILE_NONE],
            user_id=_USER_1,
            session_id=_SESSION_1,
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_does_not_update_if_already_linked_to_same_session(self):
        repo = FakeFileRepo()
        repo.files[_FILE_1] = _make_file(id=_FILE_1, session_id=_SESSION_1)
        svc = _make_service(file_repo=repo)
        await svc.get_files_by_ids_and_update_session(
            None,
            file_ids=[_FILE_1],
            user_id=_USER_1,
            session_id=_SESSION_1,
        )
        # No update needed since already linked
        assert (_FILE_1, _SESSION_1) not in repo.session_updates


# ---------------------------------------------------------------------------
# generate_download_urls
# ---------------------------------------------------------------------------


class TestGenerateDownloadUrls:
    @pytest.mark.asyncio
    async def test_returns_signed_urls_and_missing_paths(self):
        repo = FakeFileRepo()
        f = _make_file(id=_FILE_1, storage_path="users/u1/uploads/test.txt")
        repo.files[_FILE_1] = f

        svc = _make_service(file_repo=repo)
        result = await svc.generate_download_urls(
            None,
            user_id=_USER_1,
            storage_paths=["users/u1/uploads/test.txt", "/missing/path.txt"],
        )
        assert len(result.signed_urls) == 2
        assert "missing/path.txt" in result.missing_paths

    @pytest.mark.asyncio
    async def test_normalizes_leading_slashes(self):
        repo = FakeFileRepo()
        f = _make_file(id=_FILE_1, storage_path="users/u1/file.txt")
        repo.files[_FILE_1] = f

        svc = _make_service(file_repo=repo)
        result = await svc.generate_download_urls(
            None,
            user_id=_USER_1,
            storage_paths=["/users/u1/file.txt"],
        )
        # Should normalize the leading slash
        assert len(result.signed_urls) == 1


# ---------------------------------------------------------------------------
# get_media_library
# ---------------------------------------------------------------------------


class TestGetMediaLibrary:
    @pytest.mark.asyncio
    async def test_returns_items_with_signed_urls(self):
        repo = FakeFileRepo()
        from datetime import datetime, timezone

        repo.files[_IMG_1] = _make_file(
            id=_IMG_1,
            content_type="image/png",
            storage_path="sessions/s1/img.png",
        )
        # Add created_at
        repo.files[_IMG_1].created_at = datetime.now(timezone.utc)

        svc = _make_service(file_repo=repo)
        result = await svc.get_media_library(
            None,
            user_id=_USER_1,
            limit=10,
            offset=0,
        )
        assert result.total == 1
        assert len(result.items) == 1
        assert result.items[0].url is not None

    @pytest.mark.asyncio
    async def test_has_more_flag(self):
        repo = FakeFileRepo()
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        _img_ids = [_IMG_0, _IMG_1, _IMG_2, _IMG_3, _IMG_4]
        for i, img_id in enumerate(_img_ids):
            f = _make_file(
                id=img_id, content_type="image/jpeg", storage_path=f"sessions/s1/img{i}.jpg"
            )
            f.created_at = now
            repo.files[img_id] = f

        svc = _make_service(file_repo=repo)
        result = await svc.get_media_library(
            None,
            user_id=_USER_1,
            limit=2,
            offset=0,
        )
        assert result.has_more is True


# ---------------------------------------------------------------------------
# resolve_signed_urls (batch by file IDs)
# ---------------------------------------------------------------------------


class TestResolveSignedUrls:
    @pytest.mark.asyncio
    async def test_returns_empty_dict_for_empty_input(self):
        svc = _make_service()
        result = await svc.resolve_signed_urls(None, [])
        assert result == {}

    @pytest.mark.asyncio
    async def test_resolves_urls_for_known_ids(self):
        repo = FakeFileRepo()
        repo.files["f-1"] = _make_file(id="f-1", storage_path="users/u1/f1.txt")
        repo.files["f-2"] = _make_file(id="f-2", storage_path="users/u1/f2.txt")
        svc = _make_service(file_repo=repo)

        result = await svc.resolve_signed_urls(None, ["f-1", "f-2"])
        assert "f-1" in result
        assert "f-2" in result
        assert result["f-1"] == "signed://users/u1/f1.txt"
        assert result["f-2"] == "signed://users/u1/f2.txt"

    @pytest.mark.asyncio
    async def test_skips_missing_ids(self):
        repo = FakeFileRepo()
        repo.files["f-1"] = _make_file(id="f-1", storage_path="users/u1/f1.txt")
        svc = _make_service(file_repo=repo)

        result = await svc.resolve_signed_urls(None, ["f-1", "no-exist"])
        assert len(result) == 1
        assert "f-1" in result

    @pytest.mark.asyncio
    async def test_returns_http_url_as_is(self):
        repo = FakeFileRepo()
        repo.files["f-1"] = _make_file(id="f-1", storage_path="https://example.com/image.png")
        storage = _make_storage_mock()
        svc = _make_service(file_repo=repo, storage=storage)

        result = await svc.resolve_signed_urls(None, ["f-1"])
        assert result["f-1"] == "https://example.com/image.png"
        # Should NOT call storage.signed_url for http URLs
        storage.signed_url.assert_not_called()

    @pytest.mark.asyncio
    async def test_uses_cached_signed_url_when_valid(self):
        from datetime import datetime, timedelta, timezone

        repo = FakeFileRepo()
        f = _make_file(id="f-1", storage_path="users/u1/f1.txt")
        # Set a valid cached signed URL (expires 3 hours from now > 2h buffer)
        f.signed_url = "cached://valid"
        f.signed_url_expires_at = datetime.now(timezone.utc) + timedelta(hours=3)
        repo.files["f-1"] = f

        storage = _make_storage_mock()
        svc = _make_service(file_repo=repo, storage=storage)

        result = await svc.resolve_signed_urls(None, ["f-1"])
        assert result["f-1"] == "cached://valid"
        storage.signed_url.assert_not_called()

    @pytest.mark.asyncio
    async def test_regenerates_when_cached_url_expired(self):
        from datetime import datetime, timedelta, timezone

        repo = FakeFileRepo()
        f = _make_file(id="f-1", storage_path="users/u1/f1.txt")
        # Set an expired cached URL (expires 1 hour from now < 2h buffer)
        f.signed_url = "cached://stale"
        f.signed_url_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        repo.files["f-1"] = f

        storage = _make_storage_mock()
        svc = _make_service(file_repo=repo, storage=storage)

        result = await svc.resolve_signed_urls(None, ["f-1"])
        assert result["f-1"] == "signed://users/u1/f1.txt"
        storage.signed_url.assert_called_once()


# ---------------------------------------------------------------------------
# resolve_signed_url_by_path
# ---------------------------------------------------------------------------


class TestResolveSignedUrlByPath:
    @pytest.mark.asyncio
    async def test_returns_none_for_empty_path(self):
        svc = _make_service()
        result = await svc.resolve_signed_url_by_path(None, "")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_http_url_as_is(self):
        svc = _make_service()
        result = await svc.resolve_signed_url_by_path(None, "https://example.com/file.png")
        assert result == "https://example.com/file.png"

    @pytest.mark.asyncio
    async def test_resolves_via_asset_row_when_found(self):
        repo = FakeFileRepo()
        repo.files["f-1"] = _make_file(id="f-1", storage_path="users/u1/uploads/test.txt")
        svc = _make_service(file_repo=repo)

        result = await svc.resolve_signed_url_by_path(None, "users/u1/uploads/test.txt")
        assert result == "signed://users/u1/uploads/test.txt"

    @pytest.mark.asyncio
    async def test_falls_back_to_direct_storage_when_no_asset(self):
        storage = _make_storage_mock()
        svc = _make_service(storage=storage)

        result = await svc.resolve_signed_url_by_path(None, "orphaned/path/file.txt")
        assert result == "signed://orphaned/path/file.txt"
        storage.signed_url.assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_cached_url_from_asset(self):
        from datetime import datetime, timedelta, timezone

        repo = FakeFileRepo()
        f = _make_file(id="f-1", storage_path="users/u1/uploads/cached.txt")
        f.signed_url = "cached://still-good"
        f.signed_url_expires_at = datetime.now(timezone.utc) + timedelta(hours=3)
        repo.files["f-1"] = f

        storage = _make_storage_mock()
        svc = _make_service(file_repo=repo, storage=storage)

        result = await svc.resolve_signed_url_by_path(None, "users/u1/uploads/cached.txt")
        assert result == "cached://still-good"
        storage.signed_url.assert_not_called()
