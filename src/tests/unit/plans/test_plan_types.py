"""Tests for ii_agent.agents.plans.types — MilestoneStatus.terminal_states."""

from __future__ import annotations


class TestMilestoneStatusTerminalStates:
    def test_terminal_states_returns_completed_and_failed(self):
        from ii_agent.agents.plans.types import MilestoneStatus

        states = MilestoneStatus.terminal_states()
        assert MilestoneStatus.COMPLETED in states
        assert MilestoneStatus.FAILED in states
        assert MilestoneStatus.PENDING not in states
        assert MilestoneStatus.IN_PROGRESS not in states
