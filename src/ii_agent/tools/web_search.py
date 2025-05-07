from ii_agent.llm.message_history import MessageHistory
from ii_agent.tools.base import (
    LLMTool,
    ToolImplOutput,
)
from typing import Any, Optional


class DuckDuckGoSearchTool(LLMTool):
    name = "web_search"
    description = """Performs a duckduckgo web search based on your query (think a Google search) then returns the top search results."""
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The search query to perform."},
        },
        "required": ["query"],
    }
    output_type = "string"

    def __init__(self, max_results=10, **kwargs):
        self.max_results = max_results
        try:
            from duckduckgo_search import DDGS
        except ImportError as e:
            raise ImportError(
                "You must install package `duckduckgo-search` to run this tool: for instance run `pip install duckduckgo-search`."
            ) from e
        self.ddgs = DDGS(**kwargs)

    def forward(self, query: str) -> str:
        results = self.ddgs.text(query, max_results=self.max_results)
        if len(results) == 0:
            raise Exception("No results found! Try a less restrictive/shorter query.")
        postprocessed_results = [
            f"[{result['title']}]({result['href']})\n{result['body']}"
            for result in results
        ]
        return "## Search Results\n\n" + "\n\n".join(postprocessed_results)

    def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        query = tool_input["query"]
        try:
            results = self.ddgs.text(query, max_results=self.max_results)
            if len(results) == 0:
                raise Exception(
                    "No results found! Try a less restrictive/shorter query."
                )
            postprocessed_results = [
                f"[{result['title']}]({result['href']})\n{result['body']}"
                for result in results
            ]
            return ToolImplOutput(
                "## Search Results\n\n" + "\n\n".join(postprocessed_results),
                f"Search Results with query: {query} successfully retrieved",
                auxiliary_data={"success": True},
            )
        except Exception as e:
            return ToolImplOutput(
                f"Error searching the web: {str(e)}",
                f"Failed to search the web with query: {query}",
                auxiliary_data={"success": False},
            )
