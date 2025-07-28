from typing import Dict
from fastmcp import Client, FastMCP
from ii_tool.tools.mcp_tool import MCPTool


async def load_tools_from_mcp(transport: FastMCP | str | Dict) -> list[MCPTool]:
    """Load tools from an MCP (Model Context Protocol) server.

    This function establishes a connection to an MCP server, retrieves all available tools,
    and wraps them in MCPTool instances for use within the application. Each tool includes
    metadata such as name, description, input schema, and annotations that determine
    display properties and read-only behavior.

    Args:
        transport (FastMCP | str | Dict): The transport mechanism for connecting to the MCP server.
            Can be either:
            - FastMCP server instance for in-memory/direct connection mode
            - URL string for HTTP-based connection. Example: "http://localhost:8080/mcp"
            - MCP config dictionary. Example:
                {
                    "mcpServers": {
                        "playwright": {
                        "command": "npx",
                        "args": [
                            "@playwright/mcp@latest",
                            "--isolated"
                        ]
                        }
                    }
                }

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