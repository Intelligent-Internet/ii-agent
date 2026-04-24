import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from ii_agent.agents.sandboxes.shell import (
    ShellExecutionRequest,
    ShellOperationError,
    ShellResult,
    ShellSessionRecord,
    ShellSessionState,
)
from ii_agent.agents.sandboxes.service import SandboxService
from ii_agent.agents.sandboxes.types import SandboxProviderType, SandboxStatus


class FakeSandboxRepo:
    def __init__(self, records_by_session_id):
        self.records_by_session_id = records_by_session_id

    async def get_active_by_session_id(self, db, session_id):
        return self.records_by_session_id.get(session_id)


class FakeSessionRepo:
    def __init__(self, sessions_by_id):
        self.sessions_by_id = sessions_by_id

    async def get_by_id(self, db, session_id):
        return self.sessions_by_id.get(session_id)


@asynccontextmanager
async def _noop_db_cm():
    yield None


def _make_record(
    *,
    status: ShellSessionState = ShellSessionState.IDLE,
    prompt_seq: int = 7,
    pending_prompt_seq: int | None = None,
) -> ShellSessionRecord:
    return ShellSessionRecord(
        pid=123,
        cwd="/workspace/project",
        log_path="/workspace/.ii_agent/pty/build.log",
        state_path="/workspace/.ii_agent/pty/build.state",
        status=status,
        prompt_seq=prompt_seq,
        pending_prompt_seq=pending_prompt_seq,
        updated_at="2026-04-02T00:00:00+00:00",
    )


def _make_connected_shell(
    monkeypatch, service, *, sessions: dict[str, ShellSessionRecord] | None = None
):
    shell = MagicMock()
    shell.workspace_path = "/workspace"
    shell.max_timeout = 180
    shell.poll_interval = 0
    shell.validate_session_name = MagicMock()
    shell.normalize_directory = AsyncMock(side_effect=lambda directory: directory)
    shell.is_session_live = AsyncMock(return_value=True)
    shell.refresh_session_record = AsyncMock(side_effect=lambda record: (record, False))
    shell.send_stdin = AsyncMock()
    shell.wait_for_prompt = AsyncMock()
    shell.read_command_output = AsyncMock(
        return_value=ShellResult(clean_output="ok", ansi_output="ok")
    )
    shell.read_session_output = AsyncMock(
        return_value=ShellResult(clean_output="tail", ansi_output="tail")
    )

    sandbox = SimpleNamespace(shell=shell, sandbox_id=str(uuid.uuid4()))
    monkeypatch.setattr(service, "get_sandbox_for_session", AsyncMock(return_value=sandbox))
    monkeypatch.setattr(
        "ii_agent.agents.sandboxes.service.get_db_session_local",
        lambda: _noop_db_cm(),
    )
    monkeypatch.setattr(
        service,
        "load_provider_data",
        AsyncMock(
            return_value={
                "provider": "e2b",
                "pty_sessions": {
                    session_name: record.model_dump(mode="json")
                    for session_name, record in (sessions or {}).items()
                },
            }
        ),
    )
    monkeypatch.setattr(service, "persist_provider_data", AsyncMock())
    return sandbox, shell


