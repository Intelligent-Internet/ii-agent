from ii_agent.tools.base import BaseTool, ToolResult
from ii_agent.tools.clients.web_search_client import create_search_client
from ii_agent.core.storage.models.settings import Settings
from typing import Any, Optional


class WebSearchTool(BaseTool):
    name = "web_search"
    description = """Performs a web search using a search engine API and returns the search results."""
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The search query to perform."},
        },
        "required": ["query"],
    }
    output_type = "string"

    def __init__(self, settings: Optional[Settings] = None, max_results=5, **kwargs):
        self.max_results = max_results
        self.web_search_client = create_search_client(
            settings=settings, max_results=max_results, **kwargs
        )

    def is_read_only(self) -> bool:
        return True

    async def should_confirm_execute(self, tool_input: dict[str, Any]):
        return False

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
            )
        except Exception as e:
            return ToolResult(
                llm_content=f"Error searching the web with {self.web_search_client.name}: {str(e)}",
                user_display_content=f"Failed to search the web with query: {query}",
            )