from typing import Any
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError
from ii_tool.tools.base import BaseTool, ToolResult, TextContent, ImageContent


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


async def load_tools_from_mcp(transport: FastMCP | str) -> list[MCPTool]:
    """Load tools from an MCP (Model Context Protocol) server.

    This function establishes a connection to an MCP server, retrieves all available tools,
    and wraps them in MCPTool instances for use within the application. Each tool includes
    metadata such as name, description, input schema, and annotations that determine
    display properties and read-only behavior.

    Args:
        transport (FastMCP | str): The transport mechanism for connecting to the MCP server.
            Can be either:
            - FastMCP server instance for in-memory/direct connection mode
            - URL string (e.g., "http://localhost:8080") for HTTP-based connection

    Returns:
        list[MCPTool]: A list of MCPTool instances, each wrapping a tool from the MCP server
            with its associated metadata and execution capabilities.

    Raises:
        AssertionError: If any tool from the server lacks a description.
        Various connection exceptions: If the MCP server is unreachable or returns errors.
    """
    tools = []
    mcp_client = Client(transport)

    async with mcp_client:
        mcp_tools = await mcp_client.list_tools()
        for tool in mcp_tools:
            assert tool.description is not None, f"Tool {tool.name} has no description"
            tool_annotations = tool.annotations
            if tool_annotations is None:
                display_name = tool.name
                read_only = False
            else:
                display_name = tool_annotations.title or tool.name
                read_only = tool_annotations.readOnlyHint if tool_annotations.readOnlyHint is not None else False

            tools.append(
                MCPTool(
                    mcp_client=mcp_client,
                    name=tool.name,
                    display_name=display_name,
                    description=tool.description,
                    input_schema=tool.inputSchema,
                    read_only=read_only,
                )
            )
    return tools