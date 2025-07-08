from abc import ABC, abstractmethod

from ii_agent.core.storage.models.settings import Settings
from ii_agent.sandbox.model.exception import SandboxUninitializedError
from ii_agent.utils.constants import WorkSpaceMode


class BaseSandbox(ABC):
    mode: WorkSpaceMode
    settings: Settings
    sandbox_id: str | None = None
    host_url: str | None = None

    def __init__(self, session_id: str = None, settings: Settings = None):
        """
        Initializes a sandbox instance.
        """
        self.session_id = session_id
        self.settings = settings

    def get_host_url(self) -> str:
        if self.host_url is None:
            raise SandboxUninitializedError("Host URL is not set")
        return self.host_url

    def get_sandbox_id(self) -> str:
        if self.sandbox_id is None:
            raise SandboxUninitializedError("Sandbox ID is not set")
        return self.sandbox_id

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
