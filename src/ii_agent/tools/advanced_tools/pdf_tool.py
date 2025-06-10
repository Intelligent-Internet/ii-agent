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
    description = """Extract readable text content from PDF files in your workspace.

This tool converts PDF documents into plain text that you can read, analyze, or process further.

Use this tool to:
- Read PDF documents, reports, or research papers
- Extract text for analysis or summarization
- Access content from uploaded PDF files
- Convert PDF content for further processing

Important limitations:
- Only extracts text from text-based PDFs (not scanned documents)
- Cannot perform OCR on image-based or scanned PDFs
- Large files may have output truncated for performance
- Preserves basic text structure but loses formatting

File requirements:
- PDF must be located in the workspace
- Use relative paths from workspace root (e.g., 'uploads/document.pdf')
- File must exist and be a valid PDF format

Best for:
- Academic papers, reports, and text documents
- Extracting quotes or references from PDFs
- Converting PDF content for analysis
- Reading documentation or manuals

Note: For scanned PDFs or images containing text, consider using OCR tools instead."""
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

    def run_impl(
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
