from typing import Any, Optional
from ii_agent.llm.message_history import MessageHistory
from ii_agent.tools.base import (
    LLMTool,
    ToolImplOutput,
)
from .markdown_converter import MarkdownConverter
from ii_agent.utils import WorkspaceManager


class TextInspectorTool(LLMTool):
    name = "get_text_from_local_file"
    description = """Use this tool to get the text content from a local file. Supported file types: [".xlsx", ".pptx", ".flac", ".pdf", ".docx"]
Note:
- This tool works only with the supported file types listed above. 
- For other file types, use other tools if available or you need to read by yourself.
"""

    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "The path to the file you want to read.",
            },
        },
        "required": ["file_path"],
    }

    def __init__(self, workspace_manager: WorkspaceManager, text_limit: int = 100000):
        self.text_limit = text_limit
        self.md_converter = MarkdownConverter()
        self.workspace_manager = workspace_manager

    def forward(self, file_path: str) -> str:
        # Convert relative path to absolute path using workspace_manager
        abs_path = str(self.workspace_manager.workspace_path(file_path))
        result = self.md_converter.convert(abs_path)

        if file_path[-4:] in [".png", ".jpg"]:
            raise Exception(
                "Cannot use this tool with images: use display_image instead!"
            )

        if ".zip" in file_path:
            return result.text_content

        return result.text_content

    async def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        file_path = tool_input["file_path"]

        try:
            output = self.forward(file_path)
            return ToolImplOutput(
                output,
                f"Successfully inspected file {file_path}",
                auxiliary_data={"success": True},
            )
        except Exception as e:
            return ToolImplOutput(
                f"Error inspecting file: {str(e)}",
                f"Failed to inspect file {file_path}",
                auxiliary_data={"success": False},
            )
