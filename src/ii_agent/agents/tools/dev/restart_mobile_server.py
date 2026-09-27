"""Mobile app server restart tool (v1 wrapper)."""

from typing import TYPE_CHECKING, Any
import logging

from ii_agent.agents.factory.mcp.base import MCPTool
from ii_agent.agents.tools.base import ToolResult, TextContent

if TYPE_CHECKING:
    from ii_agent.agents.agent import IIAgent
    from ii_agent.agents.tools.function import FunctionCall

logger = logging.getLogger(__name__)

# Name - matches internal tool name for direct MCP passthrough
NAME = "restart_mobile_server"
DISPLAY_NAME = "Restart Mobile App Server"

# Description
DESCRIPTION = """Restarts the Expo mobile app development server.

## Overview
This tool stops the current Expo development server and starts a new one, generating new tunnel URLs for device testing.

## When to Use
- After making significant configuration changes
- When the tunnel URL has expired or stopped working
- When the development server becomes unresponsive
- To refresh the QR code for device testing

## What Happens
1. Stops the current Expo server
2. Starts a new Expo server with `--tunnel --web` flags
3. Captures new tunnel URL and QR code value
4. Updates the web preview URL for iframe display

## Output
Returns:
- `web_preview_url`: New URL for iframe web preview
- `qr_code_value`: New QR code URL for Expo Go app scanning
- `tunnel_url`: New public tunnel URL for device access
- `project_path`: Path to the project

## Notes
- Requires a mobile app project to be initialized first
- The new QR code will be displayed in the preview panel
- Device connections will need to rescan the QR code after restart
"""

# Input schema
INPUT_SCHEMA = {"type": "object", "properties": {}}


class RestartMobileServerTool(MCPTool):
    """Tool for restarting the Expo mobile app development server (v1 wrapper)."""

    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = False

    async def on_tool_start(self, agent: "IIAgent", fc: "FunctionCall") -> None:
        await super().on_tool_start(agent, fc)

    async def execute(self, tool_input: dict[str, Any]) -> ToolResult:
        # Call the base MCPTool execute which calls self.name directly
        result = await super().execute(tool_input)

        # If successful, expose the web port to get the preview URL
        if not result.is_error and isinstance(result.user_display_content, dict):
            web_port = result.user_display_content.get("web_port", 8081)
            try:
                # Expose the port to get public URL using sandbox
                if hasattr(self, "sandbox") and self.sandbox:
                    # Browser-facing: web_preview_url is shown to the user.
                    web_preview_url = await self.sandbox.expose_port(web_port, external=True)
                    result.user_display_content["web_preview_url"] = web_preview_url

                    # Update the llm_content to include the web preview URL
                    if isinstance(result.llm_content, list) and len(result.llm_content) > 0:
                        first_content = result.llm_content[0]
                        if hasattr(first_content, "text"):
                            updated_text = (
                                first_content.text + f"\n- **Web Preview URL:** `{web_preview_url}`"
                            )
                            result.llm_content[0] = TextContent(type="text", text=updated_text)
                else:
                    logger.warning("No sandbox available to expose port")
            except Exception as port_error:
                logger.warning(f"Failed to expose port {web_port}: {port_error}")

        return result
