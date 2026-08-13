"""Tests for ii_agent.agents.utils.timer — Timer branch coverage."""

from __future__ import annotations


class TestTimerBranches:
    def test_stop_without_start_returns_end_time(self):
        """Branch [23, 25]: stop() when start_time is None — skips elapsed calc."""
        from ii_agent.agents.utils.timer import Timer

        t = Timer()
        end = t.stop()
        assert end is not None
        assert t.elapsed_time is None  # not set if start_time was None

    def test_exit_without_start_does_not_set_elapsed(self):
        """Branch [33, -31]: __exit__ when start_time is None."""
        from ii_agent.agents.utils.timer import Timer

        t = Timer()
        t.__exit__(None, None, None)
        assert t.elapsed_time is None

    def test_elapsed_without_start_returns_zero(self):
        """Branch in elapsed property: start_time is None → returns 0.0."""
        from ii_agent.agents.utils.timer import Timer

        t = Timer()
        assert t.elapsed == 0.0
