from ii_agent.llm.message_history import MessageHistory
from ii_agent.tools.base import (
    LLMTool,
    ToolImplOutput,
)
from ii_agent.tools.web_search_client import create_search_client
from typing import Any, Optional


class WebSearchTool(LLMTool):
    name = "web_search"
    description = """Search the web for current information, facts, news, or any topic not in your knowledge base.

This tool performs web searches and returns relevant results including:
- Web page titles and snippets
- URLs for each result
- Brief descriptions of the content

Use this tool when you need to:
- Find current information (news, events, updates)
- Research topics beyond your training data
- Verify facts or get latest information
- Find official documentation or resources
- Discover solutions to specific problems

The tool returns the top search results formatted with titles, URLs, and content snippets. 
You can then use the visit_webpage tool to read the full content of specific pages if needed."""
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

    def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        query = tool_input["query"]
        try:
            output = self.web_search_client.forward(query)
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
