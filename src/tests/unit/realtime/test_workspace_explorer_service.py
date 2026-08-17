from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from ii_agent.agents.sandboxes.explorer import WorkspaceExplorer, _WatcherState
from ii_agent.realtime.events.app_events import FileTreeUpdateEvent

pytestmark = pytest.mark.unit


class _FakeTree:
    def __init__(self, payload):
        self._payload = payload

    def model_dump(self):
        return self._payload


class _FakeEvent:
    def __init__(self, change_type: str, name: str):
        self.type = SimpleNamespace(value=change_type)
        self.name = name


def _explorer() -> WorkspaceExplorer:
    svc = WorkspaceExplorer(sandbox_service=MagicMock())
    svc.set_pubsub(AsyncMock())
    return svc


def _session_info() -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4())


# ── ensure_watching ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ensure_watching_does_nothing_when_no_pubsub():
    svc = WorkspaceExplorer(sandbox_service=MagicMock())
    await svc.ensure_watching(session_info=_session_info())
    assert not svc._watchers


@pytest.mark.asyncio
async def test_ensure_watching_does_nothing_when_no_sandbox():
    svc = _explorer()
    with patch.object(svc, "_get_sandbox", AsyncMock(return_value=None)):
        await svc.ensure_watching(session_info=_session_info())
    assert not svc._watchers


@pytest.mark.asyncio
async def test_ensure_watching_registers_session_on_existing_watcher():
    svc = _explorer()
    sandbox = MagicMock(provider_sandbox_id="sandbox-1")
    svc._watchers["sandbox-1"] = _WatcherState(
        provider_id="sandbox-1", sandbox=sandbox, session_ids={"old-session"}
    )
    session = _session_info()
    sandbox_for_get = MagicMock(provider_sandbox_id="sandbox-1")

    with patch.object(svc, "_get_sandbox", AsyncMock(return_value=sandbox_for_get)):
        await svc.ensure_watching(session_info=session)

    assert str(session.id) in svc._watchers["sandbox-1"].session_ids


@pytest.mark.asyncio
async def test_ensure_watching_starts_watcher_when_not_running():
    svc = _explorer()
    session = _session_info()
    sandbox = MagicMock(provider_sandbox_id="sandbox-1")

    with (
        patch.object(svc, "_get_sandbox", AsyncMock(return_value=sandbox)),
        patch.object(svc, "_start_watcher", AsyncMock()) as start,
    ):
        await svc.ensure_watching(session_info=session)

    start.assert_awaited_once_with("sandbox-1", str(session.id), sandbox)


# ── Debounce scheduling ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_debounce_schedules_flush_and_coalesces():
    svc = _explorer()
    sandbox = MagicMock()
    state = _WatcherState(provider_id="sandbox-1", sandbox=sandbox)
    svc._watchers["sandbox-1"] = state

    assert state.debounce_task is None
    svc._schedule_flush("sandbox-1")
    assert state.debounce_task is not None

    first = state.debounce_task
    svc._schedule_flush("sandbox-1")
    assert state.debounce_task is first

    first.cancel()
    try:
        await first
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_debounce_skips_unknown_sandbox():
    svc = _explorer()
    svc._schedule_flush("unknown")  # should not raise


# ── Flush ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_flush_publishes_changes_to_sessions():
    svc = _explorer()
    sandbox = AsyncMock()
    sandbox.list_files_with_contents.return_value = (
        _FakeTree({"name": "workspace", "type": "directory", "children": []}),
        {},
    )

    session_id = "00000000-0000-0000-0000-000000000001"
    state = _WatcherState(
        provider_id="sandbox-1",
        sandbox=sandbox,
        session_ids={session_id},
    )
    state.event_queue.put_nowait(_FakeEvent("CREATE", "app.py"))

    pubsub = AsyncMock()
    svc.set_pubsub(pubsub)

    await svc._flush("sandbox-1", state)

    pubsub.publish.assert_awaited_once()
    evt = pubsub.publish.await_args.args[0]
    assert isinstance(evt, FileTreeUpdateEvent)
    assert evt.content["changes"] == [
        {"type": "create", "name": "app.py", "path": "/workspace/app.py"}
    ]
    assert "tree" in evt.content


