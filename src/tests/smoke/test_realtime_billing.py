import pytest
from unittest.mock import MagicMock

from ii_agent.billing.exceptions import StripeConfigError
from ii_agent.billing.service import BillingService

try:
    from ii_agent.realtime.manager import SocketIOManager
except ImportError:
    pytest.skip("Transitive google-genai dependency not available", allow_module_level=True)

pytestmark = pytest.mark.smoke


class FakeSio:
    def __init__(self):
        self.sessions = {}

    async def save_session(self, sid, data):
        self.sessions[sid] = data

    async def get_session(self, sid):
        return self.sessions.get(sid)


@pytest.mark.asyncio
async def test_realtime_connect_sanity(monkeypatch):
    fake_pubsub = MagicMock()
    fake_container = MagicMock()
    fake_container.live_terminal_service.bind_socketio = MagicMock()

    manager = SocketIOManager(FakeSio(), pubsub=fake_pubsub, container=fake_container)

    monkeypatch.setattr(
        "ii_agent.realtime.manager.jwt_handler.verify_access_token",
        lambda token: {"user_id": "00000000-0000-0000-0000-000000000001"},
    )

    accepted = await manager.connect("sid-1", {}, auth={"token": "ok"})

    assert accepted is True


def test_billing_config_missing_secret_key_raises(settings_factory):
    settings = settings_factory(stripe={"secret_key": None})
    billing_service = BillingService(settings=settings)

    with pytest.raises(StripeConfigError):
        billing_service._ensure_api_key()
