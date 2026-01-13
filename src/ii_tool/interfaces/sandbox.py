"""Abstract sandbox interface to decouple ii_tool from ii_agent."""

from abc import ABC, abstractmethod
from typing import List, Optional


class SandboxInterface(ABC):
    """Abstract interface for sandbox operations needed by ii_tool."""

    @abstractmethod
    async def expose_port(self, port: int) -> str:
        """Expose a port in the sandbox and return the public URL."""
        pass

    def get_available_ports(self) -> Optional[List[int]]:
        """Get list of available ports for external access.
        
        Returns:
            List of available port numbers, or None if any port is available.
        """
        return None  # Default: any port is available (cloud mode)