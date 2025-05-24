from typing import Any, Optional

from ii_agent.tools.base import (
    ToolImplOutput,
    LLMTool,
)
from ii_agent.llm.message_history import MessageHistory
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

    def __init__(self, workspace_manager: WorkspaceManager):
        super().__init__()
        self.workspace_manager = workspace_manager

    def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        port = tool_input["port"]
        # Make request to register service
        import httpx

        client = httpx.Client()
        response = client.post(
            "http://localhost:9000/api/register",
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
        public_url = f"http://{connection_uuid}-{port}.127.0.0.1.nip.io"

        return ToolImplOutput(
            public_url,
            f"Registering successfully. Public url/base path to access the service: {public_url}",
        )
