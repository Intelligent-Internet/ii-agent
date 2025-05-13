from ii_agent.tools.base import (
    LLMTool,
    ToolImplOutput,
)
from typing import Any, Optional
from ii_agent.llm.message_history import MessageHistory
from ii_agent.tools.visit_webpage_client import create_visit_client


class VisitWebpageTool(LLMTool):
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

    def __init__(self, max_output_length: int = 40000):
        self.max_output_length = max_output_length
        self.visit_client = create_visit_client(max_output_length=max_output_length)

    def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        url = tool_input["url"]
        output = self.visit_client.forward(url)
        return ToolImplOutput(
            output,
            f"Webpage {url} successfully visited using {self.visit_client.name}",
            auxiliary_data={"success": True},
        )
