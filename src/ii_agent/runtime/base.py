from __future__ import annotations
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from fastmcp import Client

from ii_agent.runtime.model.exception import RuntimeUninitializedError
from ii_agent.runtime.model.constants import RuntimeMode

if TYPE_CHECKING:
    from ii_agent.core.storage.models.settings import Settings


class BaseRuntime(ABC):
    """
    Base runtime class.
    """

    mode: RuntimeMode
    session_id: str
    settings: Settings
    runtime_id: str | None = None
    host_url: str | None = None

    def __init__(self, session_id: str, settings: Settings):
        """
        Initializes a runtime instance.
        """
        self.session_id = session_id
        self.settings = settings

    @abstractmethod
    def get_mcp_client(self, workspace_dir: str) -> Client:
        raise NotImplementedError("Subclasses must implement this method")

    def get_runtime_id(self) -> str:
        if self.runtime_id is None:
            raise RuntimeUninitializedError("Runtime ID is not set")
        return self.runtime_id

    @abstractmethod
    async def connect(self) -> None:
        pass

    @abstractmethod
    def expose_port(self, port: int) -> str:
        pass

    @abstractmethod
    async def create(self) -> None:
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        pass

    @abstractmethod
    async def start(self) -> None:
        pass

    @abstractmethod
    async def stop(self) -> None:
        pass
