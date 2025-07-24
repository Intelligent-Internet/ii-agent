from typing import Any
from ii_tool.core.config import WebSearchConfig
from ii_tool.tools.base import BaseTool, ToolResult
from ii_tool.tools.web.clients.web_search_client import create_search_client


# Name
NAME = "web_search"
DISPLAY_NAME = "Web Search"

# Tool description
DESCRIPTION = """Performs a web search using a search engine API and returns the search results."""

# Input schema
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "The search query to perform."},
    },
    "required": ["query"],
}

    
class WebSearchTool(BaseTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = True

    def __init__(self, settings: WebSearchConfig, **kwargs):
        self.web_search_client = create_search_client(
            settings=settings, **kwargs
        )

    async def execute(
        self,
        tool_input: dict[str, Any],
    ) -> ToolResult:
        query = tool_input["query"]
        try:
            output = await self.web_search_client.forward_async(query)
            return ToolResult(
                llm_content=output,
                user_display_content=output,
                is_error=False,
            )
        except Exception as e:
            return ToolResult(
                llm_content=f"Error searching the web with {self.web_search_client.name}: {str(e)}",
                user_display_content=f"Failed to search the web with query: {query}",
                is_error=True,
            )

    async def execute_mcp_wrapper(self, query: str):
        return await self._mcp_wrapper(
            tool_input={
                "query": query,
            }
        )