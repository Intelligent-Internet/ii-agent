import uuid
from ii_agent.core.storage.models.settings import Settings
from ii_agent.runtime.model.exception import RuntimeUninitializedError
from ii_agent.runtime.runtime_registry import RuntimeRegistry


class RuntimeManager:
    def __init__(self, session_id: uuid.UUID, settings: Settings):
        self.session_id = session_id
        self.workspace_mode = settings.runtime_config.mode
        self.settings = settings
        self.runtime = None

    async def start_runtime(self):
        self.runtime = RuntimeRegistry.create(
            self.workspace_mode, self.session_id, self.settings
        )
        await self.runtime.create()

    def expose_port(self, port: int) -> str:
        if self.runtime is None:
            raise RuntimeUninitializedError("Runtime is not initialized")
        return self.runtime.expose_port(port)

    def get_host_url(self) -> str:
        if self.runtime is None:
            raise RuntimeUninitializedError("Runtime is not initialized")
        return self.runtime.get_host_url()

    # WIP
    async def connect_runtime(self):
        self.runtime = RuntimeRegistry.create(
            self.workspace_mode, self.session_id, self.settings
        )
        await self.runtime.connect()

    async def stop_runtime(self):
        pass

    async def cleanup_runtime(self):
        pass
