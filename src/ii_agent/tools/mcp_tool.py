from typing import Any, Optional
from fastmcp import Client
from mcp.types import ToolAnnotations
from ii_agent.tools.base import BaseTool, ToolResult, TextContent, ImageContent, ToolConfirmationDetails, ToolConfirmationOutcome
from ii_agent.core.config.ii_agent_config import IIAgentConfig

class MCPTool(BaseTool):

    def __init__(self, mcp_client: Client, name: str, description: str, input_schema: dict[str, Any], annotations: Optional[ToolAnnotations] = None):
        # MCP information
        self.mcp_client = mcp_client

        # Tool information
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.annotations = annotations
        
    def is_read_only(self) -> bool:
        if self.annotations is not None:
            return self.annotations.readOnlyHint or False
        return False

    async def should_confirm_execute(self, tool_input: dict[str, Any]) -> ToolConfirmationDetails | bool:
        # TODO: implement confirmation
        return ToolConfirmationDetails(
            type="mcp",
            message=f"Do you want to execute the tool {self.name} with the following input: {tool_input}?",
            on_confirm_callback=lambda outcome: None
        )

    async def execute(self, tool_input: dict[str, Any]) -> ToolResult:
        async with self.mcp_client:
            mcp_results = await self.mcp_client.call_tool(self.name, tool_input)
            
            llm_content = []
            user_display_content = ""
            for mcp_result in mcp_results.content:
                if mcp_result.type == "text":
                    llm_content.append(TextContent(type="text", text=mcp_result.text))
                    user_display_content += mcp_result.text
                elif mcp_result.type == "image":
                    llm_content.append(ImageContent(type="image", data=mcp_result.data, mimeType=mcp_result.mimeType))
                    user_display_content += f"\n[Redacted image]"
                else:
                    raise ValueError(f"Unknown result type: {mcp_result.type}")

            return ToolResult(llm_content=llm_content, user_display_content=user_display_content)