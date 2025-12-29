from typing import Any, Callable
from ii_tool.interfaces.sandbox import SandboxInterface
from ii_tool.tools.base import BaseTool, ToolResult


# Name
NAME = "register_deployment"
DISPLAY_NAME = "Register deployment"

# Description
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

# Input schema
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

class RegisterPort(BaseTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = False

    def __init__(
        self,
        sandbox: SandboxInterface,
    ) -> None:
        super().__init__()
        self.sandbox = sandbox

    async def execute(
        self,
        tool_input: dict[str, Any],
    ) -> ToolResult:
        port = tool_input["port"]
        out = await self.sandbox.expose_port(port, external=True)

        return ToolResult(
            llm_content=f"Successfully registered port {port}. Tool output: {out}",
            user_display_content=f"Successfully registered port {port}. Tool output: {out}",
            is_error=False,
        )

    async def execute_mcp_wrapper(
        self,
        port: int,
    ):
        return await self._mcp_wrapper(
            tool_input={
                "port": port,
            }
        )
