import asyncio
import os
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
        return f"http://localhost:{port}"

    async def stop(self):
        pass

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

        self.host_url = f"http://localhost:{self.settings.sandbox_config.service_port}"

    async def cleanup(self):
        pass

    async def connect(self):
        self.host_url = f"http://localhost:{self.settings.sandbox_config.service_port}"
