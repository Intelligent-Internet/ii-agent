import json
from ii_agent.llm.message_history import MessageHistory
from ii_agent.tools.base import (
    LLMTool,
    ToolImplOutput,
)
from typing import Any, Optional
import os


class TavilySearchTool(LLMTool):
    name = "tavily_web_search"
    description = (
        """Performs a web search using Tavily API and returns the search results."""
    )
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
        self.api_key = os.environ.get("TAVILY_API_KEY", "")
        if not self.api_key:
            print(
                "Warning: TAVILY_API_KEY environment variable not set. Tool may not function correctly."
            )

    def forward(self, query: str) -> str:
        try:
            from tavily import TavilyClient
            from .utils import truncate_content
        except ImportError as e:
            raise ImportError(
                "You must install package `tavily` to run this tool: for instance run `pip install tavily-python`."
            ) from e

        try:
            # Initialize Tavily client
            tavily_client = TavilyClient(api_key=self.api_key)

            # Perform search
            response = tavily_client.search(query=query, max_results=self.max_results)

            # Check if response contains results
            if not response or "results" not in response or not response["results"]:
                return f"No search results found for query: {query}"

            # Format and return the results
            formatted_results = json.dumps(response["results"], indent=4)
            return truncate_content(formatted_results)

        except Exception as e:
            return f"Error searching with Tavily: {str(e)}"

    def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        query = tool_input["query"]
        try:
            output = self.forward(query)
            return ToolImplOutput(
                output,
                f"Search Results with query: {query} successfully retrieved using Tavily",
                auxiliary_data={"success": True},
            )
        except Exception as e:
            return ToolImplOutput(
                f"Error searching the web with Tavily: {str(e)}",
                f"Failed to search the web with query: {query}",
                auxiliary_data={"success": False},
            )
