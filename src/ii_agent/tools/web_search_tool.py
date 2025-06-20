from ii_agent.llm.message_history import MessageHistory
from ii_agent.tools.base import (
    LLMTool,
    ToolImplOutput,
)
from ii_agent.tools.web_search_client import create_search_client
from typing import Any, Optional


class WebSearchTool(LLMTool):
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

    def __init__(self, max_results=5, **kwargs):
        self.max_results = max_results
        self.web_search_client = create_search_client(max_results=max_results, **kwargs)

    async def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        query = tool_input["query"]
        try:
            output = await self.web_search_client.forward_async(query)
            return ToolImplOutput(
                output,
                f"Search Results with query: {query} successfully retrieved using {self.web_search_client.name}",
                auxiliary_data={"success": True},
            )
        except Exception as e:
            return ToolImplOutput(
                f"Error searching the web with {self.web_search_client.name}: {str(e)}",
                f"Failed to search the web with query: {query}",
                auxiliary_data={"success": False},
            )
