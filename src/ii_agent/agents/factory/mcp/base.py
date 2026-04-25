from typing import Any, Literal
from ii_agent.agents.agent import IIAgent
from ii_agent.agents.tools.function import FunctionCall
from ii_agent.agents.tools.sandbox.base import BaseSandboxTool
from ii_agent.agents.tools.base import ImageContent, TextContent, ToolResult
from ii_agent.core.config.settings import get_settings
from fastmcp.exceptions import ToolError
from fastmcp import Client

DEFAULT_TIMEOUT = 1800


class MCPTool(BaseSandboxTool):
    # Regular class attributes (not ClassVar)
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
        read_only: bool,
        requires_confirmation: bool = False,
        type: Literal[
            "function", "openai_custom"
        ] = "function",  # check https://platform.openai.com/docs/guides/function-calling#context-free-grammars
    ):
        # Tool information
        self.name = name
        self.display_name = display_name
        self.description = description
        self.read_only = read_only
        if type == "function":
            self.input_schema = input_schema
        else:
            self.format = input_schema
        self.mcp_client: Client = None
        self.requires_confirmation = requires_confirmation

    async def on_tool_start(self, agent: IIAgent, fc: FunctionCall):
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
        try:
            async with self.mcp_client:
                mcp_results = await self.mcp_client.call_tool(
                    self.name,
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
