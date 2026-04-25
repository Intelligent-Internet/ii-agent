"""Unit tests for the sandbox MCP handoff hardening (2026-04-25).

Covers the four pieces shipped together:

1. ``Sandbox.expose_port`` default flipped to ``external=False``.
2. ``SandboxService._configure_mcp`` bounded retry envelope.
3. ``SandboxService._probe_mcp_health`` post-attach probe.
4. ``ensure_mcp_configured`` lazy-retry helper used by MCP-tool factories.

See docs/design-docs/sandbox-pool-claim-mcp-handoff-audit.md.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from ii_agent.agents.sandboxes.service import SandboxService


# ── Helpers ────────────────────────────────────────────────────────────────


def _settings_with_mcp_port(port: int = 6060):
    """Minimal settings object exposing ``mcp.port``."""
    return SimpleNamespace(mcp=SimpleNamespace(port=port))


def _make_service(monkeypatch=None):
    return SandboxService(
        sandbox_repo=SimpleNamespace(),
        session_repo=SimpleNamespace(),
        config=_settings_with_mcp_port(),
    )


# ── 1. Default flip ────────────────────────────────────────────────────────


def test_expose_port_default_is_external_false_on_base_protocol():
    """Sandbox.expose_port default must be ``external=False`` so backend
    callers that omit the kwarg get the container-internal URL — which is
    the only network the backend container can reach without hairpin NAT.

    See docs/design-docs/sandbox-pool-claim-mcp-handoff-audit.md for the
    blast-radius analysis.
    """
    import inspect

    from ii_agent.agents.sandboxes.base import Sandbox
    from ii_agent.agents.sandboxes.docker import DockerSandbox
    from ii_agent.agents.sandboxes.e2b import E2BSandbox

    for cls in (Sandbox, DockerSandbox, E2BSandbox):
        sig = inspect.signature(cls.expose_port)
        external_param = sig.parameters["external"]
        assert external_param.default is False, (
            f"{cls.__name__}.expose_port default is {external_param.default!r}; "
            "must be False so backend callers do not silently route through the "
            "host-LAN address that the backend container cannot reach."
        )


# ── 2. Bounded retry envelope ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_configure_mcp_returns_true_on_first_attempt():
    service = _make_service()
    sandbox = SimpleNamespace(
        sandbox_id="sb-1",
        expose_port=AsyncMock(return_value="http://172.19.0.5:6060"),
        get_mcp_client=MagicMock(),
    )
    register = AsyncMock()

    async def stub(self, sandbox, user_id, sandbox_url, db):
        await register(sandbox, user_id, sandbox_url, db)

    SandboxService._register_user_mcp_servers = stub  # type: ignore[method-assign]
    try:
        ok = await service._configure_mcp(sandbox, uuid.uuid4(), db=MagicMock())
    finally:
        del SandboxService._register_user_mcp_servers
    assert ok is True
    assert register.await_count == 1


@pytest.mark.asyncio
async def test_configure_mcp_retries_then_succeeds(monkeypatch):
    service = _make_service()
    # Speed: zero out backoff so the test doesn't actually sleep.
    monkeypatch.setattr(SandboxService, "_CONFIGURE_MCP_BACKOFF_S", (0.0, 0.0, 0.0))

    sandbox = SimpleNamespace(
        sandbox_id="sb-2",
        expose_port=AsyncMock(return_value="http://172.19.0.5:6060"),
        get_mcp_client=MagicMock(),
    )
    calls = {"n": 0}

    async def stub(self, sandbox, user_id, sandbox_url, db):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("All connection attempts failed")
        # third attempt: success

    monkeypatch.setattr(SandboxService, "_register_user_mcp_servers", stub, raising=False)
    ok = await service._configure_mcp(sandbox, uuid.uuid4(), db=MagicMock())
    assert ok is True
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_configure_mcp_returns_false_on_terminal_failure(monkeypatch):
    service = _make_service()
    monkeypatch.setattr(SandboxService, "_CONFIGURE_MCP_BACKOFF_S", (0.0, 0.0, 0.0))

    sandbox = SimpleNamespace(
        sandbox_id="sb-3",
        expose_port=AsyncMock(return_value="http://172.19.0.5:6060"),
        get_mcp_client=MagicMock(),
    )

    async def stub(self, sandbox, user_id, sandbox_url, db):
        raise RuntimeError("All connection attempts failed")

    monkeypatch.setattr(SandboxService, "_register_user_mcp_servers", stub, raising=False)
    ok = await service._configure_mcp(sandbox, uuid.uuid4(), db=MagicMock())
    assert ok is False


@pytest.mark.asyncio
async def test_configure_mcp_returns_false_when_expose_port_fails():
    """If we cannot even resolve the URL there is nothing to retry."""
    service = _make_service()
    sandbox = SimpleNamespace(
        sandbox_id="sb-4",
        expose_port=AsyncMock(side_effect=RuntimeError("port not exposed")),
        get_mcp_client=MagicMock(),
    )
    ok = await service._configure_mcp(sandbox, uuid.uuid4(), db=MagicMock())
    assert ok is False


# ── 3. Post-attach health probe ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_probe_mcp_health_returns_true_on_2xx(monkeypatch):
    service = _make_service()
    sandbox = SimpleNamespace(
        sandbox_id="sb-5",
        expose_port=AsyncMock(return_value="http://172.19.0.5:6060"),
    )

    class FakeResp:
        status_code = 200

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            assert url.endswith("/health")
            return FakeResp()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    assert await service._probe_mcp_health(sandbox) is True


@pytest.mark.asyncio
async def test_probe_mcp_health_returns_false_on_5xx(monkeypatch):
    service = _make_service()
    sandbox = SimpleNamespace(
        sandbox_id="sb-6",
        expose_port=AsyncMock(return_value="http://172.19.0.5:6060"),
    )

    class FakeResp:
        status_code = 503

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            return FakeResp()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    assert await service._probe_mcp_health(sandbox) is False


@pytest.mark.asyncio
async def test_probe_mcp_health_returns_false_on_connect_error(monkeypatch):
    service = _make_service()
    sandbox = SimpleNamespace(
        sandbox_id="sb-7",
        expose_port=AsyncMock(return_value="http://172.19.0.5:6060"),
    )

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            raise ConnectionError("All connection attempts failed")

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    assert await service._probe_mcp_health(sandbox) is False


@pytest.mark.asyncio
async def test_probe_mcp_health_returns_false_when_expose_port_fails():
    service = _make_service()
    sandbox = SimpleNamespace(
        sandbox_id="sb-8",
        expose_port=AsyncMock(side_effect=RuntimeError("nope")),
    )
    assert await service._probe_mcp_health(sandbox) is False


# ── 4. Lazy retry helper ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ensure_mcp_configured_fast_path_when_flag_true(monkeypatch):
    """When the durable flag is True, helper must return without
    triggering a retry attach (the hot tool-call path)."""
    from ii_agent.agents.factory.mcp import lazy_retry

    sb_id = uuid.uuid4()

    class _FakeRecord:
        mcp_configured = True
        mcp_configure_attempted_at = None
        provider_sandbox_id = "container-x"

    fake_repo = SimpleNamespace(get_by_id=AsyncMock(return_value=_FakeRecord()))
    fake_svc = SimpleNamespace(
        _sandbox_repo=fake_repo,
        _MCP_LAZY_RETRY_COOLDOWN_S=30.0,
        _connect_provider=AsyncMock(),
        _configure_mcp_background=AsyncMock(),
    )
    fake_container = SimpleNamespace(sandbox_service=fake_svc)
    monkeypatch.setattr(lazy_retry, "get_app_container", lambda: fake_container)

    # Stub get_db_session_local.
    class _FakeDB:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(lazy_retry, "get_db_session_local", lambda: _FakeDB())

    ok = await lazy_retry.ensure_mcp_configured(sb_id, uuid.uuid4())
    assert ok is True
    fake_svc._connect_provider.assert_not_awaited()
    fake_svc._configure_mcp_background.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_mcp_configured_skips_when_within_cooldown(monkeypatch):
    """When the flag is False but the last attempt was recent, must not
    re-attempt — prevents hammering a wedged container."""
    from ii_agent.agents.factory.mcp import lazy_retry

    sb_id = uuid.uuid4()

    class _FakeRecord:
        mcp_configured = False
        mcp_configure_attempted_at = datetime.now(timezone.utc) - timedelta(seconds=5)
        provider_sandbox_id = "container-x"

    fake_repo = SimpleNamespace(get_by_id=AsyncMock(return_value=_FakeRecord()))
    fake_svc = SimpleNamespace(
        _sandbox_repo=fake_repo,
        _MCP_LAZY_RETRY_COOLDOWN_S=30.0,
        _connect_provider=AsyncMock(),
        _configure_mcp_background=AsyncMock(),
    )
    fake_container = SimpleNamespace(sandbox_service=fake_svc)
    monkeypatch.setattr(lazy_retry, "get_app_container", lambda: fake_container)

    class _FakeDB:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(lazy_retry, "get_db_session_local", lambda: _FakeDB())

    ok = await lazy_retry.ensure_mcp_configured(sb_id, uuid.uuid4())
    assert ok is False
    fake_svc._connect_provider.assert_not_awaited()
    fake_svc._configure_mcp_background.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_mcp_configured_retries_after_cooldown(monkeypatch):
    """When cooldown has elapsed and flag is False, helper must attach
    the provider and run a fresh configure pass."""
    from ii_agent.agents.factory.mcp import lazy_retry

    sb_id = uuid.uuid4()

    state = {"configured": False}

    class _FakeRecord:
        # On the second read we report success.
        @property
        def mcp_configured(self):
            return state["configured"]

        mcp_configure_attempted_at = datetime.now(timezone.utc) - timedelta(seconds=120)
        provider_sandbox_id = "container-x"

    record = _FakeRecord()
    fake_repo = SimpleNamespace(get_by_id=AsyncMock(return_value=record))
    sandbox_mgr = SimpleNamespace()

    async def fake_configure_bg(sandbox, user_id, record_id):
        state["configured"] = True

    fake_svc = SimpleNamespace(
        _sandbox_repo=fake_repo,
        _MCP_LAZY_RETRY_COOLDOWN_S=30.0,
        _connect_provider=AsyncMock(return_value=sandbox_mgr),
        _configure_mcp_background=AsyncMock(side_effect=fake_configure_bg),
    )
    fake_container = SimpleNamespace(sandbox_service=fake_svc)
    monkeypatch.setattr(lazy_retry, "get_app_container", lambda: fake_container)

    class _FakeDB:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(lazy_retry, "get_db_session_local", lambda: _FakeDB())

    ok = await lazy_retry.ensure_mcp_configured(sb_id, uuid.uuid4())
    assert ok is True
    fake_svc._connect_provider.assert_awaited_once()
    fake_svc._configure_mcp_background.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_mcp_configured_returns_true_for_unknown_sandbox(monkeypatch):
    """Non-UUID / missing sandbox id must short-circuit True so legacy /
    test paths cannot be blocked by this gate."""
    from ii_agent.agents.factory.mcp import lazy_retry

    assert await lazy_retry.ensure_mcp_configured("not-a-uuid", uuid.uuid4()) is True


# ── 5. Repository: set_mcp_configured ──────────────────────────────────────


@pytest.mark.asyncio
async def test_set_mcp_configured_updates_flag_and_timestamp():
    """The repository helper must update both fields atomically."""
    from ii_agent.agents.sandboxes.repository import SandboxRepository

    repo = SandboxRepository()

    fake_record = SimpleNamespace(
        mcp_configured=True,
        mcp_configure_attempted_at=None,
    )
    repo.get_by_id = AsyncMock(return_value=fake_record)  # type: ignore[method-assign]

    db = SimpleNamespace(flush=AsyncMock(), refresh=AsyncMock())
    when = datetime.now(timezone.utc)
    out = await repo.set_mcp_configured(db, uuid.uuid4(), configured=False, attempted_at=when)
    assert out is fake_record
    assert fake_record.mcp_configured is False
    assert fake_record.mcp_configure_attempted_at == when
    db.flush.assert_awaited_once()
    db.refresh.assert_awaited_once()


# ── 6. agent.warning emission on configure failure (audit item #7) ────────


@pytest.mark.asyncio
async def test_configure_mcp_background_emits_agent_warning_on_failure(monkeypatch):
    """When _configure_mcp returns False, the background wrapper must
    publish an ``agent.warning`` event on the injected pubsub so the
    frontend can surface "tool subset unavailable" instead of a silent
    degradation. See audit item #7.
    """
    from ii_agent.realtime.events.app_events import AgentWarningEvent

    service = _make_service()

    fake_pubsub = SimpleNamespace(publish=AsyncMock())
    service.set_pubsub(fake_pubsub)

    # Stub the inner configure to fail terminally.
    monkeypatch.setattr(service, "_configure_mcp", AsyncMock(return_value=False))
    # Stub repository persistence path to a no-op.
    service._sandbox_repo = SimpleNamespace(set_mcp_configured=AsyncMock())  # type: ignore[assignment]

    # Patch get_db_session_local to yield a context-managed mock.
    class _CtxDB:
        async def __aenter__(self):
            return SimpleNamespace(commit=AsyncMock())

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr("ii_agent.agents.sandboxes.service.get_db_session_local", lambda: _CtxDB())

    sandbox_record_id = str(uuid.uuid4())
    session_id = uuid.uuid4()
    await service._configure_mcp_background(
        sandbox=SimpleNamespace(sandbox_id="sb-x"),
        user_id=uuid.uuid4(),
        sandbox_record_id=sandbox_record_id,
        session_id=session_id,
    )

    fake_pubsub.publish.assert_awaited_once()
    event = fake_pubsub.publish.await_args.args[0]
    assert isinstance(event, AgentWarningEvent)
    assert event.warning_kind == "mcp_configure_failed"
    assert event.session_id == session_id
    assert event.details["sandbox_id"] == sandbox_record_id


@pytest.mark.asyncio
async def test_configure_mcp_background_skips_warning_on_success(monkeypatch):
    """No warning event when the configure succeeds."""
    service = _make_service()
    fake_pubsub = SimpleNamespace(publish=AsyncMock())
    service.set_pubsub(fake_pubsub)

    monkeypatch.setattr(service, "_configure_mcp", AsyncMock(return_value=True))
    service._sandbox_repo = SimpleNamespace(set_mcp_configured=AsyncMock())  # type: ignore[assignment]

    class _CtxDB:
        async def __aenter__(self):
            return SimpleNamespace(commit=AsyncMock())

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr("ii_agent.agents.sandboxes.service.get_db_session_local", lambda: _CtxDB())

    await service._configure_mcp_background(
        sandbox=SimpleNamespace(sandbox_id="sb-y"),
        user_id=uuid.uuid4(),
        sandbox_record_id=str(uuid.uuid4()),
        session_id=uuid.uuid4(),
    )

    fake_pubsub.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_configure_mcp_background_no_pubsub_does_not_crash(monkeypatch):
    """Service stays functional when pubsub was never wired (tests, scripts)."""
    service = _make_service()  # No set_pubsub call.

    monkeypatch.setattr(service, "_configure_mcp", AsyncMock(return_value=False))
    service._sandbox_repo = SimpleNamespace(set_mcp_configured=AsyncMock())  # type: ignore[assignment]

    class _CtxDB:
        async def __aenter__(self):
            return SimpleNamespace(commit=AsyncMock())

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr("ii_agent.agents.sandboxes.service.get_db_session_local", lambda: _CtxDB())

    # Should not raise.
    await service._configure_mcp_background(
        sandbox=SimpleNamespace(sandbox_id="sb-z"),
        user_id=uuid.uuid4(),
        sandbox_record_id=str(uuid.uuid4()),
        session_id=uuid.uuid4(),
    )


# ── 7. Pool replenish via after_commit hook (audit item #6) ───────────────


@pytest.mark.asyncio
async def test_pool_claim_registers_after_commit_listener_not_immediate_task(monkeypatch):
    """``SandboxPoolManager.claim`` must defer the replenish task creation
    to a SQLAlchemy ``after_commit`` listener so it cannot fire if the
    caller's transaction rolls back. Audit item #6.

    We capture ``event.listen`` to verify (a) exactly one listener was
    registered against the caller's ``sync_session``, (b) the replenish
    coroutine was NOT scheduled at claim time.
    """
    from ii_agent.agents.sandboxes import pool as pool_mod
    from ii_agent.agents.sandboxes.pool import SandboxPoolManager

    pool = SandboxPoolManager.__new__(SandboxPoolManager)
    pool._sandbox_repo = SimpleNamespace(  # type: ignore[attr-defined]
        claim_oldest_available=AsyncMock(return_value=(SimpleNamespace(id=uuid.uuid4()), 3))
    )
    pool._create_slot_async = AsyncMock()  # type: ignore[attr-defined]
    type(pool).enabled = property(lambda self: True)  # type: ignore[assignment]

    fake_sync = object()
    fake_db = SimpleNamespace(sync_session=fake_sync)

    captured: list = []

    def _capturing_listen(target, name, fn, **kw):
        captured.append((target, name, fn, kw))

    monkeypatch.setattr(pool_mod.event, "listen", _capturing_listen)

    row = await pool.claim(fake_db, uuid.uuid4())  # type: ignore[arg-type]
    assert row is not None

    # Replenish must NOT have run yet — caller hasn't committed.
    pool._create_slot_async.assert_not_called()

    # Exactly one after_commit listener registered against fake sync_session.
    assert len(captured) == 1
    target, name, _fn, kw = captured[0]
    assert target is fake_sync
    assert name == "after_commit"
    assert kw.get("once") is True


@pytest.mark.asyncio
async def test_pool_claim_after_commit_listener_schedules_replenish(monkeypatch):
    """When the registered ``after_commit`` listener fires, it must schedule
    the slot replenish on the running event loop. Verifies the closure
    captured the correct slot index.
    """
    import asyncio as _asyncio

    from ii_agent.agents.sandboxes import pool as pool_mod
    from ii_agent.agents.sandboxes.pool import SandboxPoolManager

    pool = SandboxPoolManager.__new__(SandboxPoolManager)
    pool._sandbox_repo = SimpleNamespace(  # type: ignore[attr-defined]
        claim_oldest_available=AsyncMock(return_value=(SimpleNamespace(id=uuid.uuid4()), 9))
    )

    create_calls: list[tuple[int, bool]] = []

    async def _fake_create_slot(slot, is_bootstrap):
        create_calls.append((slot, is_bootstrap))

    pool._create_slot_async = _fake_create_slot  # type: ignore[assignment]
    type(pool).enabled = property(lambda self: True)  # type: ignore[assignment]

    captured: list = []

    def _capturing_listen(target, name, fn, **kw):
        captured.append(fn)

    monkeypatch.setattr(pool_mod.event, "listen", _capturing_listen)

    fake_sync = object()
    fake_db = SimpleNamespace(sync_session=fake_sync)

    await pool.claim(fake_db, uuid.uuid4())  # type: ignore[arg-type]
    assert len(captured) == 1, "Pool must register exactly one after_commit listener"
    assert create_calls == [], "Replenish must not fire before commit"

    # Simulate the commit lifecycle: SQLAlchemy invokes the listener
    # synchronously. The listener must schedule the replenish task; we
    # then yield to the loop to let it actually run.
    captured[0](fake_sync)
    await _asyncio.sleep(0)
    await _asyncio.sleep(0)

    assert create_calls == [(9, False)]
