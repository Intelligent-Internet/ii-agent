from typing import Any
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError
from ii_tool.tools.base import BaseTool, ToolResult, TextContent, ImageContent, ToolConfirmationDetails


class MCPTool(BaseTool):

    def __init__(
        self,
        mcp_client: Client,
        name: str,
        display_name: str,
        description: str,
        input_schema: dict[str, Any],
        read_only: bool,
    ):
        # MCP information
        self.mcp_client = mcp_client

        # Tool information
        self.name = name
        self.display_name = display_name
        self.description = description
        self.input_schema = input_schema
        self.read_only = read_only

    def should_confirm_execute(self, tool_input: dict[str, Any]) -> ToolConfirmationDetails | bool:
        return ToolConfirmationDetails(
            type="mcp", 
            message=f"Do you want to execute the MCP tool {self.name} with input {tool_input}?"
        )

    async def execute(self, tool_input: dict[str, Any]) -> ToolResult:
        try:
            async with self.mcp_client:
                mcp_results = await self.mcp_client.call_tool(self.name, tool_input)

                llm_content = []
                user_display_content = ""
                for mcp_result in mcp_results.content:
                    if mcp_result.type == "text":
                        llm_content.append(
                            TextContent(type="text", text=mcp_result.text)
                        )
                        user_display_content += mcp_result.text
                    elif mcp_result.type == "image":
                        llm_content.append(
                            ImageContent(
                                type="image",
                                data=mcp_result.data,
                                mimeType=mcp_result.mimeType,
                            )
                        )
                        user_display_content += f"\n[Redacted image]"
                    else:
                        raise ValueError(f"Unknown result type: {mcp_result.type}")

                return ToolResult(
                    llm_content=llm_content, user_display_content=user_display_content
                )
        except ToolError as e:
            return ToolResult(
                llm_content=f"Error while calling tool {self.name} with input {tool_input}: {str(e)}\n\nPlease analyze the error message to determine if it's due to incorrect input parameters or an internal tool issue. If the error is due to incorrect input, retry with the correct parameters. Otherwise, try an alternative approach and inform the user about the issue.",
                user_display_content=f"Error while calling tool {self.name} with input {tool_input}: {str(e)}",
            )