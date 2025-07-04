from typing import Any, Optional

from ii_agent.tools.base import (
    ToolImplOutput,
    LLMTool,
)
from ii_agent.llm.message_history import MessageHistory
from ii_agent.utils.sandbox_manager import SandboxManager


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

    def __init__(self, sandbox_manager: SandboxManager):
        super().__init__()
        self.sandbox_manager = sandbox_manager

    async def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        public_url = self.sandbox_manager.expose_port(int(tool_input["port"]))

        return ToolImplOutput(
            f"Registering successfully. Public url/base path to access the service: {public_url}. Update all localhost or 127.0.0.1 to the public url in your code. If you are using Next Auth, update your NEXTAUTH_URL",
            f"Registering successfully. Public url/base path to access the service: {public_url}. Update all localhost or 127.0.0.1 to the public url in your code. If you are using Next Auth, update your NEXTAUTH_URL",
        )
