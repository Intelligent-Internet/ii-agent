from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ii_agent.auth.dependencies import get_current_user
from ii_agent.users.dependencies import _get_user_service
from ii_agent.credits.dependencies import _get_credit_service
from ii_agent.content.storybook.dependencies import (
    _get_storybook_ai_edit_service,
    _get_storybook_edit_service,
    _get_storybook_export_service,
    _get_storybook_service,
    _get_storybook_voice_service,
)
from ii_agent.content.storybook.router import router
from ii_agent.core.dependencies import _db_session_dependency
from ii_agent.core.middleware import ii_agent_error_handler
from ii_agent.core.exceptions import IIAgentError, ValidationError
from ii_agent.core.storage.dependencies import _get_storage_service
from ii_agent.sessions.dependencies import _get_session_service
from ii_agent.settings.llm.dependencies import _get_model_setting_service


pytestmark = pytest.mark.unit

# Fixed UUIDs used throughout this test file
SB1_ID = "00000000-0000-0000-0000-000000000001"
SB2_ID = "00000000-0000-0000-0000-000000000002"
UNKNOWN_ID = "00000000-0000-0000-0000-000000000099"
SESSION1_ID = "10000000-0000-0000-0000-000000000001"
SB1_UUID = UUID(SB1_ID)
SB2_UUID = UUID(SB2_ID)


def _make_app(*, session_access: bool = True, export_bytes: bytes | None = b"pdf"):
    app = FastAPI()
    app.include_router(router)
    app.exception_handler(IIAgentError)(ii_agent_error_handler)

    storybook = SimpleNamespace(
        id=SB1_ID,
        session_id="session-1",
        name="My Story",
    )
    storybook_detail = SimpleNamespace(
        **storybook.__dict__,
        pages=[],
    )

    class _StorybookService:
        async def get_storybook_detail(self, db, storybook_id, include_pages: bool):
            return storybook_detail if storybook_id == SB1_UUID else None

        async def get_session_storybooks(self, db, session_id, include_pages: bool):
            return {"session_id": session_id, "storybooks": [], "total": 0}

        def build_generation_response(self, _storybook):
            return {"type": "storybook_progress", "storybook_id": SB1_ID}

    class _SessionService:
        async def get_session_details(self, db, session_id, user_id):
            return {"id": str(session_id)} if session_access else None

        async def get_public_session_details(self, db, session_id):
            return {"id": str(session_id)}

    class _EditService:
        async def save_all_page_edits(self, db, storybook_id, page_changes, image_urls):
            return storybook_detail, 0.0

        async def get_version_history(self, db, storybook_id):
            return []

    class _AIEditService:
        async def rewrite_content(
            self, db, *, storybook, user_id: str, content: str, page_image_url=None
        ):
            if not content.strip():
                raise ValidationError("No content provided to rewrite")
            return "rewritten text"

        async def generate_background(
            self,
            db,
            *,
            storybook,
            user_id: str,
            prompt: str,
            page_image_url=None,
            text_position=None,
        ):
            if not prompt.strip():
                raise ValidationError("No prompt provided for image generation")
            return "https://storage.local/generated-background.png"

        async def regenerate_image(
            self,
            db,
            *,
            storybook,
            user_id: str,
            page_number: int,
            prompt: str,
            reference_image_url=None,
            scene_text=None,
            text_position=None,
            text_percentage=None,
        ):
            if not prompt.strip():
                raise ValidationError("No prompt provided for image regeneration")
            return "https://storage.local/generated-page.png"

    class _ExportService:
        async def download_storybook_as_pdf(self, db, storybook_id: str):
            return export_bytes

        async def download_storybook_page_as_pdf(self, db, storybook_id: str, page_number: int):
            return export_bytes if page_number == 1 else None

    class _CreditService:
        async def deduct_and_track_session_usage(self, *args, **kwargs):
            return True

    class _VoiceService:
        def get_generation_status(self, storybook):
            return "completed"

        async def cancel_generation(self, db, storybook_id):
            return None

    class _Storage:
        def upload_and_get_permanent_url(
            self, file_obj, path: str, content_type: str | None = None
        ):
            return f"https://storage.local/{path}"

    async def _fake_db():
        yield SimpleNamespace(rollback=AsyncMock())

    async def _fake_user():
        return SimpleNamespace(id="user-1")

    app.dependency_overrides[_db_session_dependency] = _fake_db
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[_get_storybook_service] = lambda: _StorybookService()
    app.dependency_overrides[_get_storybook_edit_service] = lambda: _EditService()
    app.dependency_overrides[_get_storybook_ai_edit_service] = lambda: _AIEditService()
    app.dependency_overrides[_get_storybook_export_service] = lambda: _ExportService()
    app.dependency_overrides[_get_storybook_voice_service] = lambda: _VoiceService()
    app.dependency_overrides[_get_credit_service] = lambda: _CreditService()
    app.dependency_overrides[_get_session_service] = lambda: _SessionService()
    app.dependency_overrides[_get_user_service] = lambda: SimpleNamespace()
    app.dependency_overrides[_get_model_setting_service] = lambda: SimpleNamespace()
    app.dependency_overrides[_get_storage_service] = lambda: _Storage()
    return app


