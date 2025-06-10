from ii_agent.llm.message_history import MessageHistory
from ii_agent.tools.base import (
    LLMTool,
    ToolImplOutput,
)
from ii_agent.tools.web_search_client import create_image_search_client
from typing import Any, Optional


class ImageSearchTool(LLMTool):
    name = "image_search"
    description = """Search for images on the web and get a list of image URLs matching your query.

This tool searches the internet for images and returns direct URLs to relevant images.

Use this tool when you need to:
- Find specific images, photos, or graphics on the web
- Gather visual references for a project
- Search for stock photos, illustrations, or diagrams
- Find images of specific objects, people, or concepts
- Collect visual resources for presentations or documents

Features:
- Returns direct URLs to images found on the web
- Supports various search terms (objects, concepts, styles, etc.)
- Provides multiple results per query (configurable limit)
- Searches across public web sources

Important notes:
- Returns only URLs, not the actual image files
- Use visit_webpage or other tools to download images if needed
- Respect copyright and usage rights for any images you find
- Results depend on availability of images matching your query

Example queries:
- "modern office interior design"
- "data visualization charts"
- "mountain landscape photography"
- "abstract geometric patterns"

The tool returns an array of image URLs that you can reference or download."""
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The search query to perform."},
        },
        "required": ["query"],
    }
    output_type = "array"

    def __init__(self, max_results=5, **kwargs):
        self.max_results = max_results
        self.image_search_client = create_image_search_client(
            max_results=max_results, **kwargs
        )

    def is_available(self):
        return self.image_search_client

    def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        query = tool_input["query"]
        try:
            output = self.image_search_client.forward(query)
            return ToolImplOutput(
                output,
                f"Image Search Results with query: {query} successfully retrieved using {self.image_search_client.name}",
                auxiliary_data={"success": True},
            )
        except Exception as e:
            return ToolImplOutput(
                f"Error searching the web with {self.image_search_client.name}: {str(e)}",
                f"Failed to search the web with query: {query}",
                auxiliary_data={"success": False},
            )
