from pathlib import Path
from typing import Any, Optional
import pymupdf

from ii_agent.llm.message_history import MessageHistory
from ii_agent.tools.base import (
    LLMTool,
    ToolImplOutput,
)
from ii_agent.utils import WorkspaceManager


class PdfTextExtractTool(LLMTool):
    name = "pdf_text_extract"
    description = "Extracts text content from a PDF file located in the workspace."
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "The relative path to the PDF file within the workspace (e.g., 'uploads/my_resume.pdf').",
            }
        },
        "required": ["file_path"],
    }

    def __init__(
        self, workspace_manager: WorkspaceManager, max_output_length: int = 15000
    ):
        super().__init__()
        self.workspace_manager = workspace_manager
        self.max_output_length = max_output_length

    async def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        relative_file_path = tool_input["file_path"]
        # Ensure the path is treated as relative to the workspace root
        full_file_path = self.workspace_manager.workspace_path(Path(relative_file_path))

        if not full_file_path.exists():
            return ToolImplOutput(
                f"Error: File not found at {relative_file_path}",
                f"File not found at {relative_file_path}",
                {"success": False, "error": "File not found"},
            )
        if not full_file_path.is_file():
            return ToolImplOutput(
                f"Error: Path {relative_file_path} is not a file.",
                f"Path {relative_file_path} is not a file.",
                {"success": False, "error": "Path is not a file"},
            )
        if full_file_path.suffix.lower() != ".pdf":
            return ToolImplOutput(
                f"Error: File {relative_file_path} is not a PDF.",
                f"File {relative_file_path} is not a PDF.",
                {"success": False, "error": "Not a PDF file"},
            )

        try:
            doc = pymupdf.open(full_file_path)
            text = ""
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                text += page.get_text("text")
            doc.close()

            if len(text) > self.max_output_length:
                text = (
                    text[: self.max_output_length]
                    + "\n... (content truncated due to length)"
                )

            return ToolImplOutput(
                text,
                f"Successfully extracted text from {relative_file_path}",
                {"success": True, "extracted_chars": len(text)},
            )
        except Exception as e:
            return ToolImplOutput(
                f"Error extracting text from PDF {relative_file_path}: {str(e)}",
                f"Failed to extract text from {relative_file_path}",
                {"success": False, "error": str(e)},
            )
