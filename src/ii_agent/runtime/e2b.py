from __future__ import annotations
import logging
import uuid
from typing import TYPE_CHECKING

from fastmcp.client import Client
from e2b_code_interpreter import Sandbox, SandboxListQuery
from ii_agent.runtime.base import BaseRuntime
from ii_agent.runtime.runtime_registry import RuntimeRegistry
from ii_agent.runtime.model.constants import RuntimeMode
from ii_agent.db.manager import Sessions

if TYPE_CHECKING:
    from ii_agent.core.storage.models.settings import Settings

logger = logging.getLogger(__name__)


@RuntimeRegistry.register(RuntimeMode.E2B)
class E2BRuntime(BaseRuntime):
    mode: RuntimeMode = RuntimeMode.E2B

    def __init__(self, session_id: uuid.UUID, settings: Settings):
        super().__init__(session_id=session_id, settings=settings)

    async def create(self):
        self.sandbox = Sandbox(
            self.settings.runtime_config.template_id,
            api_key=self._get_api_key(),
            timeout=3600,
        )
        self.host_url = (
            self.expose_port(self.settings.runtime_config.service_port) + "/mcp/"
        )
        if not self.sandbox.sandbox_id:
            raise ValueError("Sandbox ID is not set")
        self.runtime_id = str(self.sandbox.sandbox_id)

        Sessions.update_session_runtime_id(self.session_id, self.runtime_id)

    def expose_port(self, port: int) -> str:
        return "https://" + self.sandbox.get_host(port)

    def get_mcp_client(self, workspace_dir: str) -> Client:
        if not self.host_url:
            raise ValueError("Host URL is not set")
        return Client(self.host_url)

    async def connect(self):
        runtime_id = Sessions.get_runtime_id_by_session_id(self.session_id)
        if runtime_id is None:
            # Note: Raise error for now, should never happen
            raise ValueError(f"Runtime ID not found for session {self.session_id}")
            # self.create()

        self.sandbox = Sandbox.connect(
            runtime_id,
            api_key=self._get_api_key(),
        )
        self.host_url = (
            self.expose_port(self.settings.runtime_config.service_port) + "/mcp/"
        )
        self.runtime_id = self.sandbox.sandbox_id

    async def cleanup(self):
        pass

    async def start(self):
        runtime_id = Sessions.get_runtime_id_by_session_id(self.session_id)
        if runtime_id is None:
            # Note: Raise error for now, should never happen
            raise ValueError(f"Runtime ID not found for session {self.session_id}")
        if runtime_id in SandboxListQuery(state=["paused"]):
            self.sandbox = Sandbox.resume(
                runtime_id,
                api_key=self._get_api_key(),
                timeout=3600,
            )
            self.host_url = (
                self.expose_port(self.settings.runtime_config.service_port) + "/mcp/"
            )
            self.runtime_id = self.sandbox.sandbox_id

    def _get_api_key(self):
        if self.settings.runtime_config.runtime_api_key is None:
            logger.warning("Runtime API key is not set, using empty string")
            return ""
        else:
            return self.settings.runtime_config.runtime_api_key.get_secret_value()

    async def stop(self):
        if self.runtime_id is not None:
            self.sandbox.pause()
