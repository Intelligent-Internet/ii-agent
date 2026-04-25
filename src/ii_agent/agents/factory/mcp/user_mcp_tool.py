"""User MCP Tool - Wrapper for user's custom MCP server tools.

This module provides a tool wrapper for tools from user-configured MCP servers.
Similar to ComposioMCPTool but for general user custom MCP servers.
"""

from typing import Any, Literal

from fastmcp import Client
from fastmcp.exceptions import ToolError

from ii_agent.agents.agent import IIAgent
from ii_agent.agents.tools.function import FunctionCall
from ii_agent.agents.tools.sandbox.base import BaseSandboxTool
from ii_agent.agents.tools.base import ImageContent, TextContent, ToolResult
from ii_agent.core.config.settings import get_settings

DEFAULT_TIMEOUT = 1800


class UserMCPTool(BaseSandboxTool):
    """Tool wrapper for user-configured custom MCP server tools.

    This class wraps tools from user's custom MCP servers (configured via MCP settings).
    Unlike internal MCP tools, these tools call the sandbox MCP server directly
    using the tool name as registered by the user's MCP server.

    Attributes:
        name: The tool name as reported by the MCP server
        description: The tool description from the MCP server
        input_schema: JSON schema for the tool's input parameters
        display_name: Human-readable display name for the tool
        mcp_server_id: Optional identifier for the source MCP server
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    display_name: str
    read_only: bool = False
    type: Literal["function", "openai_custom"] = "function"
    requires_confirmation: bool = False

    def __init__(
        self,
        *,
        name: str,
        display_name: str,
        description: str,
        input_schema: dict[str, Any],
        read_only: bool = False,
        requires_confirmation: bool = False,
        type: Literal["function", "openai_custom"] = "function",
        mcp_server_id: str | None = None,
    ):
        """Initialize a UserMCPTool.

        Args:
            name: The tool name as reported by the MCP server
            display_name: Human-readable display name
            description: Tool description from the MCP server
            input_schema: JSON schema for input parameters
            read_only: Whether this tool only reads data (no side effects)
            requires_confirmation: Whether to prompt user before execution
            type: Tool type (function or openai_custom)
            mcp_server_id: Optional identifier for the source MCP server
        """
        self.name = name
        self.display_name = display_name
        self.description = description
        self.read_only = read_only
        self.requires_confirmation = requires_confirmation
        self.mcp_server_id = mcp_server_id

        if type == "function":
            self.input_schema = input_schema
        else:
            self.format = input_schema

        self.mcp_client: Client | None = None

    async def on_tool_start(self, agent: IIAgent, fc: FunctionCall):
        """Initialize MCP client when tool execution starts.

        Gets the sandbox MCP client from the agent's sandbox.
        """
        await super().on_tool_start(agent, fc)
        sandbox = agent.sandbox
        # Lazy-retry the MCP handshake if the post-claim configure pass
        # exhausted its retries. See
        # docs/design-docs/sandbox-pool-claim-mcp-handoff-audit.md.
        from ii_agent.agents.factory.mcp.lazy_retry import ensure_mcp_configured

        await ensure_mcp_configured(sandbox.sandbox_id, agent.user_id)
        sandbox_url = await sandbox.expose_port(get_settings().mcp.port)
        self.mcp_client = sandbox.get_mcp_client(sandbox_url)

    async def execute(self, tool_input: dict[str, Any]) -> ToolResult:
        """Execute the tool via the sandbox MCP server.

        Args:
            tool_input: Input parameters for the tool

        Returns:
            ToolResult containing the tool's output or error information
        """
        try:
            mcp_tool_name = (
                f"mcp_{self.mcp_server_id}_{self.name}"
                if self.mcp_server_id
                else f"mcp_{self.name}"
            )
            async with self.mcp_client:
                mcp_results = await self.mcp_client.call_tool(
                    mcp_tool_name,
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

                # Handle structured content from tools
                if mcp_results.structured_content is not None:
                    user_display_content = mcp_results.structured_content.get(
                        "user_display_content"
                    )
                    is_error = mcp_results.structured_content.get("is_error", False)

                # Fallback for tools without structured content
                if not user_display_content:
                    if not has_image_content:
                        user_display_content = "\n".join(
                            [content.text for content in llm_content if hasattr(content, "text")]
                        )
                    else:
                        user_display_content = [content.model_dump() for content in llm_content]

                return ToolResult(
                    llm_content=llm_content,
                    user_display_content=user_display_content,
                    is_error=is_error,
                )

        except ToolError as e:
            error_msg = (
                f"Error while calling tool {self.name} with input {tool_input}: {str(e)}\n\n"
                "Please analyze the error message to determine if it's due to incorrect input "
                "parameters or an internal tool issue. If the error is due to incorrect input, "
                "retry with the correct parameters. Otherwise, try an alternative approach "
                "and inform the user about the issue."
            )
            return ToolResult(
                llm_content=error_msg,
                user_display_content=f"Error while calling tool {self.name}: {str(e)}",
                is_error=True,
            )
        except Exception as e:
            error_msg = (
                f"Error while calling tool {self.name} with input {tool_input}: {str(e)}\n\n"
                "Please analyze the error message to determine if it's due to incorrect input "
                "parameters or an internal tool issue. If the error is due to incorrect input, "
                "retry with the correct parameters. Otherwise, try an alternative approach "
                "and inform the user about the issue."
            )
            return ToolResult(
                llm_content=error_msg,
                user_display_content=f"Error while calling tool {self.name}: {str(e)}",
                is_error=True,
            )
