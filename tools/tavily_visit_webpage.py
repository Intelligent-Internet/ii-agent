import json
from utils.common import (
    DialogMessages,
    LLMTool,
    ToolImplOutput,
)
from typing import Any, Optional
import os


class TavilyVisitWebpageTool(LLMTool):
    name = "tavily_visit_webpage"
    description = (
        "Visits a webpage at the given url and extracts its content using Tavily API. Returns webpage content as text."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The url of the webpage to visit.",
            }
        },
        "required": ["url"],
    }
    output_type = "string"

    def __init__(self, max_output_length: int = 40000):
        self.max_output_length = max_output_length
        self.api_key = os.environ.get("TAVILY_API_KEY", "")
        if not self.api_key:
            print("Warning: TAVILY_API_KEY environment variable not set. Tool may not function correctly.")

    def forward(self, url: str) -> str:
        try:
            from tavily import TavilyClient
            from .utils import truncate_content
        except ImportError as e:
            raise ImportError(
                "You must install package `tavily` to run this tool: for instance run `pip install tavily`."
            ) from e

        try:
            # Initialize Tavily client
            tavily_client = TavilyClient(api_key=self.api_key)
            
            # Extract webpage content
            response = tavily_client.extract(urls=[url])
            
            # Check if response contains results
            if not response or 'results' not in response or not response['results']:
                return f"No content could be extracted from {url}"
            
            # Extract the content from the first result
            content = json.dumps(response['results'][0], indent=4)
            if not content:
                return f"No textual content could be extracted from {url}"
            
            return truncate_content(content, self.max_output_length)

        except Exception as e:
            return f"Error extracting the webpage content using Tavily: {str(e)}"

    def run_impl(
        self,
        tool_input: dict[str, Any],
        dialog_messages: Optional[DialogMessages] = None,
    ) -> ToolImplOutput:
        url = tool_input["url"]
        output = self.forward(url)
        return ToolImplOutput(
            output,
            f"Webpage {url} successfully visited using Tavily",
            auxiliary_data={"success": True},
        ) 