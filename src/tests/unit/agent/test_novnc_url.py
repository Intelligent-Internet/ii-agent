"""Tests for ``ii_agent.agents.sandboxes.novnc``."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from ii_agent.agents.sandboxes.novnc import (
    NOVNC_PORT,
    VNC_PASSWORD_PATH,
    decorate_novnc_url,
)


@pytest.mark.asyncio
async def test_decorate_novnc_url_returns_base_url_for_non_novnc_port() -> None:
    sandbox = AsyncMock()
    result = await decorate_novnc_url(sandbox, port=3000, base_url="http://h:31000")
    assert result == "http://h:31000"
    sandbox.run_command.assert_not_called()


@pytest.mark.asyncio
async def test_decorate_novnc_url_embeds_password_for_port_6080() -> None:
    sandbox = AsyncMock()
    sandbox.run_command.return_value = "TyRvsUIB\n"

    result = await decorate_novnc_url(sandbox, port=NOVNC_PORT, base_url="http://192.168.2.2:31381")

    assert result == (
        "http://192.168.2.2:31381/vnc.html?autoconnect=true&resize=remote&password=TyRvsUIB"
    )
    sandbox.run_command.assert_awaited_once()
    cmd = sandbox.run_command.await_args.args[0]
    assert VNC_PASSWORD_PATH in cmd


@pytest.mark.asyncio
async def test_decorate_novnc_url_url_encodes_special_chars() -> None:
    sandbox = AsyncMock()
    sandbox.run_command.return_value = "a&b=c d\n"

    result = await decorate_novnc_url(sandbox, port=NOVNC_PORT, base_url="http://h:1/")

    assert result == "http://h:1/vnc.html?autoconnect=true&resize=remote&password=a%26b%3Dc%20d"


@pytest.mark.asyncio
async def test_decorate_novnc_url_omits_password_when_empty() -> None:
    sandbox = AsyncMock()
    sandbox.run_command.return_value = ""

    result = await decorate_novnc_url(sandbox, port=NOVNC_PORT, base_url="http://h:1")

    assert result == "http://h:1/vnc.html?autoconnect=true&resize=remote"


@pytest.mark.asyncio
async def test_decorate_novnc_url_handles_run_command_failure() -> None:
    sandbox = AsyncMock()
    sandbox.run_command.side_effect = RuntimeError("boom")

    result = await decorate_novnc_url(sandbox, port=NOVNC_PORT, base_url="http://h:1")

    # Falls back to viewer URL without password rather than raising.
    assert result == "http://h:1/vnc.html?autoconnect=true&resize=remote"
