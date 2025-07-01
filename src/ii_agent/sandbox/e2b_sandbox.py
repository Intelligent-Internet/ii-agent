from e2b import Sandbox
from ii_agent.core.storage.models.settings import Settings
from ii_agent.sandbox.base_sandbox import BaseSandbox
from ii_agent.sandbox.sandbox_registry import SandboxRegistry
from ii_agent.utils.constants import WorkSpaceMode


@SandboxRegistry.register(WorkSpaceMode.E2B)
class E2BSandbox(BaseSandbox):
    mode: WorkSpaceMode = WorkSpaceMode.E2B

    def __init__(self, container_name: str, settings: Settings):
        super().__init__(container_name=container_name, settings=settings)

    async def start(self):
        self.sandbox = Sandbox(
            self.settings.sandbox_config.template_id,
            api_key=self.settings.sandbox_config.sandbox_api_key.get_secret_value(),
            timeout=3600,
        )
        self.host_url = self.sandbox.get_host(self.settings.sandbox_config.service_port)
        self.sandbox_id = self.sandbox.sandbox_id

    def expose_port(self, port: int) -> str:
        return self.sandbox.get_host(port)

    async def stop(self):
        pass

    async def connect(self):
        pass
