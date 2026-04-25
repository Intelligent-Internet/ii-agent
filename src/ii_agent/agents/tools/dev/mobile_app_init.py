"""Mobile app initialization tool for Expo projects (v1 wrapper)."""

from fastmcp.exceptions import ToolError
from google.genai._interactions.types.image_content import ImageContent
from ii_agent.agents.tools.base import TextContent
import logging
from typing import TYPE_CHECKING, Any

from ii_agent.core.container import get_app_container
from ii_agent.core.db import get_db_session_local
from ii_agent.agents.factory.mcp.base import MCPTool
from ii_agent.agents.tools.base import ToolResult

if TYPE_CHECKING:
    from ii_agent.agents.agent import IIAgent
    from ii_agent.agents.tools.function import FunctionCall

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 180  # Longer timeout for project initialization

# Name
NAME = "mobile_app_init"
DISPLAY_NAME = "Initialize Mobile App"

# Description
DESCRIPTION = """Initializes a React Native mobile application using Expo framework with modern development tools.

## Overview
This tool scaffolds a production-ready Expo mobile application with:
- Expo Router for file-based navigation
- TypeScript for type safety
- Standard React Native StyleSheet for styling
- Development server with tunnel mode for remote QR code access

## Features
- **Web Preview**: Accessible via iframe for instant preview
- **QR Code**: Tunnel-enabled for device testing from any network
- **Cross-platform**: iOS, Android, and Web support

## Available Templates
- **tabs**: Tab-based navigation template with example screens (default)
- **blank**: Minimal blank template
- **blank-typescript**: Minimal blank template with TypeScript

## Output
Returns:
- `web_preview_url`: URL for iframe web preview
- `qr_code_url`: QR code URL for Expo Go app scanning
- `tunnel_url`: Public tunnel URL for device access
- `project_path`: Path to the created project

## Post-Initialization
1. Project is created with Expo Router template
2. Dependencies are installed via bun
3. Dev server starts with --tunnel flag
4. Web preview and QR code URLs are captured and returned

## Usage Notes
- Users can scan the QR code with Expo Go app to test on their device
- Web preview URL can be embedded in iframe for instant viewing
- Use Expo skills for guidance on building features
"""

# Input schema
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "project_name": {
            "type": "string",
            "description": "Name for the mobile app project (lowercase, no spaces, use hyphens if needed). Example: `my-app`, `todo-app`",
        },
        "template": {
            "type": "string",
            "description": "Expo template to use",
            "enum": ["tabs", "blank", "blank-typescript"],
            "default": "tabs",
        },
        "with_tailwind": {
            "type": "boolean",
            "description": "Whether to set up NativeWind/Tailwind CSS styling (currently disabled)",
            "default": False,
            "const": False,
        },
    },
    "required": ["project_name"],
}


