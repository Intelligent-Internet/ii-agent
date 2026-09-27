from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from ii_agent.files.service import FileService

pytestmark = pytest.mark.integration

USER_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
SESSION_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


class FakeFileRepo:
    def __init__(self):
        self._assets: dict[str, SimpleNamespace] = {}

    async def create_asset(self, db, **kwargs):
        asset = SimpleNamespace(id=kwargs["file_id"], **kwargs)
        self._assets[kwargs["storage_path"]] = asset
        return asset

    async def get_by_id_and_user(self, db, file_id, user_id):
        for asset in self._assets.values():
            if asset.file_id == file_id:
                return asset
        return None

    async def mark_complete(self, db, file_id):
        pass

    async def mark_failed(self, db, file_id):
        pass

    async def link_to_session(self, db, file_id, session_id):
        pass

    async def get_by_user_and_paths(self, db, user_id, normalized_paths):
        return [self._assets[p] for p in normalized_paths if p in self._assets]


class FakeSessionRepo:
    async def get_by_id(self, db, session_id):
        return SimpleNamespace(user_id=USER_ID)


@pytest.mark.asyncio
async def test_file_upload_lifecycle_integration(settings_factory):
    repo = FakeFileRepo()

    storage_mock = MagicMock()
    storage_mock.signed_upload_url = AsyncMock(
        side_effect=lambda path, ct, **kw: f"https://upload.local/{path}"
    )
    storage_mock.exists = AsyncMock(return_value=True)
    storage_mock.signed_url = AsyncMock(
        side_effect=lambda path, **kw: f"https://signed.local/{path}"
    )
    storage_mock.signed_urls_batch = AsyncMock(
        side_effect=lambda paths, **kw: [f"https://signed.local/{p}" for p in paths]
    )
    storage_mock.public_url = MagicMock(side_effect=lambda p: f"https://public.local/{p}")

    service = FileService(
        file_repo=repo,
        session_repo=FakeSessionRepo(),
        storage=storage_mock,
        config=settings_factory(storage={"file_upload_size_limit": 10}),
    )

    upload = await service.generate_upload_url(
        db=None,
        user_id=USER_ID,
        file_name="a.txt",
        content_type="text/plain",
        file_size=3,
    )

    # Service stores the file at users/{user_id}/docs/{file_id}.txt
    # (text/plain → AssetType.DOCUMENT → "docs" folder, ext="txt")
    file_id = upload.id  # already a UUID (Pydantic coerces the str)
    blob = f"users/{USER_ID}/docs/{file_id}.txt"

    completed = await service.complete_upload(
        db=None,
        user_id=USER_ID,
        file_id=file_id,
        file_name="a.txt",
        file_size=3,
        content_type="text/plain",
        session_id=SESSION_ID,
    )

    missing_path = f"users/{USER_ID}/docs/missing.txt"
    downloads = await service.generate_download_urls(
        db=None,
        user_id=USER_ID,
        storage_paths=[blob, missing_path],
    )

    assert completed.file_url.endswith(blob)
    assert downloads.signed_urls[0] is not None
    assert downloads.signed_urls[0].endswith(blob)
    assert downloads.missing_paths == [missing_path]
