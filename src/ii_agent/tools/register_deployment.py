from typing import Any, Optional
import os

from e2b import Sandbox

from ii_agent.tools.base import (
    ToolImplOutput,
    LLMTool,
)
from ii_agent.llm.message_history import MessageHistory
from ii_agent.tools.clients.config import RemoteClientConfig
from ii_agent.utils import WorkspaceManager


class RegisterDeploymentTool(LLMTool):
    """Tool for registering deployments"""

    name = "register_deployment"
    description = "Register a deployment and get the public url as well as the port that you can deploy your service on."

    input_schema = {
        "type": "object",
        "properties": {
            "port": {
                "type": "string",
                "description": "Port that you can deploy your service on",
            },
        },
        "required": ["port"],
    }

    def __init__(self, workspace_manager: WorkspaceManager, config: RemoteClientConfig):
        super().__init__()
        self.workspace_manager = workspace_manager
        self.config = config

    def _register_docker_port(self, port: str) -> str:
        # Make request to register service
        import httpx

        client = httpx.Client()
        response = client.post(
            f"{os.getenv('PROXY_SERVER_URL')}/api/register",
            json={
                "port": port,
                "container_name": self.workspace_manager.root.name,
            },
        )

        if response.status_code != 200:
            return ToolImplOutput(
                f"Failed to register service: {response.text}",
                f"Failed to register service: {response.text}",
            )

        # Get the UUID from the workspace path
        connection_uuid = self.workspace_manager.root.name

        # Construct the public URL using the base URL and connection UUID
        if os.getenv("NGINX_PORT") == "80":
            public_url = f"http://{connection_uuid}-{port}.{os.getenv('PUBLIC_DOMAIN')}"
        else:
            public_url = f"http://{connection_uuid}-{port}.{os.getenv('PUBLIC_DOMAIN')}:{os.getenv('NGINX_PORT')}"
        return public_url

    def _register_e2b_port(self, port: str) -> str:
        if self.config.container_id is None:
            raise ValueError("container_id is required for e2b mode")

        sandbox = Sandbox.connect(self.config.container_id)
        host = sandbox.get_host(int(port))
        return f"http://{host}"

    async def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        if self.config.mode == "e2b":
            public_url = self._register_e2b_port(tool_input["port"])
        else:
            public_url = self._register_docker_port(tool_input["port"])

        return ToolImplOutput(
            public_url,
            f"Registering successfully. Public url/base path to access the service: {public_url}",
        )
