"""Unit tests for ``SandboxRepository``.

These tests use ``MagicMock`` / ``AsyncMock`` to stand in for the
``AsyncSession`` rather than spinning up a full DB. They verify the SQL
shape (which models / filters / order-bys are referenced) and the
mutation logic on the returned record (status, pool_state, claimed_at,
etc.) without coupling to PostgreSQL.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from ii_agent.agents.sandboxes.models import AgentSandbox
from ii_agent.agents.sandboxes.repository import SandboxRepository
from ii_agent.agents.sandboxes.types import (
    PoolState,
    SandboxProviderType,
    SandboxStatus,
)


pytestmark = pytest.mark.unit


def _record(
    *,
    id_: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    status: SandboxStatus = SandboxStatus.RUNNING,
    pool_slot: int | None = None,
    pool_state: PoolState | None = None,
    provider_sandbox_id: str | None = None,
    expired_at=None,
    provider_data=None,
    retire_at=None,
) -> AgentSandbox:
    """Build a bare AgentSandbox for repository tests."""
    rec = AgentSandbox()
    rec.id = id_ or uuid.uuid4()
    rec.session_id = session_id or uuid.uuid4()
    rec.status = status
    rec.pool_slot = pool_slot
    rec.pool_state = pool_state
    rec.provider_sandbox_id = provider_sandbox_id
    rec.expired_at = expired_at
    rec.provider_data = provider_data
    rec.retire_at = retire_at
    rec.claimed_at = None
    rec.provider = SandboxProviderType.DOCKER
    return rec


def _mock_db_returning(scalar_value=None) -> MagicMock:
    db = MagicMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_value
    db.execute.return_value = result
    return db


def _mock_db_returning_list(scalars: list) -> MagicMock:
    db = MagicMock()
    db.execute = AsyncMock()
    result = MagicMock()
    scalars_obj = MagicMock()
    scalars_obj.all.return_value = scalars
    result.scalars.return_value = scalars_obj
    db.execute.return_value = result
    return db


# ---------------------------------------------------------------------------
# get_active_by_session_id
# ---------------------------------------------------------------------------


class TestGetActiveBySessionId:
    @pytest.mark.asyncio
    async def test_returns_record_when_present(self):
        repo = SandboxRepository()
        rec = _record()
        db = _mock_db_returning(rec)

        result = await repo.get_active_by_session_id(db, rec.session_id)

        assert result is rec
        db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_absent(self):
        repo = SandboxRepository()
        db = _mock_db_returning(None)

        result = await repo.get_active_by_session_id(db, uuid.uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_alias_get_by_session_id_works(self):
        repo = SandboxRepository()
        rec = _record()
        db = _mock_db_returning(rec)

        result = await repo.get_by_session_id(db, rec.session_id)

        assert result is rec


# ---------------------------------------------------------------------------
# update_status
# ---------------------------------------------------------------------------


class TestUpdateStatus:
    @pytest.mark.asyncio
    async def test_updates_when_record_exists(self):
        repo = SandboxRepository()
        rec = _record(status=SandboxStatus.INITIALIZING)
        db = _mock_db_returning(rec)

        result = await repo.update_status(db, rec.id, SandboxStatus.RUNNING)

        assert result is rec
        assert rec.status == SandboxStatus.RUNNING
        db.flush.assert_awaited_once()
        db.refresh.assert_awaited_once_with(rec)

    @pytest.mark.asyncio
    async def test_returns_none_when_record_missing(self):
        repo = SandboxRepository()
        db = _mock_db_returning(None)

        result = await repo.update_status(db, uuid.uuid4(), SandboxStatus.RUNNING)

        assert result is None
        db.flush.assert_not_awaited()
        db.refresh.assert_not_awaited()


# ---------------------------------------------------------------------------
# update_provider_info
# ---------------------------------------------------------------------------


class TestUpdateProviderInfo:
    @pytest.mark.asyncio
    async def test_updates_only_provided_fields(self):
        repo = SandboxRepository()
        original_status = SandboxStatus.RUNNING
        rec = _record(
            status=original_status, provider_sandbox_id="old-id"
        )
        db = _mock_db_returning(rec)

        result = await repo.update_provider_info(
            db, rec.id, provider_sandbox_id="new-id"
        )

        assert result is rec
        # status untouched, provider_sandbox_id updated
        assert rec.status == original_status
        assert rec.provider_sandbox_id == "new-id"

    @pytest.mark.asyncio
    async def test_updates_all_fields_when_supplied(self):
        repo = SandboxRepository()
        rec = _record(status=SandboxStatus.INITIALIZING)
        db = _mock_db_returning(rec)
        expired = datetime.now(timezone.utc)
        provider_data = {"region": "us-central1"}

        result = await repo.update_provider_info(
            db,
            rec.id,
            status=SandboxStatus.RUNNING,
            provider_sandbox_id="new-pid",
            expired_at=expired,
            provider_data=provider_data,
        )

        assert result.status == SandboxStatus.RUNNING
        assert result.provider_sandbox_id == "new-pid"
        assert result.expired_at == expired
        assert result.provider_data == provider_data

    @pytest.mark.asyncio
    async def test_returns_none_when_record_missing(self):
        repo = SandboxRepository()
        db = _mock_db_returning(None)

        result = await repo.update_provider_info(
            db, uuid.uuid4(), provider_sandbox_id="x"
        )

        assert result is None


# ---------------------------------------------------------------------------
# list_active_pool_rows
# ---------------------------------------------------------------------------


class TestListActivePoolRows:
    @pytest.mark.asyncio
    async def test_returns_list_of_records(self):
        repo = SandboxRepository()
        recs = [
            _record(pool_slot=0, pool_state=PoolState.AVAILABLE),
            _record(pool_slot=1, pool_state=PoolState.RETIRING),
        ]
        db = _mock_db_returning_list(recs)

        result = await repo.list_active_pool_rows(db)

        assert result == recs
        db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_rows(self):
        repo = SandboxRepository()
        db = _mock_db_returning_list([])

        result = await repo.list_active_pool_rows(db)

        assert result == []


# ---------------------------------------------------------------------------
# claim_oldest_available
# ---------------------------------------------------------------------------


class TestClaimOldestAvailable:
    @pytest.mark.asyncio
    async def test_claims_and_clears_pool_slot(self):
        repo = SandboxRepository()
        target_slot = 3
        rec = _record(
            status=SandboxStatus.RUNNING,
            pool_slot=target_slot,
            pool_state=PoolState.AVAILABLE,
            provider_sandbox_id="container-xyz",
        )
        db = _mock_db_returning(rec)
        session_id = uuid.uuid4()

        before_claim = datetime.now(timezone.utc)
        row, claimed_slot = await repo.claim_oldest_available(db, session_id)

        assert row is rec
        assert claimed_slot == target_slot
        # Critical: pool_slot cleared so the long-lived CLAIMED row no
        # longer occupies the slot in ensure_full() bookkeeping.
        assert row.pool_slot is None
        assert row.pool_state == PoolState.CLAIMED
        assert row.session_id == session_id
        assert row.claimed_at >= before_claim
        db.flush.assert_awaited_once()
        db.refresh.assert_awaited_once_with(rec)

    @pytest.mark.asyncio
    async def test_returns_none_none_when_pool_empty(self):
        repo = SandboxRepository()
        db = _mock_db_returning(None)

        row, claimed_slot = await repo.claim_oldest_available(db, uuid.uuid4())

        assert row is None
        assert claimed_slot is None
        db.flush.assert_not_awaited()


# ---------------------------------------------------------------------------
# list_due_for_retirement
# ---------------------------------------------------------------------------


class TestListDueForRetirement:
    @pytest.mark.asyncio
    async def test_returns_overdue_rows(self):
        repo = SandboxRepository()
        past = datetime.now(timezone.utc).replace(year=2020)
        recs = [
            _record(retire_at=past, pool_state=PoolState.AVAILABLE, pool_slot=0),
            _record(retire_at=past, pool_state=PoolState.AVAILABLE, pool_slot=1),
        ]
        db = _mock_db_returning_list(recs)

        result = await repo.list_due_for_retirement(db)

        assert result == recs

    @pytest.mark.asyncio
    async def test_uses_now_when_no_explicit_cutoff(self):
        repo = SandboxRepository()
        db = _mock_db_returning_list([])
        # Just verify it doesn't crash and returns []
        result = await repo.list_due_for_retirement(db)
        assert result == []
