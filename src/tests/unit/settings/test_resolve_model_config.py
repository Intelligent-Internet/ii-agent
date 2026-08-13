"""Tests for ModelSettingService.resolve_model_config()."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from ii_agent.settings.llm.service import ModelSettingService


def _make_service(
    *,
    session_repo: MagicMock | None = None,
    repo: MagicMock | None = None,
) -> ModelSettingService:
    return ModelSettingService(
        repo=repo or MagicMock(),
        session_repo=session_repo or MagicMock(),
    )


def _make_session_info(
    *,
    session_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=session_id or uuid.uuid4(),
        user_id=user_id or uuid.uuid4(),
    )


def _make_model_config() -> SimpleNamespace:
    """Minimal stand-in for ModelConfig."""
    return SimpleNamespace(id=uuid.uuid4(), model_id="claude-sonnet-4-6")


# ---------------------------------------------------------------------------
# model_setting_id is None — source="system" with UUID model_id
# (the bug scenario: frontend sends model_settings UUID as model_id)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_uuid_model_id_with_system_source_resolves_by_setting_id():
    """When source='system' and model_id is a UUID string, resolve by setting ID."""
    setting_uuid = uuid.uuid4()
    expected_config = _make_model_config()
    session_info = _make_session_info()

    session_repo = MagicMock()
    session_repo.get_by_id = AsyncMock(return_value=SimpleNamespace(model_setting_id=None))

    svc = _make_service(session_repo=session_repo)
    svc.resolve_config_by_setting_id = AsyncMock(return_value=expected_config)

    db = AsyncMock()
    result = await svc.resolve_model_config(
        db, session=session_info, source="system", model_id=str(setting_uuid)
    )

    assert result is expected_config
    svc.resolve_config_by_setting_id.assert_awaited_once_with(db, setting_id=setting_uuid)


# ---------------------------------------------------------------------------
# model_setting_id is None — source=None with UUID model_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_uuid_model_id_with_no_source_resolves_by_setting_id():
    """When source is None and model_id is a UUID, resolve by setting ID."""
    setting_uuid = uuid.uuid4()
    expected_config = _make_model_config()
    session_info = _make_session_info()

    session_repo = MagicMock()
    session_repo.get_by_id = AsyncMock(return_value=SimpleNamespace(model_setting_id=None))

    svc = _make_service(session_repo=session_repo)
    svc.resolve_config_by_setting_id = AsyncMock(return_value=expected_config)

    db = AsyncMock()
    result = await svc.resolve_model_config(
        db, session=session_info, source=None, model_id=str(setting_uuid)
    )

    assert result is expected_config
    svc.resolve_config_by_setting_id.assert_awaited_once_with(db, setting_id=setting_uuid)


# ---------------------------------------------------------------------------
# model_setting_id is None — non-UUID model_id falls through to system config
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_uuid_model_id_resolves_via_system_config():
    """When model_id is a human-readable name, use resolve_system_config."""
    expected_config = _make_model_config()
    session_info = _make_session_info()

    session_repo = MagicMock()
    session_repo.get_by_id = AsyncMock(return_value=SimpleNamespace(model_setting_id=None))

    svc = _make_service(session_repo=session_repo)
    svc.resolve_system_config = AsyncMock(return_value=expected_config)
    svc.resolve_config_by_setting_id = AsyncMock()

    db = AsyncMock()
    result = await svc.resolve_model_config(
        db, session=session_info, source="system", model_id="claude-sonnet-4-6"
    )

    assert result is expected_config
    svc.resolve_system_config.assert_awaited_once_with(db, model_id="claude-sonnet-4-6")
    svc.resolve_config_by_setting_id.assert_not_awaited()


# ---------------------------------------------------------------------------
# model_setting_id is None — source="user" delegates to get_user_model_config
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_user_source_delegates_to_get_user_model_config():
    """When source='user', look up by user's own setting ID."""
    setting_uuid = uuid.uuid4()
    user_id = uuid.uuid4()
    expected_config = _make_model_config()
    session_info = _make_session_info(user_id=user_id)

    session_repo = MagicMock()
    session_repo.get_by_id = AsyncMock(return_value=SimpleNamespace(model_setting_id=None))

    svc = _make_service(session_repo=session_repo)
    svc.get_user_model_config = AsyncMock(return_value=expected_config)

    db = AsyncMock()
    result = await svc.resolve_model_config(
        db, session=session_info, source="user", model_id=str(setting_uuid)
    )

    assert result is expected_config
    svc.get_user_model_config.assert_awaited_once_with(db, setting_id=setting_uuid, user_id=user_id)


# ---------------------------------------------------------------------------
# model_setting_id is None — no model_id raises ValueError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_model_id_raises_value_error():
    """When session has no model_setting_id and no model_id, raise."""
    session_info = _make_session_info()

    session_repo = MagicMock()
    session_repo.get_by_id = AsyncMock(return_value=SimpleNamespace(model_setting_id=None))

    svc = _make_service(session_repo=session_repo)
    db = AsyncMock()

    with pytest.raises(ValueError, match="model_id is required"):
        await svc.resolve_model_config(db, session=session_info, source="system", model_id=None)


# ---------------------------------------------------------------------------
# model_setting_id is set — uses session's stored setting
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_model_setting_id_used_when_present():
    """When session already has model_setting_id, use it directly."""
    setting_uuid = uuid.uuid4()
    user_id = uuid.uuid4()
    expected_config = _make_model_config()
    session_info = _make_session_info(user_id=user_id)

    session_repo = MagicMock()
    session_repo.get_by_id = AsyncMock(return_value=SimpleNamespace(model_setting_id=setting_uuid))

    svc = _make_service(session_repo=session_repo)
    svc.get_user_model_config = AsyncMock(return_value=expected_config)

    db = AsyncMock()
    result = await svc.resolve_model_config(
        db, session=session_info, source="system", model_id="ignored"
    )

    assert result is expected_config
    svc.get_user_model_config.assert_awaited_once_with(db, setting_id=setting_uuid, user_id=user_id)


# ---------------------------------------------------------------------------
# model_setting_id is set — fallback to resolve_config_by_setting_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_model_setting_id_fallback_on_user_config_error():
    """When get_user_model_config fails, fall back to resolve_config_by_setting_id."""
    setting_uuid = uuid.uuid4()
    expected_config = _make_model_config()
    session_info = _make_session_info()

    session_repo = MagicMock()
    session_repo.get_by_id = AsyncMock(return_value=SimpleNamespace(model_setting_id=setting_uuid))

    svc = _make_service(session_repo=session_repo)
    svc.get_user_model_config = AsyncMock(side_effect=ValueError("not found"))
    svc.resolve_config_by_setting_id = AsyncMock(return_value=expected_config)

    db = AsyncMock()
    result = await svc.resolve_model_config(db, session=session_info)

    assert result is expected_config
    svc.resolve_config_by_setting_id.assert_awaited_once_with(db, setting_id=setting_uuid)
