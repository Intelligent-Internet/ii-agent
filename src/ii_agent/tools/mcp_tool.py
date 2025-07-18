from typing import Any
from ii_agent.tools.base import BaseTool, ToolResult, TextContent, ImageContent
from fastmcp import Client

class MCPTool(BaseTool):

    def __init__(self, name: str, description: str, input_schema: dict[str, Any], mcp_client: Client):
        super().__init__(name, description, input_schema)
        self.mcp_client = mcp_client

    def is_read_only(self) -> bool:
        # TODO: implement read-only
        return False

    def should_confirm_execute(self, tool_input):
        # TODO: implement confirmation
        return False

    async def execute(self, tool_input):
        async with self.mcp_client:
            mcp_results = await self.mcp_client.call_tool(self.name, tool_input)
            
            llm_content = []
            user_display_content = ""
            for mcp_result in mcp_results:
                if mcp_result.type == "text":
                    llm_content.append(TextContent(type="text", text=mcp_result.text))
                    user_display_content += mcp_result.text
                elif mcp_result.type == "image":
                    llm_content.append(ImageContent(type="image", data=mcp_result.data, mimeType=mcp_result.mimeType))
                    user_display_content += f"\n[Redacted image]"
                else:
                    raise ValueError(f"Unknown result type: {mcp_result.type}")

            return ToolResult(llm_content=llm_content, user_display_content=user_display_content)