@pytest.mark.asyncio
async def test_init_sandbox_pool_claim_passes_caller_db_to_set_timeout(
    settings_factory, monkeypatch
):
    """Regression test for the 2026-04-24 pool-claim self-deadlock.

    The pool-claim branch of ``init_sandbox`` MUST pass the caller's
    ``db`` session to ``sandbox_mgr.set_timeout(...)``. If a future
    refactor drops the ``db=db`` keyword and falls back to the
    ``db=None`` separate-session path, ``set_timeout`` opens its own
    ``AsyncSession`` and races for the same ``agent_sandboxes`` row-lock
    that the caller's ``update_provider_info`` flush is still holding —
    producing a self-deadlock that wedges every subsequent agent run
    silently.

    This test is the service-layer companion to
    ``TestSetTimeout::test_uses_caller_session_when_db_passed`` (which
    only proves ``set_timeout`` itself is correct). Together they lock
    in both halves of the structural fix described in
    docs/design-docs/sandbox-pool-claim-self-deadlock.md.
    """
    session_id = uuid.uuid4()
    user_id = uuid.uuid4()

    # ── Fake claimed pool record ──
    record = SimpleNamespace(
        id=uuid.uuid4(),
        session_id=session_id,
        provider=SandboxProviderType.DOCKER,
        provider_sandbox_id="container-abc",
        status=SandboxStatus.RUNNING,
        expired_at=None,
        provider_data={},
        pool_state="claimed",
        pool_slot=None,
    )

    # ── Mock pool manager that returns the claimed record. ──
    pool_manager = SimpleNamespace(claim=AsyncMock(return_value=record))

    # ── Sandbox repo: no existing record (forces pool claim). ──
    sandbox_repo = SimpleNamespace(
        get_active_by_session_id=AsyncMock(return_value=None),
        update_provider_info=AsyncMock(return_value=record),
    )
    session_repo = FakeSessionRepo({})

    settings = settings_factory()
    # Use a non-zero timeout so the pool-claim set_timeout branch fires.
    settings.sandbox.timeout_seconds = 3600

    service = SandboxService(
        sandbox_repo=sandbox_repo,
        session_repo=session_repo,
        config=settings,
    )
    service.attach_pool_manager(pool_manager)

    # ── Mock _connect_provider so we avoid touching the real Docker SDK. ──
    sandbox_mgr = SimpleNamespace(
        status=SandboxStatus.RUNNING,
        provider_sandbox_id="container-abc",
        expired_at=None,
        metadata={},
        set_timeout=AsyncMock(),
    )
    monkeypatch.setattr(service, "_connect_provider", AsyncMock(return_value=sandbox_mgr))
    # Suppress fire-and-forget MCP background task.
    monkeypatch.setattr(service, "_spawn_configure_mcp", lambda *a, **kw: None)

    # ── db must support .commit() (await db.commit() runs after the claim). ──
    db = MagicMock()
    db.commit = AsyncMock()

    # We need the sentinel object to *be* the db that init_sandbox uses.
    # init_sandbox accepts ``db`` as its first positional arg, so just pass it.
    await service.init_sandbox(db, session_id=session_id, user_id=user_id)

    # ── Critical invariant: set_timeout was called with the caller's db. ──
    sandbox_mgr.set_timeout.assert_awaited_once()
    call_args = sandbox_mgr.set_timeout.await_args
    # Positional: timeout_seconds. Keyword: db must be the same object.
    assert call_args.args == (3600,), call_args
    assert "db" in call_args.kwargs, (
        "init_sandbox MUST pass db=db to set_timeout on the pool-claim path; "
        "see docs/design-docs/sandbox-pool-claim-self-deadlock.md"
    )
    assert call_args.kwargs["db"] is db, (
        "set_timeout received a different db than the caller's — this "
        "would re-introduce the 2026-04-24 self-deadlock"
    )


@pytest.mark.asyncio
async def test_get_by_session_id_falls_back_to_parent_session(settings_factory):
    parent_id = uuid.uuid4()
    child_id = uuid.uuid4()
    parent_record = SimpleNamespace(
        id=uuid.uuid4(),
        session_id=parent_id,
        provider=SandboxProviderType.E2B,
        provider_sandbox_id="sbx-parent",
        status=SandboxStatus.RUNNING,
        expired_at=None,
        provider_data={"source": "parent"},
    )
    service = SandboxService(
        sandbox_repo=FakeSandboxRepo({parent_id: parent_record}),
        session_repo=FakeSessionRepo(
            {
                child_id: SimpleNamespace(id=child_id, parent_session_id=parent_id),
            }
        ),
        config=settings_factory(),
    )

    record = await service.get_by_session_id(None, child_id)

    assert record is parent_record


