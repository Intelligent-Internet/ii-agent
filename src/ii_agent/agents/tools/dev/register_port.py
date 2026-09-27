from ii_agent.agents.tools.base import ToolResult
from ii_agent.agents.sandboxes.novnc import decorate_novnc_url
from ii_agent.agents.tools.sandbox.base import BaseSandboxTool
from typing import Any

NAME = "register_deployment"
DISPLAY_NAME = "Register deployment"
DESCRIPTION = """Register a port for deployment and get public access URL.
PURPOSE:
- Expose local development servers to public internet
- Enable sharing of web applications for testing/demo
- Support multiple concurrent deployments
WORKFLOW:
1. Start your server on a local port (e.g., 3000, 8000)
2. Register the port with this tool
3. Receive public URL for external access
COMMON PORTS:
- 3000-3999: Frontend development servers
- 8000-8999: Backend API servers
- 5000-5999: Flask/Python applications
RETURNS:
- Public URL accessible from internet
- URL remains active while server is running"""
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "port": {
            "type": "integer",
            "description": "The port to register",
        },
    },
    "required": ["port"],
}


class RegisterPort(BaseSandboxTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = False

    def __init__(
        self,
    ) -> None:
        super().__init__()

    async def execute(self, tool_input: dict[str, Any]) -> ToolResult:
        if not self.sandbox:
            return ToolResult(
                llm_content="Sandbox not initialized.",
                user_display_content="Sandbox not initialized.",
                is_error=True,
            )

        port = tool_input.get("port", None)
        if port is None:
            return ToolResult(
                llm_content="Please provide a port number.",
                user_display_content="Please provide a port number.",
                is_error=True,
            )

        # Browser-facing: this URL is shown to the user in the tool result.
        out = await self.sandbox.expose_port(port, external=True)
        out = await decorate_novnc_url(self.sandbox, port, out)

        return ToolResult(
            llm_content=f"Successfully registered port {port}. Tool output: {out}",
            user_display_content=f"Successfully registered port {port}. Tool output: {out}",
            is_error=False,
        )
