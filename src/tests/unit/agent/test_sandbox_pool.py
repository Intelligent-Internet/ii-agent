"""Unit tests for the pre-warmed sandbox pool manager.

Covers:
- Slot enumeration / modulo retirement formula
- Bootstrap creates all missing slots in parallel
- Claim atomically transitions AVAILABLE -> CLAIMED and triggers replenish
- Retirement marks AVAILABLE rows past retire_at as RETIRING
- ensure_full re-creates missing slots (the "ASAP" replenish)
- Concurrent create attempts for the same slot are de-duped
- Provider failures do not propagate to the request path
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.agents.sandboxes.exceptions import SandboxCreationError
from ii_agent.agents.sandboxes.models import AgentSandbox
from ii_agent.agents.sandboxes.pool import SandboxPoolManager
from ii_agent.agents.sandboxes.types import (
    PoolState,
    SandboxProviderType,
    SandboxStatus,
)


_MODULE = "ii_agent.agents.sandboxes.pool"

pytestmark = pytest.mark.unit


# ───────────────────────────── Test helpers ──────────────────────────────


def _make_settings(*, pool_size: int = 2, max_age: int = 86400, enabled: bool = True):
    """Build a minimal Settings stand-in."""
    sandbox_cfg = SimpleNamespace(
        prewarm_pool_size=pool_size,
        prewarm_max_age_seconds=max_age,
        provider="docker" if enabled else "e2b",
        local_mode=enabled,
    )
    return SimpleNamespace(sandbox=sandbox_cfg)


def _make_pool_row(
    *,
    slot: int,
    state: PoolState = PoolState.AVAILABLE,
    status: SandboxStatus = SandboxStatus.RUNNING,
    retire_at: datetime | None = None,
    sandbox_id: uuid.UUID | None = None,
    provider_sandbox_id: str | None = "container-abc",
    session_id: uuid.UUID | None = None,
    created_at: datetime | None = None,
) -> AgentSandbox:
    """Build a real ORM-bound AgentSandbox row (no DB needed)."""
    row = AgentSandbox(
        session_id=session_id,
        provider=SandboxProviderType.DOCKER,
        provider_sandbox_id=provider_sandbox_id,
        status=status,
        pool_state=state,
        pool_slot=slot,
        retire_at=retire_at,
    )
    # `id` is server_default — set explicitly for test predictability.
    row.id = sandbox_id or uuid.uuid4()
    row.created_at = created_at or datetime.now(timezone.utc)
    row.updated_at = row.created_at
    return row


def _make_sandbox_mgr(provider_sandbox_id: str = "ctr-xyz") -> MagicMock:
    """Mock provider Sandbox returned by the create function."""
    mgr = MagicMock()
    mgr.provider_sandbox_id = provider_sandbox_id
    mgr.expired_at = None
    mgr.metadata = {"foo": "bar"}
    mgr.status = SandboxStatus.RUNNING
    return mgr


def _patch_db():
    """Patch get_db_session_local with a noop async context manager."""
    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()

    ctx = patch(f"{_MODULE}.get_db_session_local")
    mock_get_db = ctx.start()
    mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
    mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)
    return ctx, mock_db


# ───────────────────────── Slot/retirement math ──────────────────────────


class TestRetirementSchedule:
    """Modulo enumeration of retirement deadlines."""

    def test_stagger_seconds_n2_24h(self):
        cfg = _make_settings(pool_size=2, max_age=86400)
        mgr = SandboxPoolManager(MagicMock(), cfg, AsyncMock())
        assert mgr.stagger_seconds == 43200  # 12h

    def test_stagger_seconds_n3_24h(self):
        cfg = _make_settings(pool_size=3, max_age=86400)
        mgr = SandboxPoolManager(MagicMock(), cfg, AsyncMock())
        assert mgr.stagger_seconds == 28800  # 8h

    def test_stagger_seconds_n1(self):
        cfg = _make_settings(pool_size=1, max_age=86400)
        mgr = SandboxPoolManager(MagicMock(), cfg, AsyncMock())
        assert mgr.stagger_seconds == 86400

    def test_bootstrap_retire_at_slot0_full_lifetime(self):
        cfg = _make_settings(pool_size=2, max_age=86400)
        mgr = SandboxPoolManager(MagicMock(), cfg, AsyncMock())
        now = datetime(2026, 4, 22, 12, 0, 0, tzinfo=timezone.utc)
        retire = mgr.compute_bootstrap_retire_at(0, now=now)
        assert retire == now + timedelta(seconds=86400)

    def test_bootstrap_retire_at_slot1_offset(self):
        cfg = _make_settings(pool_size=2, max_age=86400)
        mgr = SandboxPoolManager(MagicMock(), cfg, AsyncMock())
        now = datetime(2026, 4, 22, 12, 0, 0, tzinfo=timezone.utc)
        retire = mgr.compute_bootstrap_retire_at(1, now=now)
        # 86400 - 1*43200 = 43200s = 12h offset
        assert retire == now + timedelta(seconds=43200)

    def test_bootstrap_retire_at_slot2_double_offset(self):
        cfg = _make_settings(pool_size=3, max_age=86400)
        mgr = SandboxPoolManager(MagicMock(), cfg, AsyncMock())
        now = datetime(2026, 4, 22, 12, 0, 0, tzinfo=timezone.utc)
        retire = mgr.compute_bootstrap_retire_at(2, now=now)
        # 86400 - 2*28800 = 28800s = 8h
        assert retire == now + timedelta(seconds=28800)

    def test_replacement_retire_at_full_lifetime(self):
        cfg = _make_settings(pool_size=2, max_age=86400)
        mgr = SandboxPoolManager(MagicMock(), cfg, AsyncMock())
        now = datetime(2026, 4, 22, 12, 0, 0, tzinfo=timezone.utc)
        retire = mgr.compute_replacement_retire_at(now=now)
        assert retire == now + timedelta(seconds=86400)

    def test_replacement_preserves_offset_across_cycles(self):
        """Slot 0 cycles every 24h; slot 1 cycles 12h offset, perpetually."""
        cfg = _make_settings(pool_size=2, max_age=86400)
        mgr = SandboxPoolManager(MagicMock(), cfg, AsyncMock())
        t0 = datetime(2026, 4, 22, 0, 0, 0, tzinfo=timezone.utc)

        # Bootstrap retirement deadlines.
        slot0_first = mgr.compute_bootstrap_retire_at(0, now=t0)  # +24h
        slot1_first = mgr.compute_bootstrap_retire_at(1, now=t0)  # +12h

        # When slot 1 is replaced at its first retirement (t0+12h), the new
        # retire_at = (t0+12h) + 24h = t0+36h.
        slot1_second = mgr.compute_replacement_retire_at(now=slot1_first)
        # When slot 0 is replaced at its first retirement (t0+24h), the new
        # retire_at = (t0+24h) + 24h = t0+48h.
        slot0_second = mgr.compute_replacement_retire_at(now=slot0_first)

        # The 12h offset between slot 0 and slot 1 retirements is preserved.
        assert (slot0_second - slot1_second) == timedelta(hours=12)
        assert (slot1_second - slot0_first) == timedelta(hours=12)

    def test_degenerate_pool_size_larger_than_max_age_clamped(self):
        """Stagger never produces a negative retire_at; min 60s."""
        cfg = _make_settings(pool_size=10, max_age=120)  # 12s stagger
        mgr = SandboxPoolManager(MagicMock(), cfg, AsyncMock())
        now = datetime(2026, 4, 22, 12, 0, 0, tzinfo=timezone.utc)
        # Slot 9: 120 - 9*12 = 12s. Clamped to 60.
        retire = mgr.compute_bootstrap_retire_at(9, now=now)
        assert retire >= now + timedelta(seconds=60)


# ─────────────────────────────── enabled gate ────────────────────────────


class TestEnabledGate:
    def test_disabled_when_pool_size_zero(self):
        cfg = _make_settings(pool_size=0)
        mgr = SandboxPoolManager(MagicMock(), cfg, AsyncMock())
        assert mgr.enabled is False

    def test_disabled_when_provider_not_docker(self):
        cfg = _make_settings(enabled=False)
        mgr = SandboxPoolManager(MagicMock(), cfg, AsyncMock())
        assert mgr.enabled is False

    def test_enabled_when_docker_local_size_gt0(self):
        cfg = _make_settings(pool_size=2)
        mgr = SandboxPoolManager(MagicMock(), cfg, AsyncMock())
        assert mgr.enabled is True


# ──────────────────────────────── Bootstrap ──────────────────────────────


class TestBootstrap:
    """All N slots are created in parallel at startup if not in existence."""

    @pytest.mark.asyncio
    async def test_bootstrap_creates_all_slots_when_pool_empty(self):
        cfg = _make_settings(pool_size=3)
        repo = MagicMock()
        repo.list_active_pool_rows = AsyncMock(return_value=[])

        # Stub out _create_slot_async so we can observe scheduling.
        created_slots: list[int] = []

        ctx, mock_db = _patch_db()
        try:
            mgr = SandboxPoolManager(repo, cfg, AsyncMock())

            async def _spy(slot: int, *, is_bootstrap: bool):
                created_slots.append(slot)

            mgr._create_slot_async = _spy  # type: ignore[assignment]

            await mgr.bootstrap()
        finally:
            ctx.stop()

        assert sorted(created_slots) == [0, 1, 2]

    @pytest.mark.asyncio
    async def test_bootstrap_only_fills_missing_slots(self):
        cfg = _make_settings(pool_size=3)
        repo = MagicMock()
        # Slot 1 already exists in AVAILABLE state.
        existing = _make_pool_row(slot=1, state=PoolState.AVAILABLE)
        repo.list_active_pool_rows = AsyncMock(return_value=[existing])

        created_slots: list[int] = []
        ctx, _ = _patch_db()
        try:
            mgr = SandboxPoolManager(repo, cfg, AsyncMock())

            async def _spy(slot: int, *, is_bootstrap: bool):
                created_slots.append(slot)

            mgr._create_slot_async = _spy  # type: ignore[assignment]

            await mgr.bootstrap()
        finally:
            ctx.stop()

        assert sorted(created_slots) == [0, 2]

    @pytest.mark.asyncio
    async def test_bootstrap_noop_when_disabled(self):
        cfg = _make_settings(pool_size=0)
        repo = MagicMock()
        repo.list_active_pool_rows = AsyncMock()
        mgr = SandboxPoolManager(repo, cfg, AsyncMock())
        await mgr.bootstrap()
        repo.list_active_pool_rows.assert_not_called()


# ──────────────────────────────── Claim ──────────────────────────────────


class TestClaim:
    """Claim transitions AVAILABLE -> CLAIMED atomically and triggers replenish."""

    @pytest.mark.asyncio
    async def test_claim_returns_row_and_schedules_replenish(self):
        cfg = _make_settings(pool_size=2)
        repo = MagicMock()
        claimed_row = _make_pool_row(slot=0, state=PoolState.CLAIMED)
        # Repository now returns (row, claimed_slot) and clears row.pool_slot.
        claimed_row.pool_slot = None
        repo.claim_oldest_available = AsyncMock(return_value=(claimed_row, 0))

        mgr = SandboxPoolManager(repo, cfg, AsyncMock())

        replenish_calls: list[int] = []

        async def _spy(slot: int, *, is_bootstrap: bool):
            replenish_calls.append(slot)

        mgr._create_slot_async = _spy  # type: ignore[assignment]

        session_id = uuid.uuid4()
        db = AsyncMock()
        result = await mgr.claim(db, session_id)

        # Let the scheduled task run.
        await asyncio.sleep(0)

        assert result is claimed_row
        repo.claim_oldest_available.assert_awaited_once_with(db, session_id)
        assert replenish_calls == [0]

    @pytest.mark.asyncio
    async def test_claim_returns_none_when_pool_empty(self):
        cfg = _make_settings(pool_size=2)
        repo = MagicMock()
        repo.claim_oldest_available = AsyncMock(return_value=(None, None))

        mgr = SandboxPoolManager(repo, cfg, AsyncMock())

        called: list[int] = []

        async def _spy(slot: int, *, is_bootstrap: bool):
            called.append(slot)

        mgr._create_slot_async = _spy  # type: ignore[assignment]

        result = await mgr.claim(AsyncMock(), uuid.uuid4())
        await asyncio.sleep(0)

        assert result is None
        assert called == []  # no replenish triggered when nothing to replace

    @pytest.mark.asyncio
    async def test_claim_noop_when_disabled(self):
        cfg = _make_settings(pool_size=0)
        repo = MagicMock()
        repo.claim_oldest_available = AsyncMock()

        mgr = SandboxPoolManager(repo, cfg, AsyncMock())
        result = await mgr.claim(AsyncMock(), uuid.uuid4())

        assert result is None
        repo.claim_oldest_available.assert_not_called()


# ──────────────────────────── Retirement ─────────────────────────────────


class TestRetirement:
    """Past-due AVAILABLE rows get marked RETIRING."""

    @pytest.mark.asyncio
    async def test_mark_due_for_retirement_marks_each_due_row(self):
        cfg = _make_settings(pool_size=2)
        past = datetime.now(timezone.utc) - timedelta(seconds=10)
        due_rows = [
            _make_pool_row(slot=0, retire_at=past),
            _make_pool_row(slot=1, retire_at=past),
        ]
        repo = MagicMock()
        repo.list_due_for_retirement = AsyncMock(return_value=due_rows)

        ctx, mock_db = _patch_db()
        try:
            mgr = SandboxPoolManager(repo, cfg, AsyncMock())
            count = await mgr.mark_due_for_retirement()
        finally:
            ctx.stop()

        assert count == 2
        for row in due_rows:
            assert row.pool_state == PoolState.RETIRING
        mock_db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_mark_due_for_retirement_noop_when_no_rows_due(self):
        cfg = _make_settings(pool_size=2)
        repo = MagicMock()
        repo.list_due_for_retirement = AsyncMock(return_value=[])

        ctx, mock_db = _patch_db()
        try:
            mgr = SandboxPoolManager(repo, cfg, AsyncMock())
            count = await mgr.mark_due_for_retirement()
        finally:
            ctx.stop()

        assert count == 0
        mock_db.commit.assert_not_awaited()


# ──────────────────────── ensure_full / replenish ASAP ───────────────────


class TestEnsureFull:
    """Missing slots get re-created as soon as the next sweep runs."""

    @pytest.mark.asyncio
    async def test_ensure_full_recreates_missing_slots(self):
        cfg = _make_settings(pool_size=3)
        # Only slot 1 is alive; 0 and 2 are missing.
        existing = _make_pool_row(slot=1, state=PoolState.AVAILABLE)
        repo = MagicMock()
        repo.list_active_pool_rows = AsyncMock(return_value=[existing])

        scheduled: list[tuple[int, bool]] = []

        ctx, _ = _patch_db()
        try:
            mgr = SandboxPoolManager(repo, cfg, AsyncMock())

            async def _spy(slot: int, *, is_bootstrap: bool):
                scheduled.append((slot, is_bootstrap))

            mgr._create_slot_async = _spy  # type: ignore[assignment]
            await mgr.ensure_full()
            # Drain the scheduled tasks.
            await asyncio.sleep(0)
        finally:
            ctx.stop()

        # ensure_full schedules slots 0 and 2 (not 1) as replacements.
        assert sorted(scheduled) == [(0, False), (2, False)]

    @pytest.mark.asyncio
    async def test_ensure_full_treats_retiring_slots_as_occupied(self):
        """RETIRING rows still hold their slot until the cleanup loop kills them."""
        cfg = _make_settings(pool_size=2)
        retiring = _make_pool_row(slot=0, state=PoolState.RETIRING)
        repo = MagicMock()
        repo.list_active_pool_rows = AsyncMock(return_value=[retiring])

        scheduled: list[int] = []
        ctx, _ = _patch_db()
        try:
            mgr = SandboxPoolManager(repo, cfg, AsyncMock())

            async def _spy(slot: int, *, is_bootstrap: bool):
                scheduled.append(slot)

            mgr._create_slot_async = _spy  # type: ignore[assignment]
            await mgr.ensure_full()
            await asyncio.sleep(0)
        finally:
            ctx.stop()

        # Only slot 1 is missing; slot 0 is retiring (still occupies it).
        assert scheduled == [1]


# ──────────────────────────── Concurrency ────────────────────────────────


class TestCreateConcurrency:
    """Concurrent creates for the same slot are de-duplicated."""

    @pytest.mark.asyncio
    async def test_duplicate_slot_create_skipped(self):
        cfg = _make_settings(pool_size=2)
        repo = MagicMock()
        repo.save = AsyncMock(side_effect=lambda db, row: row)
        repo.update_status = AsyncMock()
        repo.update_provider_info = AsyncMock()

        # Track how many times the provider create runs.
        create_calls: list[uuid.UUID] = []

        async def _slow_create(sandbox_id, session_placeholder):
            create_calls.append(sandbox_id)
            await asyncio.sleep(0.05)
            return _make_sandbox_mgr()

        ctx, _ = _patch_db()
        try:
            mgr = SandboxPoolManager(repo, cfg, _slow_create)

            # Fire two concurrent creates for slot 0.
            await asyncio.gather(
                mgr._create_slot_async(0, is_bootstrap=True),
                mgr._create_slot_async(0, is_bootstrap=True),
            )
        finally:
            ctx.stop()

        assert len(create_calls) == 1


# ──────────────────────── Error containment ──────────────────────────────


class TestErrorContainment:
    """Provider failures must not propagate to the caller."""

    @pytest.mark.asyncio
    async def test_provider_create_failure_marks_row_deleted(self):
        cfg = _make_settings(pool_size=2)
        saved_rows: list[AgentSandbox] = []

        async def _save(db, row):
            row.id = uuid.uuid4()
            saved_rows.append(row)
            return row

        repo = MagicMock()
        repo.save = AsyncMock(side_effect=_save)
        repo.update_status = AsyncMock()
        repo.update_provider_info = AsyncMock()

        async def _failing_create(sandbox_id, session_placeholder):
            raise SandboxCreationError("docker hates us today")

        ctx, _ = _patch_db()
        try:
            mgr = SandboxPoolManager(repo, cfg, _failing_create)
            # Should not raise.
            await mgr._create_slot_async(0, is_bootstrap=True)
        finally:
            ctx.stop()

        assert len(saved_rows) == 1
        # Failed row was marked DELETED so future ensure_full retries it.
        called_args = repo.update_status.await_args
        assert called_args is not None
        assert called_args.args[1] == saved_rows[0].id
        assert called_args.args[2] == SandboxStatus.DELETED


# ─────────────────────────── do_create_slot path ─────────────────────────


class TestDoCreateSlot:
    """The full create flow: insert row → call provider → persist state."""

    @pytest.mark.asyncio
    async def test_successful_create_persists_provider_info(self):
        cfg = _make_settings(pool_size=2)

        async def _save(db, row):
            row.id = uuid.uuid4()
            return row

        repo = MagicMock()
        repo.save = AsyncMock(side_effect=_save)
        repo.update_status = AsyncMock()
        repo.update_provider_info = AsyncMock()

        mock_mgr = _make_sandbox_mgr(provider_sandbox_id="ctr-123")

        async def _create(sandbox_id, session_placeholder):
            assert session_placeholder == SandboxPoolManager.POOL_SESSION_PLACEHOLDER
            return mock_mgr

        ctx, _ = _patch_db()
        try:
            mgr = SandboxPoolManager(repo, cfg, _create)
            await mgr._do_create_slot(0, is_bootstrap=True)
        finally:
            ctx.stop()

        repo.save.assert_awaited()
        repo.update_provider_info.assert_awaited_once()
        kwargs = repo.update_provider_info.await_args.kwargs
        assert kwargs["status"] == SandboxStatus.RUNNING
        assert kwargs["provider_sandbox_id"] == "ctr-123"

    @pytest.mark.asyncio
    async def test_bootstrap_uses_staggered_retire_at(self):
        """Slot 1 with N=2 gets the 12h-offset retire_at, not full 24h."""
        cfg = _make_settings(pool_size=2, max_age=86400)
        captured: list[AgentSandbox] = []

        async def _save(db, row):
            row.id = uuid.uuid4()
            captured.append(row)
            return row

        repo = MagicMock()
        repo.save = AsyncMock(side_effect=_save)
        repo.update_status = AsyncMock()
        repo.update_provider_info = AsyncMock()

        async def _create(sandbox_id, session_placeholder):
            return _make_sandbox_mgr()

        ctx, _ = _patch_db()
        try:
            mgr = SandboxPoolManager(repo, cfg, _create)
            await mgr._do_create_slot(1, is_bootstrap=True)
        finally:
            ctx.stop()

        assert len(captured) == 1
        row = captured[0]
        assert row.pool_slot == 1
        # retire_at should be roughly +12h (43200s), not +24h.
        delta = row.retire_at - datetime.now(timezone.utc)
        assert timedelta(hours=11, minutes=58) < delta < timedelta(hours=12, minutes=2)

    @pytest.mark.asyncio
    async def test_replacement_uses_full_max_age(self):
        cfg = _make_settings(pool_size=2, max_age=86400)
        captured: list[AgentSandbox] = []

        async def _save(db, row):
            row.id = uuid.uuid4()
            captured.append(row)
            return row

        repo = MagicMock()
        repo.save = AsyncMock(side_effect=_save)
        repo.update_status = AsyncMock()
        repo.update_provider_info = AsyncMock()

        async def _create(sandbox_id, session_placeholder):
            return _make_sandbox_mgr()

        ctx, _ = _patch_db()
        try:
            mgr = SandboxPoolManager(repo, cfg, _create)
            # Replacement for slot 1: should still get +24h regardless of slot.
            await mgr._do_create_slot(1, is_bootstrap=False)
        finally:
            ctx.stop()

        delta = captured[0].retire_at - datetime.now(timezone.utc)
        assert timedelta(hours=23, minutes=58) < delta < timedelta(hours=24, minutes=2)


# ───────────────── Stuck-INITIALIZING reap (Fix A) ───────────────────────


class TestReapStuckInitializing:
    """Cover the recovery path for AVAILABLE rows wedged in INITIALIZING.

    Failure mode (the bug this guards against): a previous backend run
    inserted a pool row at INITIALIZING and crashed before reaching
    status=RUNNING. The row survives forever because every cleanup path
    skips it (orphan cleanup ignores AVAILABLE pool rows, the docker-zombie
    sweep needs a provider_sandbox_id, stale-pause needs a session_id).
    bootstrap then logs "all slots already populated" and the pool stays
    empty.
    """

    @pytest.mark.asyncio
    async def test_reap_marks_stuck_no_provider_id_row_deleted(self):
        """Crashed before container create: row has no provider_sandbox_id."""
        cfg = _make_settings(pool_size=2)
        old = datetime.now(timezone.utc) - timedelta(hours=11)
        stuck = _make_pool_row(
            slot=0,
            state=PoolState.AVAILABLE,
            status=SandboxStatus.INITIALIZING,
            provider_sandbox_id=None,
            created_at=old,
        )
        repo = MagicMock()
        repo.list_active_pool_rows = AsyncMock(return_value=[stuck])

        ctx, mock_db = _patch_db()
        try:
            mgr = SandboxPoolManager(repo, cfg, AsyncMock())
            reaped = await mgr.reap_stuck_initializing()
        finally:
            ctx.stop()

        assert reaped == 1
        assert stuck.status == SandboxStatus.DELETED
        mock_db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_reap_marks_stuck_with_provider_id_row_deleted(self):
        """Crashed *after* container create: row carries provider_sandbox_id.

        The orphan container is then a true zombie reaped by the existing
        Docker-zombie sweep on its next pass.
        """
        cfg = _make_settings(pool_size=2)
        old = datetime.now(timezone.utc) - timedelta(minutes=30)
        stuck = _make_pool_row(
            slot=1,
            state=PoolState.AVAILABLE,
            status=SandboxStatus.INITIALIZING,
            provider_sandbox_id="ctr-leaked",
            created_at=old,
        )
        repo = MagicMock()
        repo.list_active_pool_rows = AsyncMock(return_value=[stuck])

        ctx, _ = _patch_db()
        try:
            mgr = SandboxPoolManager(repo, cfg, AsyncMock())
            reaped = await mgr.reap_stuck_initializing()
        finally:
            ctx.stop()

        assert reaped == 1
        assert stuck.status == SandboxStatus.DELETED

    @pytest.mark.asyncio
    async def test_reap_skips_recent_initializing_row(self):
        """Genuine in-flight provisioning must not be reaped."""
        cfg = _make_settings(pool_size=2)
        recent = datetime.now(timezone.utc) - timedelta(seconds=30)
        in_flight = _make_pool_row(
            slot=0,
            state=PoolState.AVAILABLE,
            status=SandboxStatus.INITIALIZING,
            provider_sandbox_id=None,
            created_at=recent,
        )
        repo = MagicMock()
        repo.list_active_pool_rows = AsyncMock(return_value=[in_flight])

        ctx, mock_db = _patch_db()
        try:
            mgr = SandboxPoolManager(repo, cfg, AsyncMock())
            reaped = await mgr.reap_stuck_initializing()
        finally:
            ctx.stop()

        assert reaped == 0
        assert in_flight.status == SandboxStatus.INITIALIZING
        mock_db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_reap_ignores_running_and_claimed_and_retiring(self):
        """Only AVAILABLE+INITIALIZING is in scope. Other states are owned
        by other lifecycle paths."""
        cfg = _make_settings(pool_size=4)
        old = datetime.now(timezone.utc) - timedelta(hours=3)
        rows = [
            _make_pool_row(
                slot=0, state=PoolState.AVAILABLE, status=SandboxStatus.RUNNING, created_at=old
            ),
            _make_pool_row(
                slot=1, state=PoolState.CLAIMED, status=SandboxStatus.INITIALIZING, created_at=old
            ),
            _make_pool_row(
                slot=2, state=PoolState.RETIRING, status=SandboxStatus.INITIALIZING, created_at=old
            ),
        ]
        repo = MagicMock()
        repo.list_active_pool_rows = AsyncMock(return_value=rows)

        ctx, mock_db = _patch_db()
        try:
            mgr = SandboxPoolManager(repo, cfg, AsyncMock())
            reaped = await mgr.reap_stuck_initializing()
        finally:
            ctx.stop()

        assert reaped == 0
        for row in rows:
            assert row.status != SandboxStatus.DELETED
        mock_db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_reap_noop_when_disabled(self):
        cfg = _make_settings(pool_size=0)
        repo = MagicMock()
        repo.list_active_pool_rows = AsyncMock()
        mgr = SandboxPoolManager(repo, cfg, AsyncMock())
        assert await mgr.reap_stuck_initializing() == 0
        repo.list_active_pool_rows.assert_not_called()


class TestExistingLiveSlotsStatusFilter:
    """_existing_live_slots must NOT count stuck INITIALIZING rows as live.

    Without this filter, the bootstrap "phantom standby" bug recurs: a
    row left over from a crashed previous backend run takes the slot
    forever even though no container backs it.
    """

    @pytest.mark.asyncio
    async def test_running_available_row_is_live(self):
        cfg = _make_settings(pool_size=2)
        row = _make_pool_row(slot=0, state=PoolState.AVAILABLE, status=SandboxStatus.RUNNING)
        repo = MagicMock()
        repo.list_active_pool_rows = AsyncMock(return_value=[row])
        ctx, _ = _patch_db()
        try:
            mgr = SandboxPoolManager(repo, cfg, AsyncMock())
            live = await mgr._existing_live_slots()
        finally:
            ctx.stop()
        assert live == {0}

    @pytest.mark.asyncio
    async def test_recent_initializing_available_row_is_live(self):
        cfg = _make_settings(pool_size=2)
        recent = datetime.now(timezone.utc) - timedelta(seconds=30)
        row = _make_pool_row(
            slot=0,
            state=PoolState.AVAILABLE,
            status=SandboxStatus.INITIALIZING,
            created_at=recent,
        )
        repo = MagicMock()
        repo.list_active_pool_rows = AsyncMock(return_value=[row])
        ctx, _ = _patch_db()
        try:
            mgr = SandboxPoolManager(repo, cfg, AsyncMock())
            live = await mgr._existing_live_slots()
        finally:
            ctx.stop()
        assert live == {0}

    @pytest.mark.asyncio
    async def test_old_initializing_available_row_is_not_live(self):
        cfg = _make_settings(pool_size=2)
        old = datetime.now(timezone.utc) - timedelta(hours=2)
        row = _make_pool_row(
            slot=0,
            state=PoolState.AVAILABLE,
            status=SandboxStatus.INITIALIZING,
            created_at=old,
        )
        repo = MagicMock()
        repo.list_active_pool_rows = AsyncMock(return_value=[row])
        ctx, _ = _patch_db()
        try:
            mgr = SandboxPoolManager(repo, cfg, AsyncMock())
            live = await mgr._existing_live_slots()
        finally:
            ctx.stop()
        # The whole point of Fix A: stuck rows do NOT occupy the slot.
        assert live == set()

    @pytest.mark.asyncio
    async def test_claimed_and_retiring_rows_always_live(self):
        cfg = _make_settings(pool_size=3)
        old = datetime.now(timezone.utc) - timedelta(hours=2)
        rows = [
            _make_pool_row(
                slot=0, state=PoolState.CLAIMED, status=SandboxStatus.RUNNING, created_at=old
            ),
            _make_pool_row(
                slot=1, state=PoolState.RETIRING, status=SandboxStatus.RUNNING, created_at=old
            ),
            # Edge: CLAIMED but somehow still INITIALIZING (race window)
            # — the session owns it now, we don't recreate the slot.
            _make_pool_row(
                slot=2, state=PoolState.CLAIMED, status=SandboxStatus.INITIALIZING, created_at=old
            ),
        ]
        repo = MagicMock()
        repo.list_active_pool_rows = AsyncMock(return_value=rows)
        ctx, _ = _patch_db()
        try:
            mgr = SandboxPoolManager(repo, cfg, AsyncMock())
            live = await mgr._existing_live_slots()
        finally:
            ctx.stop()
        assert live == {0, 1, 2}


class TestBootstrapReapsStuckRowsBeforeEnumeration:
    """End-to-end: bootstrap must reap-then-enumerate, otherwise the
    phantom standby bug returns."""

    @pytest.mark.asyncio
    async def test_bootstrap_recreates_slot_when_only_stuck_row_exists(self):
        cfg = _make_settings(pool_size=2)
        old = datetime.now(timezone.utc) - timedelta(hours=11)
        # Two zombie rows from a crashed previous run — the exact shape
        # of the live host bug as observed on 2026-04-23.
        zombies = [
            _make_pool_row(
                slot=0,
                state=PoolState.AVAILABLE,
                status=SandboxStatus.INITIALIZING,
                provider_sandbox_id=None,
                created_at=old,
            ),
            _make_pool_row(
                slot=1,
                state=PoolState.AVAILABLE,
                status=SandboxStatus.INITIALIZING,
                provider_sandbox_id=None,
                created_at=old,
            ),
        ]
        repo = MagicMock()
        repo.list_active_pool_rows = AsyncMock(return_value=zombies)

        scheduled: list[int] = []
        ctx, _ = _patch_db()
        try:
            mgr = SandboxPoolManager(repo, cfg, AsyncMock())

            async def _spy(slot: int, *, is_bootstrap: bool):
                scheduled.append(slot)

            mgr._create_slot_async = _spy  # type: ignore[assignment]
            await mgr.bootstrap()
        finally:
            ctx.stop()

        # Both zombie rows should be marked DELETED and both slots
        # should have been re-scheduled for creation.
        assert sorted(scheduled) == [0, 1]
        for row in zombies:
            assert row.status == SandboxStatus.DELETED


class TestSnapshot:
    """SandboxPoolManager.snapshot() shape contract.

    Used by the ``/health/sandbox-pool`` endpoint and
    ``platform_checks_pool.sh``. Must always return a JSON-friendly
    dict with the documented keys, even when degraded.
    """

    @pytest.mark.asyncio
    async def test_snapshot_disabled_pool_returns_zeros(self):
        cfg = _make_settings(pool_size=0)
        repo = MagicMock()
        repo.list_active_pool_rows = AsyncMock(return_value=[])
        mgr = SandboxPoolManager(repo, cfg, AsyncMock())

        snap = await mgr.snapshot()

        assert snap["enabled"] is False
        assert snap["configured"] == 0
        assert snap["ready"] == 0
        assert snap["initializing"] == 0
        assert snap["claimed"] == 0
        assert snap["retiring"] == 0

    @pytest.mark.asyncio
    async def test_snapshot_counts_rows_by_state_and_status(self):
        cfg = _make_settings(pool_size=2)
        now = datetime.now(timezone.utc)
        rows = [
            _make_pool_row(
                slot=0,
                state=PoolState.AVAILABLE,
                status=SandboxStatus.RUNNING,
                created_at=now - timedelta(minutes=5),
            ),
            _make_pool_row(
                slot=1,
                state=PoolState.AVAILABLE,
                status=SandboxStatus.INITIALIZING,
                created_at=now - timedelta(seconds=30),
            ),
            _make_pool_row(
                slot=0,
                state=PoolState.CLAIMED,
                status=SandboxStatus.RUNNING,
                created_at=now - timedelta(hours=1),
            ),
            _make_pool_row(
                slot=1,
                state=PoolState.RETIRING,
                status=SandboxStatus.RUNNING,
                created_at=now - timedelta(hours=2),
            ),
        ]
        repo = MagicMock()
        repo.list_active_pool_rows = AsyncMock(return_value=rows)

        ctx, _ = _patch_db()
        try:
            mgr = SandboxPoolManager(repo, cfg, AsyncMock())
            snap = await mgr.snapshot()
        finally:
            ctx.stop()

        assert snap["enabled"] is True
        assert snap["configured"] == 2
        assert snap["ready"] == 1
        assert snap["initializing"] == 1
        assert snap["claimed"] == 1
        assert snap["retiring"] == 1
        assert snap["stuck_initializing"] == 0
        assert snap["initializing_age_max_seconds"] is not None
        assert 25 <= snap["initializing_age_max_seconds"] <= 60
        assert snap["stuck_threshold_seconds"] == 600

    @pytest.mark.asyncio
    async def test_snapshot_flags_stuck_initializing_rows(self):
        cfg = _make_settings(pool_size=2)
        now = datetime.now(timezone.utc)
        rows = [
            _make_pool_row(
                slot=0,
                state=PoolState.AVAILABLE,
                status=SandboxStatus.INITIALIZING,
                created_at=now - timedelta(hours=11),
            ),
        ]
        repo = MagicMock()
        repo.list_active_pool_rows = AsyncMock(return_value=rows)

        ctx, _ = _patch_db()
        try:
            mgr = SandboxPoolManager(repo, cfg, AsyncMock())
            snap = await mgr.snapshot()
        finally:
            ctx.stop()

        assert snap["initializing"] == 1
        assert snap["stuck_initializing"] == 1
        assert snap["initializing_age_max_seconds"] >= 11 * 3600 - 5
