from ii_agent.tools.base import BaseTool, ToolResult
from typing import Any, Optional
from ii_agent.tools.clients.web_visit_client import (
    create_visit_client,
    WebpageVisitException,
    ContentExtractionError,
    NetworkError,
)
from ii_agent.core.storage.models.settings import Settings


VISIT_WEB_PAGE_MAX_OUTPUT_LENGTH = 40_000

class WebVisitTool(BaseTool):
    name = "visit_webpage"
    description = "You should call this tool when you need to visit a webpage and extract its content. Returns webpage content as text."
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

    def __init__(
        self,
        settings: Optional[Settings] = None,
        max_output_length: int = VISIT_WEB_PAGE_MAX_OUTPUT_LENGTH,
    ):
        self.max_output_length = max_output_length
        self.visit_client = create_visit_client(
            settings=settings, max_output_length=max_output_length
        )

    def is_read_only(self) -> bool:
        return True

    async def should_confirm_execute(self, tool_input: dict[str, Any]):
        return False

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
            )

        except ContentExtractionError:
            error_msg = f"Failed to extract content from {url} using {self.visit_client.name} tool. Please visit the webpage in a browser to manually verify the content or confirm that none is available."
            return ToolResult(
                llm_content=error_msg,
                user_display_content=f"Failed to extract content from {url}",
            )

        except NetworkError:
            error_msg = f"Failed to access {url} using {self.visit_client.name} tool. Please check if the URL is correct and accessible from your browser."
            return ToolResult(
                llm_content=error_msg,
                user_display_content=f"Failed to access {url} due to network error",
            )

        except WebpageVisitException:
            error_msg = f"Failed to visit {url} using {self.visit_client.name} tool. Please visit the webpage in a browser to manually verify the content."
            return ToolResult(
                llm_content=error_msg,
                user_display_content=f"Failed to visit {url}",
            )