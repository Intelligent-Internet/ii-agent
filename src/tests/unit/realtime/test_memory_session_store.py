"""Tests for ii_agent.realtime.session_store (MemorySessionStore + create_session_store)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.realtime.session_store import MemorySessionStore


# ---------------------------------------------------------------------------
# MemorySessionStore — add_sid_to_session
# ---------------------------------------------------------------------------


class TestMemorySessionStoreAddSid:
    @pytest.mark.asyncio
    async def test_add_single_sid(self):
        store = MemorySessionStore()
        await store.add_sid_to_session("session-1", "sid-A")
        sids = await store.get_session_sids("session-1")
        assert "sid-A" in sids

    @pytest.mark.asyncio
    async def test_add_multiple_sids_same_session(self):
        store = MemorySessionStore()
        await store.add_sid_to_session("session-1", "sid-A")
        await store.add_sid_to_session("session-1", "sid-B")
        sids = await store.get_session_sids("session-1")
        assert sids == {"sid-A", "sid-B"}

    @pytest.mark.asyncio
    async def test_add_same_sid_twice_is_idempotent(self):
        store = MemorySessionStore()
        await store.add_sid_to_session("session-1", "sid-A")
        await store.add_sid_to_session("session-1", "sid-A")
        sids = await store.get_session_sids("session-1")
        assert sids == {"sid-A"}

    @pytest.mark.asyncio
    async def test_add_sids_to_different_sessions(self):
        store = MemorySessionStore()
        await store.add_sid_to_session("session-1", "sid-A")
        await store.add_sid_to_session("session-2", "sid-B")
        assert "sid-A" in await store.get_session_sids("session-1")
        assert "sid-B" in await store.get_session_sids("session-2")
        assert "sid-B" not in await store.get_session_sids("session-1")


# ---------------------------------------------------------------------------
# MemorySessionStore — remove_sid_from_session
# ---------------------------------------------------------------------------


class TestMemorySessionStoreRemoveSid:
    @pytest.mark.asyncio
    async def test_remove_existing_sid(self):
        store = MemorySessionStore()
        await store.add_sid_to_session("session-1", "sid-A")
        await store.remove_sid_from_session("session-1", "sid-A")
        sids = await store.get_session_sids("session-1")
        assert "sid-A" not in sids

    @pytest.mark.asyncio
    async def test_remove_cleans_up_empty_session(self):
        store = MemorySessionStore()
        await store.add_sid_to_session("session-1", "sid-A")
        await store.remove_sid_from_session("session-1", "sid-A")
        assert "session-1" not in store._sessions

    @pytest.mark.asyncio
    async def test_remove_one_leaves_others(self):
        store = MemorySessionStore()
        await store.add_sid_to_session("sess", "sid-A")
        await store.add_sid_to_session("sess", "sid-B")
        await store.remove_sid_from_session("sess", "sid-A")
        sids = await store.get_session_sids("sess")
        assert sids == {"sid-B"}

    @pytest.mark.asyncio
    async def test_remove_nonexistent_sid_is_safe(self):
        store = MemorySessionStore()
        await store.add_sid_to_session("session-1", "sid-A")
        # Should not raise
        await store.remove_sid_from_session("session-1", "nonexistent-sid")

    @pytest.mark.asyncio
    async def test_remove_from_nonexistent_session_is_safe(self):
        store = MemorySessionStore()
        # Should not raise
        await store.remove_sid_from_session("does-not-exist", "sid-A")


# ---------------------------------------------------------------------------
# MemorySessionStore — get_session_sids
# ---------------------------------------------------------------------------


class TestMemorySessionStoreGetSids:
    @pytest.mark.asyncio
    async def test_returns_copy_not_reference(self):
        store = MemorySessionStore()
        await store.add_sid_to_session("sess", "sid-A")
        sids = await store.get_session_sids("sess")
        sids.add("MUTATED")
        internal = await store.get_session_sids("sess")
        assert "MUTATED" not in internal

    @pytest.mark.asyncio
    async def test_unknown_session_returns_empty_set(self):
        store = MemorySessionStore()
        sids = await store.get_session_sids("unknown")
        assert sids == set()


# ---------------------------------------------------------------------------
# MemorySessionStore — get_all_session_sids
# ---------------------------------------------------------------------------


class TestMemorySessionStoreGetAllSids:
    @pytest.mark.asyncio
    async def test_returns_all_sessions(self):
        store = MemorySessionStore()
        await store.add_sid_to_session("s1", "sid-A")
        await store.add_sid_to_session("s2", "sid-B")
        all_sids = await store.get_all_session_sids()
        assert "s1" in all_sids
        assert "s2" in all_sids

    @pytest.mark.asyncio
    async def test_empty_store_returns_empty_dict(self):
        store = MemorySessionStore()
        assert await store.get_all_session_sids() == {}

    @pytest.mark.asyncio
    async def test_returns_copy_not_reference(self):
        store = MemorySessionStore()
        await store.add_sid_to_session("s1", "sid-A")
        all_sids = await store.get_all_session_sids()
        all_sids["NEW_SESSION"] = {"sid-X"}
        internal = await store.get_all_session_sids()
        assert "NEW_SESSION" not in internal


# ---------------------------------------------------------------------------
# MemorySessionStore — is_session_empty
# ---------------------------------------------------------------------------


class TestMemorySessionStoreIsEmpty:
    @pytest.mark.asyncio
    async def test_empty_when_no_sids(self):
        store = MemorySessionStore()
        assert await store.is_session_empty("nonexistent") is True

    @pytest.mark.asyncio
    async def test_not_empty_when_has_sid(self):
        store = MemorySessionStore()
        await store.add_sid_to_session("sess", "sid-A")
        assert await store.is_session_empty("sess") is False

    @pytest.mark.asyncio
    async def test_empty_after_all_sids_removed(self):
        store = MemorySessionStore()
        await store.add_sid_to_session("sess", "sid-A")
        await store.remove_sid_from_session("sess", "sid-A")
        assert await store.is_session_empty("sess") is True

    @pytest.mark.asyncio
    async def test_empty_string_session_uuid(self):
        store = MemorySessionStore()
        assert await store.is_session_empty("") is True


# ---------------------------------------------------------------------------
# MemorySessionStore — TTL cleanup
# ---------------------------------------------------------------------------


class TestMemorySessionStoreTtl:
    @pytest.mark.asyncio
    async def test_ttl_cleans_up_session(self):
        # Use a very short TTL so the test doesn't slow down
        store = MemorySessionStore(ttl_seconds=0)
        await store.add_sid_to_session("sess", "sid-A")
        # Let the event loop process the sleep(0)
        await asyncio.sleep(0.05)
        # Session should be gone after TTL
        assert await store.is_session_empty("sess") is True

    @pytest.mark.asyncio
    async def test_ttl_reset_on_add(self):
        """Adding a SID resets the TTL task."""
        store = MemorySessionStore(ttl_seconds=10)
        await store.add_sid_to_session("sess", "sid-A")
        task_1 = store._ttl_tasks.get("sess")
        # Adding again resets the TTL task
        await store.add_sid_to_session("sess", "sid-B")
        task_2 = store._ttl_tasks.get("sess")
        # The second task should be different (previous was cancelled)
        assert task_1 is not task_2 or task_1 is None


# ---------------------------------------------------------------------------
# create_session_store
# ---------------------------------------------------------------------------


class TestCreateSessionStore:
    def test_returns_memory_store_when_session_disabled(self):
        from ii_agent.realtime.session_store import create_session_store

        mock_settings = MagicMock()
        mock_settings.redis.session_enabled = False

        with patch("ii_agent.realtime.session_store.get_settings", return_value=mock_settings):
            store = create_session_store()

        assert isinstance(store, MemorySessionStore)

    def test_returns_redis_store_when_session_enabled(self):
        from ii_agent.realtime.session_store import create_session_store, RedisSessionStore

        mock_settings = MagicMock()
        mock_settings.redis.session_enabled = True

        with (
            patch("ii_agent.realtime.session_store.get_settings", return_value=mock_settings),
            patch("ii_agent.realtime.session_store.redis_client", MagicMock()),
        ):
            store = create_session_store()

        assert isinstance(store, RedisSessionStore)
