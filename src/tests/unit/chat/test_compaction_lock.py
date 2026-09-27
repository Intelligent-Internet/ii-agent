"""Tests for ii_agent.chat.application.compaction_lock."""

from __future__ import annotations

import asyncio
import uuid

import pytest

from ii_agent.chat.application.compaction_lock import (
    _get_lock,
    _locks,
    compaction_lock,
    is_compaction_locked,
    remove_session_lock,
)


@pytest.fixture(autouse=True)
def _clear_locks():
    """Ensure lock registry is empty before and after each test."""
    _locks.clear()
    yield
    _locks.clear()


class TestGetLock:
    def test_creates_lock_on_first_call(self):
        sid = uuid.uuid4()
        lock = _get_lock(sid)
        assert isinstance(lock, asyncio.Lock)
        assert sid in _locks

    def test_returns_same_lock_for_same_session(self):
        sid = uuid.uuid4()
        assert _get_lock(sid) is _get_lock(sid)

    def test_different_sessions_get_different_locks(self):
        sid1, sid2 = uuid.uuid4(), uuid.uuid4()
        assert _get_lock(sid1) is not _get_lock(sid2)


class TestCompactionLock:
    @pytest.mark.asyncio
    async def test_lock_is_held_inside_context(self):
        sid = uuid.uuid4()
        async with compaction_lock(sid):
            assert is_compaction_locked(sid)
        assert not is_compaction_locked(sid)

    @pytest.mark.asyncio
    async def test_concurrent_acquires_are_serialized(self):
        sid = uuid.uuid4()
        order: list[int] = []

        async def _worker(n: int):
            async with compaction_lock(sid):
                order.append(n)
                await asyncio.sleep(0)  # yield so other tasks can check the lock

        await asyncio.gather(_worker(1), _worker(2))
        assert len(order) == 2


class TestIsCompactionLocked:
    def test_returns_false_for_unknown_session(self):
        assert is_compaction_locked(uuid.uuid4()) is False

    @pytest.mark.asyncio
    async def test_returns_true_when_lock_held(self):
        sid = uuid.uuid4()
        lock = _get_lock(sid)
        await lock.acquire()
        try:
            assert is_compaction_locked(sid) is True
        finally:
            lock.release()

    @pytest.mark.asyncio
    async def test_returns_false_after_release(self):
        sid = uuid.uuid4()
        async with compaction_lock(sid):
            pass
        assert is_compaction_locked(sid) is False


class TestRemoveSessionLock:
    def test_removes_existing_lock(self):
        sid = uuid.uuid4()
        _get_lock(sid)
        assert sid in _locks
        remove_session_lock(sid)
        assert sid not in _locks

    def test_noop_for_unknown_session(self):
        remove_session_lock(uuid.uuid4())  # should not raise
