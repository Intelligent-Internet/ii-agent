"""Unit tests for ``StorageService`` — the high-level facade combining
``StorageProvider`` with ``PathResolver``.

These tests verify the service is a faithful pass-through and that path
construction is delegated to the resolver. Provider I/O is mocked.
"""

from __future__ import annotations

import io
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from ii_agent.core.storage.path_resolver import PathResolver
from ii_agent.core.storage.service import StorageService


pytestmark = pytest.mark.unit


def _make_service() -> tuple[StorageService, MagicMock, PathResolver]:
    provider = MagicMock(name="StorageProvider")
    # All methods we care about are async
    for name in (
        "read",
        "write",
        "write_from_url",
        "exists",
        "size",
        "delete",
        "copy",
        "signed_download_url",
        "signed_download_urls_batch",
        "signed_upload_url",
    ):
        setattr(provider, name, AsyncMock())
    provider.public_url = MagicMock(return_value="https://public/u")
    paths = PathResolver()
    return StorageService(provider, paths), provider, paths


# ---------------------------------------------------------------------------
# Direct passthroughs
# ---------------------------------------------------------------------------


class TestPassThrough:
    def test_provider_property_returns_underlying(self):
        svc, provider, _ = _make_service()
        assert svc.provider is provider

    def test_paths_property_returns_resolver(self):
        svc, _, paths = _make_service()
        assert svc.paths is paths

    @pytest.mark.asyncio
    async def test_read_delegates(self):
        svc, provider, _ = _make_service()
        provider.read.return_value = io.BytesIO(b"x")
        await svc.read("p")
        provider.read.assert_awaited_once_with("p")

    @pytest.mark.asyncio
    async def test_write_delegates(self):
        svc, provider, _ = _make_service()
        provider.write.return_value = "p"
        buf = io.BytesIO(b"x")
        result = await svc.write("p", buf, "text/plain")
        assert result == "p"
        provider.write.assert_awaited_once_with("p", buf, "text/plain")

    @pytest.mark.asyncio
    async def test_write_from_url_delegates(self):
        svc, provider, _ = _make_service()
        provider.write_from_url.return_value = "dest"
        result = await svc.write_from_url("https://x", "dest", "image/png")
        assert result == "dest"
        provider.write_from_url.assert_awaited_once_with("https://x", "dest", "image/png")

    @pytest.mark.asyncio
    async def test_exists_size_delete(self):
        svc, provider, _ = _make_service()
        provider.exists.return_value = True
        provider.size.return_value = 42

        assert await svc.exists("p") is True
        assert await svc.size("p") == 42
        await svc.delete("p")
        provider.delete.assert_awaited_once_with("p")

    @pytest.mark.asyncio
    async def test_copy_delegates(self):
        svc, provider, _ = _make_service()
        provider.copy.return_value = "b"
        assert await svc.copy("a", "b") == "b"
        provider.copy.assert_awaited_once_with("a", "b")

    @pytest.mark.asyncio
    async def test_signed_url_uses_default_expiry(self):
        svc, provider, _ = _make_service()
        provider.signed_download_url.return_value = "https://signed"
        assert await svc.signed_url("p") == "https://signed"
        provider.signed_download_url.assert_awaited_once_with("p", 3600)

    @pytest.mark.asyncio
    async def test_signed_url_passes_expiry(self):
        svc, provider, _ = _make_service()
        provider.signed_download_url.return_value = "https://signed"
        await svc.signed_url("p", expiry_seconds=120)
        provider.signed_download_url.assert_awaited_once_with("p", 120)

    @pytest.mark.asyncio
    async def test_signed_urls_batch_passthrough(self):
        svc, provider, _ = _make_service()
        provider.signed_download_urls_batch.return_value = ["a", None, "c"]
        result = await svc.signed_urls_batch(["1", "2", "3"], expiry_seconds=60)
        assert result == ["a", None, "c"]
        provider.signed_download_urls_batch.assert_awaited_once_with(["1", "2", "3"], 60)

    @pytest.mark.asyncio
    async def test_signed_upload_url_passthrough(self):
        svc, provider, _ = _make_service()
        provider.signed_upload_url.return_value = "https://put"
        await svc.signed_upload_url("p", "image/png", 60)
        provider.signed_upload_url.assert_awaited_once_with("p", "image/png", 60)

    def test_public_url_passthrough(self):
        svc, provider, _ = _make_service()
        assert svc.public_url("any") == "https://public/u"
        provider.public_url.assert_called_once_with("any")


# ---------------------------------------------------------------------------
# Path-aware uploads
# ---------------------------------------------------------------------------


