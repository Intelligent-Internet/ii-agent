"""Adapter to make IISandbox compatible with ii_tool's SandboxInterface."""

import os
from typing import List, Optional

from ii_tool.interfaces.sandbox import SandboxInterface
from ii_agent.sandbox.ii_sandbox import IISandbox

# Ports available in Docker local sandbox mode (must match docker.py DEFAULT_EXPOSED_PORTS)
# Excludes internal ports (MCP 6060, code-server 9000)
DOCKER_AVAILABLE_PORTS = [3000, 5173, 8080]


class IISandboxToSandboxInterfaceAdapter(SandboxInterface):
    """Adapter that allows IISandbox to be used where SandboxInterface is expected."""

    def __init__(self, sandbox: IISandbox):
        """Initialize adapter with an IISandbox instance.

        Args:
            sandbox: An instance of IISandbox from ii_agent
        """
        self._sandbox = sandbox

    async def expose_port(self, port: int, external: bool = True) -> str:
        """Expose a port in the sandbox and return the public URL.

        Args:
            port: The port to expose
            external: If True, returns host-mapped URL for browser access.
                     If False, returns internal Docker IP for container-to-container.
                     Defaults to True for backwards compatibility.
        """
        return await self._sandbox.expose_port(port, external=external)

    def get_available_ports(self) -> Optional[List[int]]:
        """Get list of available ports for external access.
        
        Returns:
            List of available port numbers for Docker mode, or None for cloud mode.
        """
        provider = os.getenv("SANDBOX_PROVIDER", "e2b").lower()
        if provider in ("docker", "local"):
            return DOCKER_AVAILABLE_PORTS
        return None  # Cloud mode: any port is available