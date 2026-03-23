from typing import Any, Callable, Optional, List
from ii_tool.interfaces.sandbox import SandboxInterface
from ii_tool.tools.base import BaseTool, ToolResult


# Name
NAME = "register_deployment"
DISPLAY_NAME = "Register deployment"

# Common description parts
_DESCRIPTION_WORKFLOW = """WORKFLOW:
1. Start your server on a supported port
2. Register the port with this tool
3. Receive accessible URL"""

_DESCRIPTION_RETURNS = """RETURNS:
- Accessible URL for the deployed service
- URL remains active while server is running"""

# Description for local/Docker mode (restricted ports, localhost URLs)
DESCRIPTION_LOCAL = f"""Register a port for deployment and get an accessible URL.
PURPOSE:
- Expose sandbox services to the host machine
- Enable file downloads and web app testing
- Share running applications with the local browser
{_DESCRIPTION_WORKFLOW}
REQUIRED PORTS (you MUST use one of these):
- 3000: Frontend dev servers (React, Next.js, Express)
- 5173: Vite development server
- 6080: noVNC web viewer (use this to let the user handle CAPTCHAs, logins, or other manual browser interactions)
- 8080: General HTTP server (recommended for file serving)
For serving files to users: python3 -m http.server 8080
Other ports will NOT work. Always use 3000, 5173, 6080, or 8080.
{_DESCRIPTION_RETURNS}"""

# Description for cloud mode (any port, public URLs)
DESCRIPTION_CLOUD = f"""Register a port for deployment and get a public access URL.
PURPOSE:
- Expose local development servers to public internet
- Enable sharing of web applications for testing/demo
- Support multiple concurrent deployments
{_DESCRIPTION_WORKFLOW}
COMMON PORTS:
- 3000-3999: Frontend development servers
- 8000-8999: Backend API servers
- 5000-5999: Flask/Python applications
{_DESCRIPTION_RETURNS}"""

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
    input_schema = INPUT_SCHEMA
    read_only = False

    def __init__(
        self,
        sandbox: SandboxInterface,
    ) -> None:
        super().__init__()
        self.sandbox = sandbox
        # Set description based on available ports
        available_ports = sandbox.get_available_ports()
        if available_ports is not None:
            # Local/Docker mode: restricted ports
            self.description = DESCRIPTION_LOCAL
        else:
            # Cloud mode: any port
            self.description = DESCRIPTION_CLOUD

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
