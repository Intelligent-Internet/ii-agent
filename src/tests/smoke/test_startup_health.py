from contextlib import asynccontextmanager

import httpx
import pytest

try:
    from ii_agent import app as app_module
except ImportError:
    pytest.skip("Transitive google-genai dependency not available", allow_module_level=True)

pytestmark = pytest.mark.smoke


@pytest.mark.asyncio
async def test_app_startup_and_health_route(monkeypatch, settings_factory):
    @asynccontextmanager
    async def _noop_lifespan(_app):
        yield

    monkeypatch.setattr(app_module, "create_lifespan", lambda sio: _noop_lifespan)
    monkeypatch.setattr(app_module, "get_settings", lambda: settings_factory())

    asgi_app = app_module.create_app()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=asgi_app),
        base_url="http://test",
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
