from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ii_agent.auth.dependencies import get_current_user
from ii_agent.core.dependencies import _db_session_dependency
from ii_agent.core.exceptions import IIAgentError
from ii_agent.core.middleware import ii_agent_error_handler
from ii_agent.integrations.connectors.router import (
    _create_state_token,
    router,
)


pytestmark = pytest.mark.unit

connectors_router_module = importlib.import_module("ii_agent.integrations.connectors.router")


def _make_app():
    app = FastAPI()
    app.include_router(router)
    app.exception_handler(IIAgentError)(ii_agent_error_handler)

    async def _fake_db():
        yield SimpleNamespace()

    async def _fake_user():
        return SimpleNamespace(id="user-1")

    app.dependency_overrides[_db_session_dependency] = _fake_db
    app.dependency_overrides[get_current_user] = _fake_user
    return app


def test_connectors_github_auth_url_requires_auth():
    app = _make_app()
    app.dependency_overrides.pop(get_current_user, None)

    with TestClient(app) as client:
        resp = client.get("/connectors/github/auth-url")

    assert resp.status_code == 403


def test_connectors_github_callback_invalid_state_returns_400():
    app = _make_app()
    with TestClient(app) as client:
        resp = client.post(
            "/connectors/github/callback",
            headers={"Authorization": "Bearer token"},
            json={"code": "abc", "state": "bad-state"},
        )

    assert resp.status_code == 400
    assert resp.json()["error_code"] == "connector_state"


def test_connectors_github_callback_uses_state_redirect_uri(monkeypatch):
    app = _make_app()

    class _FakeGitHubConnector:
        def __init__(self):
            self.received_redirect_uri = None
            self.connected = False

        async def handle_callback(self, code: str, state: str, redirect_uri: str | None = None):
            self.received_redirect_uri = redirect_uri
            return {"access_token": "tok"}

        async def connect(self, user_id: str, connector_data):
            self.connected = True

    connector = _FakeGitHubConnector()
    monkeypatch.setattr(connectors_router_module, "GitHubConnector", _FakeGitHubConnector)
    monkeypatch.setattr(
        connectors_router_module.ConnectorFactory,
        "create",
        lambda connector_type, db: connector,
    )
    state = _create_state_token(
        "user-1",
        "github",
        redirect_uri="https://frontend.example.com/oauth/callback",
    )

    with TestClient(app) as client:
        resp = client.post(
            "/connectors/github/callback",
            headers={"Authorization": "Bearer token"},
            json={"code": "abc", "state": state},
        )

    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert connector.connected is True
    assert connector.received_redirect_uri == "https://frontend.example.com/oauth/callback"


def test_connectors_github_repositories_mapping(monkeypatch):
    app = _make_app()

    class _FakeGitHubConnector:
        async def get_repositories(self, user_id: str):
            return [
                {
                    "id": 1,
                    "name": "repo",
                    "full_name": "org/repo",
                    "owner": {"login": "org"},
                    "private": False,
                    "description": "desc",
                    "html_url": "https://github.com/org/repo",
                    "default_branch": "main",
                }
            ]

    monkeypatch.setattr(connectors_router_module, "GitHubConnector", _FakeGitHubConnector)
    monkeypatch.setattr(
        connectors_router_module.ConnectorFactory,
        "create",
        lambda connector_type, db: _FakeGitHubConnector(),
    )

    with TestClient(app) as client:
        resp = client.get(
            "/connectors/github/repositories",
            headers={"Authorization": "Bearer token"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["repositories"][0]["full_name"] == "org/repo"
    assert body["repositories"][0]["owner"] == "org"


def test_connectors_google_drive_auth_and_status(monkeypatch):
    app = _make_app()

    class _FakeGoogleDriveConnector:
        async def get_auth_url(self, state: str):
            return f"https://accounts.example/auth?state={state}"

        async def get_status(self, user_id: str):
            return SimpleNamespace(
                is_connected=True,
                connector_type="google_drive",
                metadata={"email": "u@example.com"},
                access_token="tok",
            )

        async def get_connector(self, user_id: str):
            return {"id": "conn"}

        async def disconnect(self, user_id: str):
            return None

    monkeypatch.setattr(
        connectors_router_module.ConnectorFactory,
        "create",
        lambda connector_type, db: _FakeGoogleDriveConnector(),
    )

    with TestClient(app) as client:
        auth = client.get(
            "/connectors/google-drive/auth-url",
            headers={"Authorization": "Bearer token"},
        )
        assert auth.status_code == 200
        assert auth.json()["auth_url"].startswith("https://accounts.example/auth")
        assert auth.json()["state"]

        status = client.get(
            "/connectors/google-drive/status",
            headers={"Authorization": "Bearer token"},
        )
        assert status.status_code == 200
        assert status.json()["is_connected"] is True

        disconnect = client.delete(
            "/connectors/google-drive",
            headers={"Authorization": "Bearer token"},
        )
        assert disconnect.status_code == 200
        assert disconnect.json()["success"] is True


def test_connectors_google_drive_picker_config_validation(monkeypatch):
    app = _make_app()

    class _FakeGoogleDriveConnector:
        async def get_picker_config(self, user_id: str):
            return {
                "is_connected": True,
                "access_token": "tok",
                "developer_key": "dev",
                "app_id": "app",
            }

    monkeypatch.setattr(connectors_router_module, "GoogleDriveConnector", _FakeGoogleDriveConnector)
    monkeypatch.setattr(
        connectors_router_module.ConnectorFactory,
        "create",
        lambda connector_type, db: _FakeGoogleDriveConnector(),
    )

    with TestClient(app) as client:
        ok = client.get(
            "/connectors/google-drive/picker-config",
            headers={"Authorization": "Bearer token"},
        )
        assert ok.status_code == 200
        assert ok.json()["developer_key"] == "dev"

    class _BadConnector:
        pass

    monkeypatch.setattr(
        connectors_router_module.ConnectorFactory,
        "create",
        lambda connector_type, db: _BadConnector(),
    )

    with TestClient(app) as client:
        bad = client.get(
            "/connectors/google-drive/picker-config",
            headers={"Authorization": "Bearer token"},
        )
        assert bad.status_code == 500
        assert bad.json()["error_code"] == "connector_config"


def test_connectors_github_status_disconnect_and_app_config(monkeypatch):
    app = _make_app()

    class _FakeGitHubConnector:
        async def get_status(self, user_id: str):
            return SimpleNamespace(
                is_connected=True,
                connector_type="github",
                metadata={"login": "org"},
                access_token="tok",
            )

        async def get_connector(self, user_id: str):
            return {"id": "conn"}

        async def disconnect(self, user_id: str):
            return None

        async def get_app_config(self):
            return {
                "app_name": "My App",
                "installation_url": "https://github.com/apps/my-app/installations/new",
            }

    monkeypatch.setattr(connectors_router_module, "GitHubConnector", _FakeGitHubConnector)
    monkeypatch.setattr(
        connectors_router_module.ConnectorFactory,
        "create",
        lambda connector_type, db: _FakeGitHubConnector(),
    )

    with TestClient(app) as client:
        status = client.get(
            "/connectors/github/status",
            headers={"Authorization": "Bearer token"},
        )
        assert status.status_code == 200
        assert status.json()["connector_type"] == "github"

        app_cfg = client.get("/connectors/github/app-config")
        assert app_cfg.status_code == 200
        assert app_cfg.json()["app_name"] == "My App"

        disconnected = client.delete(
            "/connectors/github",
            headers={"Authorization": "Bearer token"},
        )
        assert disconnected.status_code == 200
        assert disconnected.json()["success"] is True