@pytest.mark.asyncio
async def test_flush_skips_tree_refresh_for_write_only():
    svc = _explorer()
    sandbox = AsyncMock()
    state = _WatcherState(
        provider_id="sandbox-1",
        sandbox=sandbox,
        session_ids={"00000000-0000-0000-0000-000000000001"},
    )
    state.event_queue.put_nowait(_FakeEvent("WRITE", "/workspace/app.py"))

    pubsub = AsyncMock()
    svc.set_pubsub(pubsub)

    await svc._flush("sandbox-1", state)

    evt = pubsub.publish.await_args.args[0]
    assert "tree" not in evt.content
    sandbox.list_files_with_contents.assert_not_awaited()


@pytest.mark.parametrize(
    "name",
    [
        ".ii_app",
        ".ii_app/cache.json",
        ".ii-app",
        ".ii-app/web.json",
        "/workspace/.ii-app/web.json",
    ],
)
def test_build_changes_ignores_ii_app_cache_paths(name: str):
    changes = WorkspaceExplorer._build_changes([_FakeEvent("WRITE", name)])

    assert changes == []


def test_build_changes_keeps_regular_dotfiles():
    changes = WorkspaceExplorer._build_changes([_FakeEvent("WRITE", ".gitignore")])

    assert changes == [{"type": "write", "name": ".gitignore", "path": "/workspace/.gitignore"}]


# ── Watcher start ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_watcher_sets_up_watch_dir():
    svc = _explorer()
    watch_handle = MagicMock()
    sandbox = AsyncMock()
    sandbox.watch_dir = AsyncMock(return_value=watch_handle)

    await svc._start_watcher("sandbox-1", "sess-1", sandbox)

    assert "sandbox-1" in svc._watchers
    sandbox.watch_dir.assert_awaited_once_with(
        "/workspace",
        on_event=ANY,
        on_exit=ANY,
        timeout=0,
        recursive=True,
    )


@pytest.mark.asyncio
async def test_start_watcher_does_nothing_on_sandbox_error():
    svc = _explorer()
    sandbox = AsyncMock()
    sandbox.watch_dir = AsyncMock(side_effect=Exception("connection failed"))

    await svc._start_watcher("sandbox-1", "sess-1", sandbox)

    assert "sandbox-1" not in svc._watchers


# ── Cleanup ──────────────────────────────────────────────────────


def test_cleanup_watcher_removes_state():
    svc = _explorer()
    sandbox = MagicMock()
    svc._watchers["sandbox-1"] = _WatcherState(provider_id="sandbox-1", sandbox=sandbox)
    svc._cleanup_watcher("sandbox-1")
    assert "sandbox-1" not in svc._watchers


@pytest.mark.asyncio
async def test_shutdown_stops_all_watchers():
    svc = _explorer()
    sandbox = MagicMock()
    svc._watchers["sandbox-1"] = _WatcherState(provider_id="sandbox-1", sandbox=sandbox)
    svc._watchers["sandbox-2"] = _WatcherState(provider_id="sandbox-2", sandbox=sandbox)

    await svc.shutdown()

    assert not svc._watchers


@pytest.mark.asyncio
async def test_stop_watcher_handles_sync_stop():
    svc = _explorer()
    watch_handle = MagicMock()
    sandbox = MagicMock()
    svc._watchers["sandbox-1"] = _WatcherState(
        provider_id="sandbox-1",
        sandbox=sandbox,
        watch_handle=watch_handle,
    )

    await svc._stop_watcher("sandbox-1")

    watch_handle.stop.assert_called_once_with()
    assert "sandbox-1" not in svc._watchers


@pytest.mark.asyncio
async def test_stop_watcher_handles_async_stop():
    svc = _explorer()
    async_handle = MagicMock()
    async_handle.stop = AsyncMock()
    sandbox = MagicMock()
    svc._watchers["sandbox-1"] = _WatcherState(
        provider_id="sandbox-1",
        sandbox=sandbox,
        watch_handle=async_handle,
    )

    await svc._stop_watcher("sandbox-1")

    async_handle.stop.assert_awaited_once_with()
    assert "sandbox-1" not in svc._watchers
