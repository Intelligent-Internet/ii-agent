"""Tests for the /health endpoint conditional response behavior.

Covers:
- local_mode=True returns extended configuration details
- local_mode=False returns only status (no internal details leaked)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


def _make_settings(*, local_mode: bool = False):
    settings = MagicMock()
    settings.sandbox.local_mode = local_mode
    settings.agent.inner_loop_mode = "a2a"
    settings.agent.chat_inner_loop_mode = "a2a"
    settings.agent.a2a_backend = "copilot"
    return settings


@pytest.mark.asyncio
async def test_health_local_mode_returns_extended_info():
    """In local mode, health endpoint exposes agent configuration."""
    from ii_agent.app.health import health_check

    with patch("ii_agent.app.health.get_settings", return_value=_make_settings(local_mode=True)):
        result = await health_check()

    assert result["status"] == "ok"
    assert "agent_inner_loop_mode" in result
    assert "chat_inner_loop_mode" in result
    assert "a2a_backend" in result
    assert result["agent_inner_loop_mode"] == "a2a"


@pytest.mark.asyncio
async def test_health_non_local_mode_returns_minimal():
    """In non-local mode, health endpoint only returns status — no internal config leaked."""
    from ii_agent.app.health import health_check

    with patch("ii_agent.app.health.get_settings", return_value=_make_settings(local_mode=False)):
        result = await health_check()

    assert result == {"status": "ok"}
    assert "agent_inner_loop_mode" not in result
    assert "a2a_backend" not in result
