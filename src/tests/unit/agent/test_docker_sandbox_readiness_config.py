from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.agents.sandboxes.docker import DockerSandbox


pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_wait_for_ready_uses_configured_mcp_port_for_container_ip():
    container = MagicMock()
    container.id = "container-123"
    container.status = "running"
    container.attrs = {
        "NetworkSettings": {
            "Networks": {
                "ii-network": {"IPAddress": "172.18.0.5"},
            }
        }
    }

    sandbox = DockerSandbox(
        sandbox_id="sandbox-1",
        session_id="session-1",
        provider_sandbox_id="container-123",
        container=container,
        port_mappings={7777: 32000},
    )
    sandbox._config = MagicMock()
    sandbox._config.sandbox.docker_network = "ii-network"
    sandbox._config.sandbox.mcp_server_port = 7777

    response = MagicMock()
    response.status_code = 200

    with patch("httpx.AsyncClient") as mock_httpx_cls:
        mock_httpx_client = AsyncMock()
        mock_httpx_client.get.return_value = response
        mock_httpx_cls.return_value.__aenter__ = AsyncMock(return_value=mock_httpx_client)
        mock_httpx_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        await sandbox._wait_for_ready(timeout=2)

    call_url = mock_httpx_client.get.call_args[0][0]
    assert call_url == "http://172.18.0.5:7777/health"


@pytest.mark.asyncio
async def test_wait_for_ready_uses_mapping_for_configured_mcp_port_without_container_ip():
    container = MagicMock()
    container.id = "container-456"
    container.status = "running"
    container.attrs = {"NetworkSettings": {"Networks": {}}}

    sandbox = DockerSandbox(
        sandbox_id="sandbox-2",
        session_id="session-2",
        provider_sandbox_id="container-456",
        container=container,
        port_mappings={7777: 32000},
    )
    sandbox._config = MagicMock()
    sandbox._config.sandbox.docker_network = "ii-network"
    sandbox._config.sandbox.mcp_server_port = 7777

    response = MagicMock()
    response.status_code = 200

    with patch("httpx.AsyncClient") as mock_httpx_cls:
        mock_httpx_client = AsyncMock()
        mock_httpx_client.get.return_value = response
        mock_httpx_cls.return_value.__aenter__ = AsyncMock(return_value=mock_httpx_client)
        mock_httpx_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        await sandbox._wait_for_ready(timeout=2)

    call_url = mock_httpx_client.get.call_args[0][0]
    assert call_url == "http://localhost:32000/health"