@pytest.mark.asyncio
async def test_get_sandbox_for_session_uses_parent_sandbox_for_fork(settings_factory, monkeypatch):
    parent_id = uuid.uuid4()
    child_id = uuid.uuid4()
    parent_record = SimpleNamespace(
        id=uuid.uuid4(),
        session_id=parent_id,
        provider=SandboxProviderType.E2B,
        provider_sandbox_id="sbx-parent",
        status=SandboxStatus.RUNNING,
        expired_at=None,
        provider_data={"source": "parent"},
    )
    service = SandboxService(
        sandbox_repo=FakeSandboxRepo({parent_id: parent_record}),
        session_repo=FakeSessionRepo(
            {
                child_id: SimpleNamespace(id=child_id, parent_session_id=parent_id),
            }
        ),
        config=settings_factory(),
    )
    expected_sandbox = SimpleNamespace(provider_sandbox_id="sbx-parent")

    async def fake_connect(record):
        assert record is parent_record
        return expected_sandbox

    monkeypatch.setattr(service, "_connect_provider", fake_connect)

    sandbox = await service.get_sandbox_for_session(None, child_id)

    assert sandbox is expected_sandbox


@pytest.mark.asyncio
async def test_get_sandbox_for_session_propagates_provider_connection_errors(
    settings_factory, monkeypatch
):
    session_id = uuid.uuid4()
    record = SimpleNamespace(
        id=uuid.uuid4(),
        session_id=session_id,
        provider=SandboxProviderType.E2B,
        provider_sandbox_id="sbx-1",
        status=SandboxStatus.RUNNING,
        expired_at=None,
        provider_data={},
    )
    service = SandboxService(
        sandbox_repo=FakeSandboxRepo({session_id: record}),
        session_repo=FakeSessionRepo({}),
        config=settings_factory(),
    )

    async def fake_connect(_record):
        raise RuntimeError("e2b unavailable")

    monkeypatch.setattr(service, "_connect_provider", fake_connect)

    with pytest.raises(RuntimeError, match="e2b unavailable"):
        await service.get_sandbox_for_session(None, session_id)


@pytest.mark.asyncio
async def test_get_sandbox_by_session_id_aliases_existing_lookup(settings_factory, monkeypatch):
    session_id = uuid.uuid4()
    expected_sandbox = SimpleNamespace(provider_sandbox_id="sbx-1")
    service = SandboxService(
        sandbox_repo=FakeSandboxRepo({}),
        session_repo=FakeSessionRepo({}),
        config=settings_factory(),
    )

    get_sandbox_for_session = AsyncMock(return_value=expected_sandbox)
    monkeypatch.setattr(service, "get_sandbox_for_session", get_sandbox_for_session)

    sandbox = await service.get_sandbox_by_session_id(None, str(session_id))

    assert sandbox is expected_sandbox
    get_sandbox_for_session.assert_awaited_once_with(None, session_id=session_id)


@pytest.mark.asyncio
async def test_get_sandbox_by_session_loads_user_from_session_when_db_is_implicit(
    settings_factory, monkeypatch
):
    session_id = uuid.uuid4()
    user_id = uuid.uuid4()
    expected_sandbox = SimpleNamespace(provider_sandbox_id="sbx-1")
    service = SandboxService(
        sandbox_repo=FakeSandboxRepo({}),
        session_repo=FakeSessionRepo(
            {
                session_id: SimpleNamespace(id=session_id, user_id=user_id),
            }
        ),
        config=settings_factory(),
    )

    init_sandbox = AsyncMock(return_value=expected_sandbox)
    monkeypatch.setattr(service, "init_sandbox", init_sandbox)
    monkeypatch.setattr(
        "ii_agent.agents.sandboxes.service.get_db_session_local",
        lambda: _noop_db_cm(),
    )

    sandbox = await service.get_sandbox_by_session(session_id)

    assert sandbox is expected_sandbox
    init_sandbox.assert_awaited_once_with(
        None,
        session_id=session_id,
        user_id=user_id,
    )


