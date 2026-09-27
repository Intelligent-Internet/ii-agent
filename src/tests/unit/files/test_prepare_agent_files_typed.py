"""Tests for FileService.prepare_agent_files() returning typed media objects."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from ii_agent.files.media import File, Image
from ii_agent.files.schemas import FileDataResponse
from ii_agent.files.service import FileService


def _make_file_service() -> FileService:
    return FileService(
        file_repo=MagicMock(),
        session_repo=MagicMock(),
        storage=AsyncMock(),
        config=MagicMock(),
    )


def _file_response(
    *,
    file_id: uuid.UUID | None = None,
    name: str = "test.txt",
    url: str = "https://example.com/test.txt",
    content_type: str = "text/plain",
) -> FileDataResponse:
    return FileDataResponse(
        id=file_id or uuid.uuid4(),
        name=name,
        url=url,
        content_type=content_type,
        size=100,
        storage_path="path/to/file",
        upload_status="complete",
        is_public=False,
        created_at=None,
        asset_type="document",
        source="user_upload",
    )


@pytest.mark.asyncio
async def test_prepare_agent_files_returns_typed_image_and_file() -> None:
    svc = _make_file_service()
    img_id = uuid.uuid4()
    file_id = uuid.uuid4()

    svc.get_files_by_ids_and_update_session = AsyncMock(
        return_value=[
            _file_response(
                file_id=img_id,
                name="photo.png",
                url="https://cdn/photo.png",
                content_type="image/png",
            ),
            _file_response(
                file_id=file_id,
                name="doc.pdf",
                url="https://cdn/doc.pdf",
                content_type="application/pdf",
            ),
        ]
    )

    db = AsyncMock()
    images, files = await svc.prepare_agent_files(
        db,
        file_ids=[img_id, file_id],
        user_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
    )

    assert len(files) == 1
    assert all(isinstance(f, File) for f in files)
    assert files[0].url == "https://cdn/doc.pdf"
    assert files[0].filename == "doc.pdf"

    assert len(images) == 1
    assert all(isinstance(i, Image) for i in images)
    assert images[0].url == "https://cdn/photo.png"
    assert images[0].mime_type == "image/png"


@pytest.mark.asyncio
async def test_prepare_agent_files_skips_files_without_url() -> None:
    svc = _make_file_service()
    svc.get_files_by_ids_and_update_session = AsyncMock(
        return_value=[
            _file_response(name="no-url.txt", url=None),
        ]
    )

    db = AsyncMock()
    images, files = await svc.prepare_agent_files(
        db,
        file_ids=[uuid.uuid4()],
        user_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
    )

    assert images == []
    assert files == []


@pytest.mark.asyncio
async def test_prepare_agent_files_empty_file_ids() -> None:
    svc = _make_file_service()
    svc.get_files_by_ids_and_update_session = AsyncMock(return_value=[])

    db = AsyncMock()
    images, files = await svc.prepare_agent_files(
        db,
        file_ids=[],
        user_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
    )

    assert images == []
    assert files == []
