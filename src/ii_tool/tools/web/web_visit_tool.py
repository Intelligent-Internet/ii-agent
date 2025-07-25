from typing import Any
from ii_tool.core.config import WebVisitConfig
from ii_tool.tools.base import BaseTool, ToolResult
from ii_tool.tools.web.clients.web_visit_client import (
    create_visit_client,
    WebpageVisitException,
    ContentExtractionError,
    NetworkError,
)

# Name
NAME = "visit_webpage"
DISPLAY_NAME = "Web Visit"

# Tool description
DESCRIPTION = "You should call this tool when you need to visit a webpage and extract its content. Returns webpage content as text."

# Input schema
INPUT_SCHEMA = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The url of the webpage to visit.",
            }
        },
        "required": ["url"],
    }


class WebVisitTool(BaseTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = True

    def __init__(
        self,
        settings: WebVisitConfig,
    ):
        self.visit_client = create_visit_client(
            settings=settings,
        )

    async def execute(
        self,
        tool_input: dict[str, Any],
    ) -> ToolResult:
        url = tool_input["url"]
        if "arxiv.org/abs" in url:
            url = "https://arxiv.org/html/" + url.split("/")[-1]

        try:
            output = await self.visit_client.forward_async(url)
            return ToolResult(
                llm_content=output,
                user_display_content=output,
                is_error=False,
            )

        except ContentExtractionError:
            error_msg = f"Failed to extract content from {url} using {self.visit_client.name} tool. Please visit the webpage in a browser to manually verify the content or confirm that none is available."
            return ToolResult(
                llm_content=error_msg,
                user_display_content=f"Failed to extract content from {url}",
                is_error=True,
            )

        except NetworkError:
            error_msg = f"Failed to access {url} using {self.visit_client.name} tool. Please check if the URL is correct and accessible from your browser."
            return ToolResult(
                llm_content=error_msg,
                user_display_content=f"Failed to access {url} due to network error",
                is_error=True,
            )

        except WebpageVisitException:
            error_msg = f"Failed to visit {url} using {self.visit_client.name} tool. Please visit the webpage in a browser to manually verify the content."
            return ToolResult(
                llm_content=error_msg,
                user_display_content=f"Failed to visit {url}",
                is_error=True,
            )

    async def execute_mcp_wrapper(self, url: str):
        return await self._mcp_wrapper(
            tool_input={
                "url": url,
            }
        )