@pytest.mark.asyncio
async def test_get_sandbox_by_session_accepts_db_first_and_normalizes_user_id(
    settings_factory, monkeypatch
):
    session_id = uuid.uuid4()
    user_id = uuid.uuid4()
    db = object()
    expected_sandbox = SimpleNamespace(provider_sandbox_id="sbx-1")
    service = SandboxService(
        sandbox_repo=FakeSandboxRepo({}),
        session_repo=FakeSessionRepo({}),
        config=settings_factory(),
    )

    init_sandbox = AsyncMock(return_value=expected_sandbox)
    monkeypatch.setattr(service, "init_sandbox", init_sandbox)

    sandbox = await service.get_sandbox_by_session(
        db,
        session_id=session_id,
        user_id=str(user_id),
    )

    assert sandbox is expected_sandbox
    init_sandbox.assert_awaited_once_with(
        db,
        session_id=session_id,
        user_id=user_id,
    )


@pytest.mark.asyncio
async def test_list_shell_sessions_prunes_stale_records(settings_factory, monkeypatch):
    service = SandboxService(
        sandbox_repo=FakeSandboxRepo({}),
        session_repo=FakeSessionRepo({}),
        config=settings_factory(),
    )
    live_record = _make_record()
    stale_record = _make_record()
    sandbox, shell = _make_connected_shell(
        monkeypatch,
        service,
        sessions={"build": live_record, "old": stale_record},
    )
    shell.is_session_live = AsyncMock(side_effect=[True, False])

    result = await service.list_shell_sessions(uuid.uuid4())

    assert result == ["build"]
    service.persist_provider_data.assert_awaited_once()
    persisted_provider_data = service.persist_provider_data.await_args.args[1]
    assert list(persisted_provider_data["pty_sessions"]) == ["build"]
    assert str(sandbox.sandbox_id)


@pytest.mark.asyncio
async def test_create_shell_session_persists_record(settings_factory, monkeypatch):
    service = SandboxService(
        sandbox_repo=FakeSandboxRepo({}),
        session_repo=FakeSessionRepo({}),
        config=settings_factory(),
    )
    record = _make_record()
    _, shell = _make_connected_shell(monkeypatch, service)
    shell.create_session_record = AsyncMock(return_value=record)
    session_id = uuid.uuid4()

    await service.create_shell_session(
        session_id,
        "build",
        "/workspace/project",
        timeout=42,
    )

    shell.validate_session_name.assert_called_once_with("build")
    shell.normalize_directory.assert_awaited_once_with("/workspace/project")
    shell.create_session_record.assert_awaited_once_with(
        "build",
        "/workspace/project",
        timeout=42,
    )
    persisted_provider_data = service.persist_provider_data.await_args.args[1]
    assert persisted_provider_data["pty_sessions"]["build"] == record.model_dump(mode="json")


@pytest.mark.asyncio
async def test_run_shell_command_uses_service_owned_session_registry(settings_factory, monkeypatch):
    service = SandboxService(
        sandbox_repo=FakeSandboxRepo({}),
        session_repo=FakeSessionRepo({}),
        config=settings_factory(),
    )
    record = _make_record()
    _, shell = _make_connected_shell(monkeypatch, service, sessions={"build": record})
    shell.refresh_session_record = AsyncMock(side_effect=[(record, False), (record, False)])
    shell.build_command_request = AsyncMock(
        return_value=ShellExecutionRequest(
            record=record,
            stdin=b"pwd\n",
            log_offset=12,
            expected_prompt_seq=10,
        )
    )
    session_id = uuid.uuid4()

    result = await service.run_shell_command(
        session_id,
        "build",
        "pwd",
        timeout=42,
        wait_for_output=True,
    )

    assert result.clean_output == "ok"
    shell.build_command_request.assert_awaited_once_with(record, "pwd", run_dir=None)
    shell.send_stdin.assert_awaited_once_with("build", record, b"pwd\n")
    shell.wait_for_prompt.assert_awaited_once_with(
        record,
        minimum_prompt_seq=10,
        timeout=42,
    )
    shell.read_command_output.assert_awaited_once_with(record, start_offset=12)


