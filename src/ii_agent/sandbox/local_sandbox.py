from ii_agent.core.storage.models.settings import Settings
from ii_agent.sandbox.base_sandbox import BaseSandbox
from ii_agent.sandbox.sandbox_registry import SandboxRegistry
from ii_agent.utils.constants import WorkSpaceMode


@SandboxRegistry.register(WorkSpaceMode.LOCAL)
class LocalSandbox(BaseSandbox):
    mode: WorkSpaceMode = WorkSpaceMode.LOCAL

    def __init__(self, session_id: str, settings: Settings):
        super().__init__(session_id=session_id, settings=settings)

    async def start(self):
        pass

    def expose_port(self, port: int) -> str:
        return ""

    async def stop(self):
        pass

    async def create(self):
        self.host_url = f"http://localhost:{self.settings.sandbox_config.service_port}"

    async def cleanup(self):
        pass

    async def connect(self):
        self.host_url = f"http://localhost:{self.settings.sandbox_config.service_port}"
