from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4, UUID

import pytest

from ii_agent.settings.llm import Provider
from ii_agent.files.exceptions import FileSizeLimitExceededError
from ii_agent.files.service import FileService
from ii_agent.sessions.service import SessionService
from ii_agent.sessions.types import AppKind
from ii_agent.settings.llm.schemas import ModelSettingCreate
from ii_agent.settings.llm.service import ModelSettingService

pytestmark = pytest.mark.smoke


USER_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


class SessionRepo:
    def __init__(self):
        self.sessions = {}

    async def save(self, db, session):
        from datetime import datetime, timezone

        if session.created_at is None:
            session.created_at = datetime.now(timezone.utc)
        if session.updated_at is None:
            session.updated_at = datetime.now(timezone.utc)
        if session.is_public is None:
            session.is_public = False
        if session.app_kind is None:
            session.app_kind = AppKind.AGENT
        self.sessions[session.id] = session
        return session

    async def get_by_id(self, db, session_id):
        return self.sessions.get(session_id)


class FileRepo:
    async def create_asset(self, db, **kwargs):
        return SimpleNamespace(**kwargs)


class LLMRepo:
    def __init__(self):
        self.by_model = {}

    async def find_by_model_and_user(self, db, model, user_id):
        return self.by_model.get((model, user_id))

    async def create(self, db, setting):
        if setting.id is None:
            setting.id = uuid4()
        self.by_model[(setting.model_id, str(setting.user_id))] = setting
        return setting

    async def update(self, db, setting):
        self.by_model[(setting.model_id, str(setting.user_id))] = setting
        return setting


@pytest.mark.asyncio
async def test_session_and_file_sanity(settings_factory):
    session_service = SessionService(
        session_repo=SessionRepo(),
        event_repo=SimpleNamespace(),
        run_task_service=SimpleNamespace(),
        file_store=SimpleNamespace(get_download_signed_url=lambda path: f"signed:{path}"),
        file_service=SimpleNamespace(),
        sandbox_repo=SimpleNamespace(),
        cache=SimpleNamespace(),
        config=settings_factory(),
    )

    session = await session_service.create_new_session(
        db=None,
        session_uuid=uuid4(),
        user_id=USER_ID,
        api_version="v1",
    )

    storage_mock = MagicMock()
    storage_mock.signed_upload_url = AsyncMock(
        side_effect=lambda path, ct, **kw: f"upload://{path}"
    )

    file_service = FileService(
        file_repo=FileRepo(),
        session_repo=SimpleNamespace(),
        storage=storage_mock,
        config=settings_factory(storage={"file_upload_size_limit": 10}),
    )

    upload = await file_service.generate_upload_url(
        db=None,
        user_id=str(USER_ID),
        file_name="a.txt",
        content_type="text/plain",
        file_size=3,
    )

    assert upload.id

    with pytest.raises(FileSizeLimitExceededError):
        await file_service.generate_upload_url(
            db=None,
            user_id=str(USER_ID),
            file_name="big.txt",
            content_type="text/plain",
            file_size=100,
        )

    assert str(session.id)


@pytest.mark.asyncio
async def test_llm_setting_create_and_read_sanity(settings_factory, monkeypatch):
    monkeypatch.setattr(
        "ii_agent.settings.llm.service.encryption_manager.encrypt", lambda value: f"enc:{value}"
    )

    service = ModelSettingService(
        repo=LLMRepo(),
        session_repo=SimpleNamespace(get_by_id=lambda *args, **kwargs: None),
    )

    created = await service.create_model_settings(
        db=None,
        user_id=USER_ID,
        model_setting_request=ModelSettingCreate(
            model_id="gpt-4o",
            provider=Provider.OPENAI,
            api_key="secret",
        ),
    )

    assert created.model_id == "gpt-4o"
    assert created.has_api_key is True
