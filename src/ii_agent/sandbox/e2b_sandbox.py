import logging
from e2b_code_interpreter import Sandbox, SandboxListQuery
from ii_agent.core.storage.models.settings import Settings
from ii_agent.sandbox.base_sandbox import BaseSandbox
from ii_agent.sandbox.sandbox_registry import SandboxRegistry
from ii_agent.utils.constants import WorkSpaceMode
from ii_agent.db.manager import Sessions

logger = logging.getLogger(__name__)


@SandboxRegistry.register(WorkSpaceMode.E2B)
class E2BSandbox(BaseSandbox):
    mode: WorkSpaceMode = WorkSpaceMode.E2B

    def __init__(self, session_id: str, settings: Settings):
        super().__init__(session_id=session_id, settings=settings)

    async def create(self):
        self.sandbox = Sandbox(
            self.settings.sandbox_config.template_id,
            api_key=self.settings.sandbox_config.sandbox_api_key.get_secret_value(),
            timeout=3600,
        )
        self.host_url = self.expose_port(self.settings.sandbox_config.service_port)
        self.sandbox_id = self.sandbox.sandbox_id
        import uuid

        Sessions.update_session_sandbox_id(uuid.UUID(self.session_id), self.sandbox_id)

    def expose_port(self, port: int) -> str:
        return "https://" + self.sandbox.get_host(port)

    async def connect(self):
        import uuid

        sandbox_id = Sessions.get_sandbox_id_by_session_id(uuid.UUID(self.session_id))
        if sandbox_id is None:
            # Note: Raise error for now, should never happen
            raise ValueError(f"Sandbox ID not found for session {self.session_id}")
            # self.create()

        self.sandbox = Sandbox.connect(
            sandbox_id,
            api_key=self.settings.sandbox_config.sandbox_api_key.get_secret_value(),
        )
        self.host_url = self.expose_port(self.settings.sandbox_config.service_port)
        self.sandbox_id = self.sandbox.sandbox_id

    async def cleanup(self):
        pass

    async def start(self):
        sandbox_id = Sessions.get_sandbox_id_by_session_id(self.session_id)
        if sandbox_id is None:
            # Note: Raise error for now, should never happen
            raise ValueError(f"Sandbox ID not found for session {self.session_id}")
        if sandbox_id in SandboxListQuery(state=["paused"]):
            self.sandbox = Sandbox.resume(
                sandbox_id,
                api_key=self.settings.sandbox_config.sandbox_api_key.get_secret_value(),
                timeout=3600,
            )
            self.host_url = self.expose_port(self.settings.sandbox_config.service_port)
            self.sandbox_id = self.sandbox.sandbox_id

    async def stop(self):
        if self.sandbox is not None:
            self.sandbox.pause()
