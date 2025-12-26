"""Adapter to make IISandbox compatible with ii_tool's SandboxInterface."""

from ii_tool.interfaces.sandbox import SandboxInterface
from ii_agent.sandbox.ii_sandbox import IISandbox


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