from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

try:
    from ii_agent.realtime.manager import SocketIOManager
except ImportError:
    pytest.skip("Transitive google-genai dependency not available", allow_module_level=True)

pytestmark = pytest.mark.integration


class FakeSio:
    def __init__(self):
        self.sessions = {}
        self.events = []
        self.rooms = []

    async def save_session(self, sid, data):
        self.sessions[sid] = data

    async def get_session(self, sid):
        return self.sessions.get(sid)

    async def emit(self, event, payload, room=None, to=None):
        self.events.append((event, payload, room or to))

    async def enter_room(self, sid, room):
        self.rooms.append((sid, room))

    async def leave_room(self, sid, room):
        return None

    async def disconnect(self, sid):
        return None

    def event(self, fn):
        return fn

    def on(self, name):
        def _decorator(fn):
            return fn

        return _decorator


@pytest.mark.asyncio
async def test_realtime_connect_and_join_flow(monkeypatch):
    sio = FakeSio()
    session_id = uuid4()
    user_uuid = uuid4()

    fake_pubsub = MagicMock()
    fake_container = MagicMock()
    fake_container.live_terminal_service.bind_socketio = MagicMock()
    fake_container.session_service.get_or_create_session = AsyncMock(
        return_value=SimpleNamespace(id=session_id, user_id=user_uuid, is_public=False)
    )
    manager = SocketIOManager(sio, pubsub=fake_pubsub, container=fake_container)

    manager.command_factory = SimpleNamespace(get_handler_by_string=lambda _: None)

    @asynccontextmanager
    async def _db_cm():
        yield None

    monkeypatch.setattr("ii_agent.realtime.manager.get_db_session_local", _db_cm)
    monkeypatch.setattr(
        "ii_agent.realtime.manager.jwt_handler.verify_access_token",
        lambda token: {"user_id": str(user_uuid)},
    )

    connected = await manager.connect("sid-1", {}, auth={"token": "ok"})
    await manager.join_session("sid-1", {"session_uuid": str(session_id)})

    assert connected is True
    assert ("sid-1", str(session_id)) in sio.rooms