class MobileAppInitTool(MCPTool):
    """Tool for initializing Expo mobile app projects (v1 wrapper)."""

    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = False

    async def on_tool_start(self, agent: "IIAgent", fc: "FunctionCall") -> None:
        await super().on_tool_start(agent, fc)

    async def execute(self, tool_input: dict[str, Any]) -> ToolResult:
        try:
            result = await self._execute(tool_input)

            # If successful, expose the web port to get the preview URL
            if not result.is_error and isinstance(result.user_display_content, dict):
                web_port = result.user_display_content.get("web_port", 8081)
                try:
                    # Expose the port to get public URL using sandbox (set by parent in on_tool_start)
                    if hasattr(self, "sandbox") and self.sandbox:
                        # Browser-facing: web_preview_url is shown to the user.
                        web_preview_url = await self.sandbox.expose_port(web_port, external=True)
                        result.user_display_content["web_preview_url"] = web_preview_url

                        # Update the llm_content to include the web preview URL
                        if isinstance(result.llm_content, list) and len(result.llm_content) > 0:
                            first_content = result.llm_content[0]
                            if hasattr(first_content, "text"):
                                updated_text = first_content.text.replace(
                                    "use register_deployment tool to get public URL",
                                    f"`{web_preview_url}`",
                                )
                                updated_text = updated_text.replace(
                                    f"Use `register_deployment` tool with port {web_port} to get the web preview URL",
                                    f"Web preview available at: `{web_preview_url}`",
                                )
                                result.llm_content[0] = TextContent(type="text", text=updated_text)
                    else:
                        logger.warning("No sandbox available to expose port")
                except Exception as port_error:
                    logger.warning(f"Failed to expose port {web_port}: {port_error}")

            return result
        except Exception as e:
            return ToolResult(
                llm_content="Failed to initialize mobile app project: " + str(e),
                user_display_content="Failed to initialize mobile app project: " + str(e),
                is_error=True,
            )

    async def _execute(self, tool_input: dict[str, Any]) -> ToolResult:
        try:
            async with self.mcp_client:
                mcp_results = await self.mcp_client.call_tool(
                    self.name + "_internal",
                    tool_input,
                    timeout=DEFAULT_TIMEOUT,
                )

                llm_content = []
                has_image_content = False
                for mcp_result in mcp_results.content:
                    if mcp_result.type == "text":
                        llm_content.append(TextContent(type="text", text=mcp_result.text))
                    elif mcp_result.type == "image":
                        llm_content.append(
                            ImageContent(
                                type="image",
                                data=mcp_result.data,
                                mime_type=mcp_result.mimeType,
                            )
                        )
                        has_image_content = True
                    else:
                        raise ValueError(f"Unknown result type: {mcp_result.type}")

                user_display_content = None
                is_error = False
                # Logic for our internal tools
                if mcp_results.structured_content is not None:
                    user_display_content = mcp_results.structured_content.get(
                        "user_display_content"
                    )
                    is_error = mcp_results.structured_content.get("is_error")
                # For external tools (like MCP) or internal tools that don't have a user_display_content
                if not user_display_content:
                    if not has_image_content:
                        user_display_content = "\n".join([content.text for content in llm_content])
                    else:
                        user_display_content = [content.model_dump() for content in llm_content]

                return ToolResult(
                    llm_content=llm_content,
                    user_display_content=user_display_content,
                    is_error=is_error,
                )
        except ToolError as e:
            return ToolResult(
                llm_content=f"Error while calling tool {self.name} with input {tool_input}: {str(e)}\n\nPlease analyze the error message to determine if it's due to incorrect input parameters or an internal tool issue. If the error is due to incorrect input, retry with the correct parameters. Otherwise, try an alternative approach and inform the user about the issue.",
                user_display_content=f"Error while calling tool {self.name} with input {tool_input}: {str(e)}",
                is_error=True,
            )
        except Exception as e:
            return ToolResult(
                llm_content=f"Error while calling tool {self.name} with input {tool_input}: {str(e)}\n\nPlease analyze the error message to determine if it's due to incorrect input parameters or an internal tool issue. If the error is due to incorrect input, retry with the correct parameters. Otherwise, try an alternative approach and inform the user about the issue.",
                user_display_content=f"Error while calling tool {self.name} with input {tool_input}: {str(e)}",
                is_error=True,
            )

    async def on_tool_end(self, agent: "IIAgent", fc: "FunctionCall") -> None:
        if fc.error:
            return

        session_id = getattr(agent, "session_id", None)
        if not session_id:
            return

        tool_result = fc.result
        if not isinstance(tool_result, ToolResult):
            return
        if tool_result.is_error:
            return

        raw_result = None
        if isinstance(tool_result.user_display_content, dict):
            raw_result = tool_result.user_display_content
        if not isinstance(raw_result, dict):
            return

        project_name = raw_result.get("project_name")
        if not isinstance(project_name, str):
            return

        template = raw_result.get("template")
        template_str = template if isinstance(template, str) else None
        project_dir = raw_result.get("project_path") or raw_result.get("project_directory")
        project_dir_str = project_dir if isinstance(project_dir, str) else None

        # Persist mobile app project metadata
        project_record = await self._persist_project_metadata(
            session_id=str(session_id),
            project_name=project_name,
            framework=f"expo-{template_str}" if template_str else "expo-tabs",
            project_path=project_dir_str,
            description=f"Expo mobile app: {project_name}",
            database=None,
        )

        if project_record:
            raw_result["project"] = project_record
            tool_result.user_display_content = raw_result

    async def _persist_project_metadata(
        self,
        *,
        session_id: str,
        project_name: str,
        framework: str | None,
        project_path: str | None,
        description: str | None,
        database: dict | None,
    ) -> dict | None:
        try:
            import uuid as _uuid

            container = get_app_container()
            async with get_db_session_local() as db:
                project = await container.project_service.create_project(
                    db,
                    session_id=_uuid.UUID(session_id),
                    project_name=project_name,
                    framework=framework,
                    project_path=project_path,
                    description=description,
                    database=database,
                )
                await db.commit()
                if project:
                    return {"id": str(project.id), "name": project.name}
                return None
        except Exception as exc:
            logger.error("Failed to persist mobile app project metadata: %s", exc)
            return None
