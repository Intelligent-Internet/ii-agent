import uuid
from ii_agent.core.storage.models.settings import Settings
from ii_agent.sandbox.sandbox_registry import SandboxRegistry


class SandboxManager:
    def __init__(self, session_id: uuid.UUID, settings: Settings):
        self.session_id = session_id
        self.workspace_mode = settings.sandbox_config.mode
        self.settings = settings
        self.sandbox = None

    async def start_sandbox(self):
        self.sandbox = SandboxRegistry.create(
            self.workspace_mode, str(self.session_id), self.settings
        )
        await self.sandbox.create()

    def expose_port(self, port: int) -> str:
        return self.sandbox.expose_port(port)

    def get_host_url(self) -> str:
        return self.sandbox.get_host_url()

    # WIP
    async def connect_sandbox(self):
        self.sandbox = SandboxRegistry.create(
            self.workspace_mode, str(self.session_id), self.settings
        )
        await self.sandbox.connect()

    async def stop_sandbox(self):
        pass

    async def cleanup_sandbox(self):
        pass