@pytest.mark.asyncio
async def test_delete_shell_session_uses_connected_shell(settings_factory, monkeypatch):
    service = SandboxService(
        sandbox_repo=FakeSandboxRepo({}),
        session_repo=FakeSessionRepo({}),
        config=settings_factory(),
    )
    record = _make_record()
    _, shell = _make_connected_shell(monkeypatch, service, sessions={"build": record})
    shell.delete_session = AsyncMock()
    session_id = uuid.uuid4()

    await service.delete_shell_session(session_id, "build")

    shell.delete_session.assert_awaited_once_with("build", record)
    persisted_provider_data = service.persist_provider_data.await_args.args[1]
    assert persisted_provider_data["pty_sessions"] == {}


@pytest.mark.asyncio
async def test_kill_shell_command_uses_connected_shell(settings_factory, monkeypatch):
    service = SandboxService(
        sandbox_repo=FakeSandboxRepo({}),
        session_repo=FakeSessionRepo({}),
        config=settings_factory(),
    )
    record = _make_record(status=ShellSessionState.BUSY, pending_prompt_seq=8)
    _, shell = _make_connected_shell(monkeypatch, service, sessions={"build": record})
    shell.build_interrupt_request = AsyncMock(
        return_value=ShellExecutionRequest(
            record=record,
            stdin=b"\x03",
            log_offset=5,
            expected_prompt_seq=8,
        )
    )
    shell.refresh_session_record = AsyncMock(return_value=(record, False))
    session_id = uuid.uuid4()

    result = await service.kill_shell_command(
        session_id,
        "build",
        timeout=42,
    )

    assert result.clean_output == "ok"
    shell.build_interrupt_request.assert_awaited_once_with(record)
    shell.send_stdin.assert_awaited_once_with("build", record, b"\x03")
    shell.wait_for_prompt.assert_awaited_once_with(
        record,
        minimum_prompt_seq=8,
        timeout=42,
    )


@pytest.mark.asyncio
async def test_get_shell_session_output_uses_connected_shell(settings_factory, monkeypatch):
    service = SandboxService(
        sandbox_repo=FakeSandboxRepo({}),
        session_repo=FakeSessionRepo({}),
        config=settings_factory(),
    )
    record = _make_record()
    _, shell = _make_connected_shell(monkeypatch, service, sessions={"build": record})
    session_id = uuid.uuid4()

    result = await service.get_shell_session_output(session_id, "build")

    assert result.clean_output == "tail"
    shell.read_session_output.assert_awaited_once_with(record)


@pytest.mark.asyncio
async def test_write_to_shell_process_uses_connected_shell(settings_factory, monkeypatch):
    service = SandboxService(
        sandbox_repo=FakeSandboxRepo({}),
        session_repo=FakeSessionRepo({}),
        config=settings_factory(),
    )
    record = _make_record()
    _, shell = _make_connected_shell(monkeypatch, service, sessions={"build": record})
    shell.build_process_input_request = AsyncMock(
        return_value=ShellExecutionRequest(record=record, stdin=b"yes")
    )
    monkeypatch.setattr(
        service,
        "get_shell_session_output",
        AsyncMock(return_value=ShellResult(clean_output="prompt", ansi_output="prompt")),
    )
    session_id = uuid.uuid4()

    result = await service.write_to_shell_process(
        session_id,
        "build",
        "yes",
        press_enter=False,
    )

    assert result.clean_output == "prompt"
    shell.build_process_input_request.assert_awaited_once_with(record, "yes", False)
    shell.send_stdin.assert_awaited_once_with("build", record, b"yes")


@pytest.mark.asyncio
async def test_get_shell_backend_for_session_raises_when_sandbox_missing(
    settings_factory,
    monkeypatch,
):
    service = SandboxService(
        sandbox_repo=FakeSandboxRepo({}),
        session_repo=FakeSessionRepo({}),
        config=settings_factory(),
    )

    monkeypatch.setattr(service, "get_sandbox_for_session", AsyncMock(return_value=None))
    monkeypatch.setattr(
        "ii_agent.agents.sandboxes.service.get_db_session_local",
        lambda: _noop_db_cm(),
    )

    with pytest.raises(ShellOperationError, match="No sandbox found for session"):
        await service.list_shell_sessions(uuid.uuid4())
