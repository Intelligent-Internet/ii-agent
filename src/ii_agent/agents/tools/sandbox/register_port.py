from __future__ import annotations

from typing import Any, Dict, TYPE_CHECKING

from ii_agent.agents.sandboxes import Sandbox
from ii_agent.agents.sandboxes.novnc import NOVNC_PORT, decorate_novnc_url
from ii_agent.agents.tools.sandbox.base import BaseSandboxTool
from ii_agent.agents.tools.base import ToolResult

if TYPE_CHECKING:
    from ii_agent.agents.agent import IIAgent
    from ii_agent.agents.tools.function import FunctionCall


class RegisterPortTool(BaseSandboxTool):
    """Tool to expose a port from the sandbox and get a public URL."""

    name: str = "register_port"
    display_name: str = "Register Port"
    description: str = """Expose a port from the sandbox to get a public access URL.

PURPOSE:
- Expose local development servers to public internet
- Enable sharing of web applications for testing/demo
- Support multiple concurrent deployments

WORKFLOW:
1. Start your server on a local port (e.g., 3000, 8000)
2. Use this tool to expose the port
3. Receive public URL for external access

COMMON PORTS:
- 3000-3999: Frontend development servers
- 8000-8999: Backend API servers
- 5000-5999: Flask/Python applications

RETURNS:
- Public URL accessible from internet
- URL remains active while server is running"""

    input_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "port": {
                "type": "integer",
                "description": "The port number to expose (e.g., 3000, 8000, 5000)",
            },
        },
        "required": ["port"],
    }
    read_only: bool = False

    def __init__(self) -> None:
        self.sandbox: Sandbox = None  # type: ignore

    async def on_tool_start(self, agent: "IIAgent", fc: "FunctionCall") -> None:
        await super().on_tool_start(agent, fc)

    async def execute(self, tool_input: Dict[str, Any]) -> ToolResult:
        """Execute the expose port operation.

        Args:
            tool_input: Dictionary containing 'port' key

        Returns:
            ToolResult with the public URL or error message
        """
        port = tool_input["port"]

        if not self.sandbox:
            return ToolResult(
                llm_content=f"Error: No sandbox available to expose port {port}",
                user_display_content=f"Failed to expose port {port}: No sandbox available",
                is_error=True,
            )

        try:
            # Browser-facing: ``public_url`` is rendered to the user.
            public_url = await self.sandbox.expose_port(port, external=True)
            public_url = await decorate_novnc_url(self.sandbox, port, public_url)
            if port == NOVNC_PORT:
                llm_msg = (
                    f"Successfully exposed port {port} (noVNC). The returned URL is "
                    f"a ready-to-click viewer link with the per-sandbox VNC password "
                    f"embedded as a query parameter — share it with the user as-is "
                    f"(do NOT append /vnc.html or any other path). URL: {public_url}"
                )
                user_msg = f"noVNC viewer ready (port {port}).\nURL: {public_url}"
            else:
                llm_msg = f"Successfully exposed port {port}. Public URL: {public_url}"
                user_msg = f"Port {port} exposed successfully.\nPublic URL: {public_url}"
            return ToolResult(
                llm_content=llm_msg,
                user_display_content=user_msg,
                is_error=False,
            )
        except Exception as e:
            return ToolResult(
                llm_content=f"Error exposing port {port}: {str(e)}",
                user_display_content=f"Failed to expose port {port}: {str(e)}",
                is_error=True,
            )