def test_storybook_edit_save_requires_auth_header():
    app = _make_app()
    app.dependency_overrides.pop(get_current_user, None)

    with TestClient(app) as client:
        resp = client.post(
            f"/storybooks/{SB1_ID}/edit/save",
            json={"storybook_id": SB1_ID, "page_changes": []},
        )

    assert resp.status_code == 403


def test_storybook_edit_save_path_validation_error_response():
    app = _make_app()
    with TestClient(app) as client:
        resp = client.post(
            f"/storybooks/{SB1_ID}/edit/save",
            headers={"Authorization": "Bearer token"},
            json={
                "storybook_id": SB2_ID,
                "page_changes": [{"page_number": 1, "changes": []}],
            },
        )

    assert resp.status_code == 200
    assert resp.json() == {
        "success": False,
        "storybook": None,
        "error": "Path storybook_id does not match request.storybook_id",
    }


def test_storybook_ai_rewrite_path_validation_error_response():
    app = _make_app()
    with TestClient(app) as client:
        resp = client.post(
            f"/storybooks/{SB1_ID}/edit/ai-rewrite",
            headers={"Authorization": "Bearer token"},
            json={
                "storybook_id": SB2_ID,
                "content": "Rewrite me",
            },
        )

    assert resp.status_code == 200
    assert resp.json() == {
        "success": False,
        "rewritten_content": None,
        "error": "Path storybook_id does not match request.storybook_id",
    }


def test_storybook_ai_regenerate_requires_prompt():
    app = _make_app()
    with TestClient(app) as client:
        resp = client.post(
            f"/storybooks/{SB1_ID}/edit/ai-regenerate-image",
            headers={"Authorization": "Bearer token"},
            json={
                "storybook_id": SB1_ID,
                "page_number": 1,
                "prompt": "   ",
            },
        )

    assert resp.status_code == 200
    assert resp.json() == {
        "success": False,
        "image_url": None,
        "error": "No prompt provided for image regeneration",
    }


def test_storybook_upload_background_rejects_non_image():
    app = _make_app()
    with TestClient(app) as client:
        resp = client.post(
            f"/storybooks/{SB1_ID}/edit/upload-background",
            headers={"Authorization": "Bearer token"},
            files={"file": ("notes.txt", BytesIO(b"text"), "text/plain")},
        )

    assert resp.status_code == 400
    payload = resp.json()
    assert payload["error_code"] == "validation"
    assert "Only image uploads are supported" in payload["detail"]


def test_storybook_download_export_failure_and_access_denied():
    app_export_fail = _make_app(export_bytes=None)
    with TestClient(app_export_fail) as client:
        resp = client.get(
            f"/storybooks/{SB1_ID}/download",
            headers={"Authorization": "Bearer token"},
        )
    assert resp.status_code == 500
    assert resp.json()["error_code"] == "storybook_export"

    app_access_denied = _make_app(session_access=False)
    with TestClient(app_access_denied) as client:
        resp = client.get(
            f"/storybooks/{SB1_ID}/download",
            headers={"Authorization": "Bearer token"},
        )
    assert resp.status_code == 403
    assert resp.json()["error_code"] == "storybook_access_denied"


def test_storybook_not_found_and_page_not_found_errors():
    app = _make_app()
    with TestClient(app) as client:
        not_found = client.get(
            f"/storybooks/{UNKNOWN_ID}",
            headers={"Authorization": "Bearer token"},
        )
        assert not_found.status_code == 404
        assert not_found.json()["error_code"] == "storybook_not_found"

        page_missing = client.get(
            f"/storybooks/{SB1_ID}/download/page/2",
            headers={"Authorization": "Bearer token"},
        )
        assert page_missing.status_code == 404
        assert page_missing.json()["error_code"] == "storybook_page_not_found"


def test_storybook_session_list_and_cancel_endpoint():
    app = _make_app()
    with TestClient(app) as client:
        listing = client.get(
            f"/storybooks/session/{SESSION1_ID}?include_pages=true",
            headers={"Authorization": "Bearer token"},
        )
        assert listing.status_code == 200
        assert listing.json()["session_id"] == SESSION1_ID

        cancelled = client.post(
            f"/storybooks/{SB1_ID}/cancel",
            headers={"Authorization": "Bearer token"},
        )
        assert cancelled.status_code == 200
        assert cancelled.json()["success"] is False