class TestUserFiles:
    @pytest.mark.asyncio
    async def test_upload_user_file_uses_path_resolver(self):
        svc, provider, _ = _make_service()
        provider.write.return_value = "users/u1/media/f1.png"
        user_id = uuid.UUID("11111111-1111-1111-1111-111111111111")

        path = await svc.upload_user_file(
            user_id, "image", "f1", "png", io.BytesIO(b"x"), "image/png"
        )

        assert path == "users/u1/media/f1.png"
        provider.write.assert_awaited_once()
        called_path = provider.write.call_args.args[0]
        assert called_path == f"users/{user_id}/media/f1.png"

    @pytest.mark.asyncio
    async def test_upload_user_file_from_url_uses_path_resolver(self):
        svc, provider, _ = _make_service()
        provider.write_from_url.return_value = "users/u/docs/abc.txt"
        user_id = uuid.UUID("11111111-1111-1111-1111-111111111111")

        await svc.upload_user_file_from_url(
            user_id, "document", "abc", "txt", "https://src/", "text/plain"
        )

        provider.write_from_url.assert_awaited_once()
        args = provider.write_from_url.call_args.args
        assert args[0] == "https://src/"
        assert args[1] == f"users/{user_id}/docs/abc.txt"


class TestAvatars:
    @pytest.mark.asyncio
    async def test_upload_avatar(self):
        svc, provider, _ = _make_service()
        user_id = uuid.UUID("22222222-2222-2222-2222-222222222222")
        provider.write.return_value = "p"

        await svc.upload_avatar(user_id, "av1", "png", io.BytesIO(b"x"), "image/png")

        called_path = provider.write.call_args.args[0]
        assert called_path == f"users/{user_id}/avatars/av1.png"

    def test_avatar_path_no_io(self):
        svc, provider, _ = _make_service()
        user_id = uuid.UUID("22222222-2222-2222-2222-222222222222")
        assert svc.avatar_path(user_id, "av1", "png") == f"users/{user_id}/avatars/av1.png"
        provider.write.assert_not_called()


class TestSkills:
    @pytest.mark.asyncio
    async def test_upload_skill(self):
        svc, provider, _ = _make_service()
        user_id = uuid.UUID("33333333-3333-3333-3333-333333333333")
        provider.write.return_value = "p"

        await svc.upload_skill(user_id, "my-skill", b"PK\x03\x04zip")

        called_args = provider.write.call_args.args
        assert called_args[0] == f"users/{user_id}/skills/my-skill.zip"
        assert called_args[1].read() == b"PK\x03\x04zip"
        assert called_args[2] == "application/zip"

    @pytest.mark.asyncio
    async def test_download_skill_returns_bytes(self):
        svc, provider, _ = _make_service()
        user_id = uuid.UUID("44444444-4444-4444-4444-444444444444")
        provider.read.return_value = io.BytesIO(b"zipdata")

        data = await svc.download_skill(user_id, "s1")

        assert data == b"zipdata"
        provider.read.assert_awaited_once_with(f"users/{user_id}/skills/s1.zip")

    @pytest.mark.asyncio
    async def test_skill_exists_delegates(self):
        svc, provider, _ = _make_service()
        provider.exists.return_value = False
        user_id = uuid.UUID("55555555-5555-5555-5555-555555555555")
        assert await svc.skill_exists(user_id, "s1") is False

    @pytest.mark.asyncio
    async def test_delete_skill_uses_resolver_path(self):
        svc, provider, _ = _make_service()
        user_id = uuid.UUID("66666666-6666-6666-6666-666666666666")
        await svc.delete_skill(user_id, "s1")
        provider.delete.assert_awaited_once_with(f"users/{user_id}/skills/s1.zip")

    def test_skill_path_no_io(self):
        svc, _, _ = _make_service()
        user_id = uuid.UUID("77777777-7777-7777-7777-777777777777")
        assert svc.skill_path(user_id, "s1") == f"users/{user_id}/skills/s1.zip"


class TestContentSlidesSystemTemp:
    @pytest.mark.asyncio
    async def test_upload_content_template(self):
        svc, provider, _ = _make_service()
        await svc.upload_content_template("cards", "x", "json", io.BytesIO(b"{}"), "application/json")
        assert provider.write.call_args.args[0] == "content/templates/cards/x.json"

    @pytest.mark.asyncio
    async def test_upload_slide_asset(self):
        svc, provider, _ = _make_service()
        await svc.upload_slide_asset("hash123", "png", io.BytesIO(b"x"), "image/png")
        assert provider.write.call_args.args[0] == "content/slides/hash123.png"

    @pytest.mark.asyncio
    async def test_upload_system_asset(self):
        svc, provider, _ = _make_service()
        await svc.upload_system_asset("logos", "main", "svg", io.BytesIO(b"<svg/>"), "image/svg+xml")
        assert provider.write.call_args.args[0] == "system/logos/main.svg"

    @pytest.mark.asyncio
    async def test_upload_temp(self):
        svc, provider, _ = _make_service()
        await svc.upload_temp("tok123", "doc", "pdf", io.BytesIO(b"%PDF"), "application/pdf")
        assert provider.write.call_args.args[0] == "tmp/tok123/doc.pdf"
