from typing import Any
from ii_tool.core.config import ImageSearchConfig
from ii_tool.tools.base import BaseTool, ToolResult
from ii_tool.tools.web.clients.image_search_client import create_image_search_client


# Name
NAME = "image_search"
DISPLAY_NAME = "Image Search"

# Tool description
DESCRIPTION = """Performs an image search using a search engine API and returns a list of image URLs."""

# Input schema
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "The search query to perform."},
    },
    "required": ["query"],
}


class ImageSearchTool(BaseTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = True

    def __init__(self, settings: ImageSearchConfig, **kwargs):
        self.image_search_client = create_image_search_client(
            settings=settings, **kwargs
        )

    async def execute(
        self,
        tool_input: dict[str, Any],
    ) -> ToolResult:
        query = tool_input["query"]
        try:
            output = await self.image_search_client.forward_async(query)
            return ToolResult(
                llm_content=output,
                user_display_content=f"Image Search Results with query: {query} successfully retrieved using {self.image_search_client.name}",
                is_error=False,
            )
        except Exception as e:
            return ToolResult(
                llm_content=f"Error searching the web with {self.image_search_client.name}: {str(e)}",
                user_display_content=f"Failed to search the web with query: {query}",
                is_error=True,
            )

    async def execute_mcp_wrapper(self, query: str):
        return await self._mcp_wrapper(
            tool_input={
                "query": query,
            }
        )