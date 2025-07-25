from __future__ import annotations
import asyncio
import os
from typing import TYPE_CHECKING

from fastmcp.client import Client
from ii_tool.mcp.server import create_mcp
from ii_agent.runtime.base import BaseRuntime
from ii_agent.runtime.runtime_registry import RuntimeRegistry
from ii_agent.runtime.model.constants import RuntimeMode

if TYPE_CHECKING:
    from ii_agent.core.storage.models.settings import Settings


@RuntimeRegistry.register(RuntimeMode.LOCAL)
class LocalRuntime(BaseRuntime):
    mode: RuntimeMode = RuntimeMode.LOCAL

    def __init__(self, session_id: str, settings: Settings):
        super().__init__(session_id=session_id, settings=settings)

    async def start(self):
        pass

    def expose_port(self, port: int) -> str:
        return f"http://localhost:{port}"

    async def stop(self):
        pass

    def get_mcp_client(self, workspace_dir: str) -> Client:
        mcp_client = create_mcp(workspace_dir, str(self.session_id))
        return Client(mcp_client)

    async def create(self):
        # Start code-server in the background
        code_server_cmd = (
            "code-server "
            f"--port {os.getenv('CODE_SERVER_PORT', 9000)} "
            "--auth none "
            f"--bind-addr 0.0.0.0:{os.getenv('CODE_SERVER_PORT', 9000)} "
            "--disable-telemetry "
            "--disable-update-check "
            "--trusted-origins * "
            "--disable-workspace-trust "
            f"/.ii_agent/workspace/{self.session_id} &"  # Quickfix: hard code for now
        )

        try:
            process = await asyncio.create_subprocess_shell(
                code_server_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            # Don't wait for the process to complete since it runs in background
            print(f"Started code-server with PID: {process.pid}")
        except Exception as e:
            print(f"Failed to start code-server: {e}")

        self.host_url = f"http://localhost:{self.settings.runtime_config.service_port}"

    async def cleanup(self):
        pass

    async def connect(self):
        self.host_url = f"http://localhost:{self.settings.runtime_config.service_port}"
