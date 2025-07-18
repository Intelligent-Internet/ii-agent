from typing import Any, Optional
from ii_agent.controller.state import State
from ii_agent.tools.base import LLMTool, ToolImplOutput
from fastmcp import Client

class MCPTool(LLMTool):

    def __init__(self, name, description, input_schema, mcp_client: Client):
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.mcp_client = mcp_client

    def is_read_only(self) -> bool:
        """Message tool is read-only - it only communicates, doesn't modify state."""
        return False

    async def run_impl(
        self,
        tool_input: dict[str, Any],
        state: Optional[State] = None,
    ) -> ToolImplOutput:
        async with self.mcp_client:
            result = await self.mcp_client.call_tool(self.name, tool_input)
            result = result[0]
            if result.type == "text":
                msg = result.text

                # For debug purpose
                print("--------------------------------")
                print(f"MCPTool {self.name} result: {msg}")
                print("--------------------------------")
            else:
                raise ValueError(f"Unknown result type: {result.type}")
            
        return ToolImplOutput(msg, msg, auxiliary_data={"success": True})