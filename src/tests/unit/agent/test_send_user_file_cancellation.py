"""Unit tests for SendUserFile on_tool_start / on_tool_end cancellation checks.

Validates that the `raise_if_cancelled` guard added to both hooks correctly
raises `RunCancelledException` when the run has been cancelled, and does NOT
raise when the run is still active or when no run_context is provided.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


@dataclass
class _FakeRunContext:
    run_id: str | None
    session_id: str | None = None
    user_id: str | None = None


def _make_tool():
    """Import and instantiate SendUserFile with minimal deps."""
    from ii_agent.agents.tools.agent.message_user import SendUserFile

    return SendUserFile()


def _make_agent():
    """Minimal agent mock that satisfies on_tool_start's super() call."""
    agent = MagicMock()
    agent.sandbox = MagicMock()
    agent.sandbox.get_info = AsyncMock(return_value=MagicMock())
    return agent


def _make_fc():
    """Minimal FunctionCall mock."""
    fc = MagicMock()
    fc.error = None
    fc.result = None
    return fc


# ---------------------------------------------------------------------------
# on_tool_start
# ---------------------------------------------------------------------------


class TestOnToolStartCancellation:
    @patch("ii_agent.agents.tools.agent.message_user.raise_if_cancelled", new_callable=AsyncMock)
    async def test_raises_when_run_cancelled(self, mock_raise):
        from ii_agent.core.redis.cancel import RunCancelledException

        mock_raise.side_effect = RunCancelledException("run-123 was cancelled")

        tool = _make_tool()
        agent = _make_agent()
        fc = _make_fc()
        ctx = _FakeRunContext(run_id="run-123")

        with pytest.raises(RunCancelledException, match="run-123"):
            await tool.on_tool_start(agent, fc, run_context=ctx)

        mock_raise.assert_awaited_once_with("run-123")

    @patch("ii_agent.agents.tools.agent.message_user.raise_if_cancelled", new_callable=AsyncMock)
    async def test_no_raise_when_run_active(self, mock_raise):
        """If raise_if_cancelled does not raise, on_tool_start proceeds normally."""
        mock_raise.return_value = None

        tool = _make_tool()
        agent = _make_agent()
        fc = _make_fc()
        ctx = _FakeRunContext(run_id="run-456")

        # Should not raise
        await tool.on_tool_start(agent, fc, run_context=ctx)
        mock_raise.assert_awaited_once_with("run-456")

    @patch("ii_agent.agents.tools.agent.message_user.raise_if_cancelled", new_callable=AsyncMock)
    async def test_skipped_when_no_run_context(self, mock_raise):
        """Without run_context, cancellation check is skipped entirely."""
        tool = _make_tool()
        agent = _make_agent()
        fc = _make_fc()

        await tool.on_tool_start(agent, fc, run_context=None)
        mock_raise.assert_not_awaited()

    @patch("ii_agent.agents.tools.agent.message_user.raise_if_cancelled", new_callable=AsyncMock)
    async def test_skipped_when_run_id_is_none(self, mock_raise):
        """If run_context has run_id=None, cancellation check is skipped."""
        tool = _make_tool()
        agent = _make_agent()
        fc = _make_fc()
        ctx = _FakeRunContext(run_id=None)

        await tool.on_tool_start(agent, fc, run_context=ctx)
        mock_raise.assert_not_awaited()


# ---------------------------------------------------------------------------
# on_tool_end
# ---------------------------------------------------------------------------


class TestOnToolEndCancellation:
    @patch("ii_agent.agents.tools.agent.message_user.raise_if_cancelled", new_callable=AsyncMock)
    async def test_raises_when_run_cancelled(self, mock_raise):
        from ii_agent.core.redis.cancel import RunCancelledException

        mock_raise.side_effect = RunCancelledException("run-789 was cancelled")

        tool = _make_tool()
        agent = _make_agent()
        fc = _make_fc()
        fc.error = "some error"  # early-return path after cancel check
        ctx = _FakeRunContext(run_id="run-789")

        with pytest.raises(RunCancelledException, match="run-789"):
            await tool.on_tool_end(agent, fc, run_context=ctx)

        mock_raise.assert_awaited_once_with("run-789")

    @patch("ii_agent.agents.tools.agent.message_user.raise_if_cancelled", new_callable=AsyncMock)
    async def test_no_raise_when_run_active(self, mock_raise):
        """If raise_if_cancelled does not raise, on_tool_end proceeds."""
        mock_raise.return_value = None

        tool = _make_tool()
        agent = _make_agent()
        fc = _make_fc()
        fc.error = "some error"  # triggers early return after cancel check
        ctx = _FakeRunContext(run_id="run-active")

        await tool.on_tool_end(agent, fc, run_context=ctx)
        mock_raise.assert_awaited_once_with("run-active")

    @patch("ii_agent.agents.tools.agent.message_user.raise_if_cancelled", new_callable=AsyncMock)
    async def test_skipped_when_no_run_context(self, mock_raise):
        tool = _make_tool()
        agent = _make_agent()
        fc = _make_fc()
        fc.error = "err"

        await tool.on_tool_end(agent, fc, run_context=None)
        mock_raise.assert_not_awaited()

    @patch("ii_agent.agents.tools.agent.message_user.raise_if_cancelled", new_callable=AsyncMock)
    async def test_skipped_when_run_id_is_none(self, mock_raise):
        tool = _make_tool()
        agent = _make_agent()
        fc = _make_fc()
        fc.error = "err"
        ctx = _FakeRunContext(run_id=None)

        await tool.on_tool_end(agent, fc, run_context=ctx)
        mock_raise.assert_not_awaited()
