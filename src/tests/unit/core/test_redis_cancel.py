"""Unit tests for MemoryRunCancellationManager (in-process cancellation)."""

from __future__ import annotations

import pytest

from ii_agent.core.redis.cancel import MemoryRunCancellationManager, RunCancelledException


@pytest.fixture
def mgr() -> MemoryRunCancellationManager:
    return MemoryRunCancellationManager()


class TestRegisterRun:
    @pytest.mark.asyncio
    async def test_run_registered_as_not_cancelled(self, mgr):
        await mgr.register_run("run-1")
        assert not await mgr.is_cancelled("run-1")

    @pytest.mark.asyncio
    async def test_register_multiple_runs(self, mgr):
        await mgr.register_run("run-a")
        await mgr.register_run("run-b")
        assert not await mgr.is_cancelled("run-a")
        assert not await mgr.is_cancelled("run-b")

    @pytest.mark.asyncio
    async def test_register_overwrites_cancelled_state(self, mgr):
        """Re-registering a run resets its cancellation flag."""
        await mgr.register_run("run-1")
        await mgr.cancel_run("run-1")
        assert await mgr.is_cancelled("run-1")
        await mgr.register_run("run-1")
        assert not await mgr.is_cancelled("run-1")


class TestCancelRun:
    @pytest.mark.asyncio
    async def test_returns_true_for_known_run(self, mgr):
        await mgr.register_run("run-1")
        result = await mgr.cancel_run("run-1")
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_for_unknown_run(self, mgr):
        result = await mgr.cancel_run("no-such-run")
        assert result is False

    @pytest.mark.asyncio
    async def test_run_is_cancelled_after_cancel(self, mgr):
        await mgr.register_run("run-1")
        await mgr.cancel_run("run-1")
        assert await mgr.is_cancelled("run-1")


class TestIsCancelled:
    @pytest.mark.asyncio
    async def test_returns_false_for_unregistered_run(self, mgr):
        assert not await mgr.is_cancelled("unknown-run")

    @pytest.mark.asyncio
    async def test_returns_false_for_active_run(self, mgr):
        await mgr.register_run("run-1")
        assert not await mgr.is_cancelled("run-1")

    @pytest.mark.asyncio
    async def test_returns_true_after_cancellation(self, mgr):
        await mgr.register_run("run-1")
        await mgr.cancel_run("run-1")
        assert await mgr.is_cancelled("run-1")


class TestCleanupRun:
    @pytest.mark.asyncio
    async def test_removes_run_from_tracking(self, mgr):
        await mgr.register_run("run-1")
        await mgr.cleanup_run("run-1")
        active = await mgr.get_active_runs()
        assert "run-1" not in active

    @pytest.mark.asyncio
    async def test_cleanup_nonexistent_run_does_not_raise(self, mgr):
        # Should not raise even if run does not exist
        await mgr.cleanup_run("ghost-run")

    @pytest.mark.asyncio
    async def test_cleanup_restores_is_cancelled_to_false(self, mgr):
        await mgr.register_run("run-1")
        await mgr.cancel_run("run-1")
        await mgr.cleanup_run("run-1")
        # After cleanup, the run is gone; is_cancelled should return False (default)
        assert not await mgr.is_cancelled("run-1")


class TestRaiseIfCancelled:
    @pytest.mark.asyncio
    async def test_does_not_raise_for_active_run(self, mgr):
        await mgr.register_run("run-1")
        await mgr.raise_if_cancelled("run-1")  # Should not raise

    @pytest.mark.asyncio
    async def test_raises_for_cancelled_run(self, mgr):
        await mgr.register_run("run-1")
        await mgr.cancel_run("run-1")
        with pytest.raises(RunCancelledException, match="run-1"):
            await mgr.raise_if_cancelled("run-1")

    @pytest.mark.asyncio
    async def test_does_not_raise_for_unknown_run(self, mgr):
        # Unknown run: is_cancelled returns False → no raise
        await mgr.raise_if_cancelled("not-registered")


class TestGetActiveRuns:
    @pytest.mark.asyncio
    async def test_empty_when_no_runs(self, mgr):
        active = await mgr.get_active_runs()
        assert active == {}

    @pytest.mark.asyncio
    async def test_shows_registered_runs(self, mgr):
        await mgr.register_run("run-1")
        await mgr.register_run("run-2")
        active = await mgr.get_active_runs()
        assert "run-1" in active
        assert "run-2" in active

    @pytest.mark.asyncio
    async def test_reflects_cancellation_state(self, mgr):
        await mgr.register_run("run-1")
        await mgr.register_run("run-2")
        await mgr.cancel_run("run-2")
        active = await mgr.get_active_runs()
        assert active["run-1"] is False
        assert active["run-2"] is True

    @pytest.mark.asyncio
    async def test_returns_copy_not_reference(self, mgr):
        await mgr.register_run("run-1")
        active = await mgr.get_active_runs()
        active["run-1"] = True  # Mutate the returned copy
        # Original should not be affected
        assert not await mgr.is_cancelled("run-1")
