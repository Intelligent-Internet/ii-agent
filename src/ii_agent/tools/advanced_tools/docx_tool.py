"""Tool for reading text content from Word (.docx) files."""

import logging
from pathlib import Path
from typing import Any, Optional

try:
    import docx
except ImportError:
    docx = None

from ii_agent.tools.base import (
    DialogMessages,
    LLMTool,
    ToolImplOutput,
)
from ii_agent.tools.utils import truncate_content
from ii_agent.utils import WorkspaceManager

logger = logging.getLogger(__name__)

class ReadWordTool(LLMTool):
    name = "read_word_document"
    description = "Reads the text content from a Microsoft Word document (.docx). Does not support older .doc format."

    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "The path to the Word (.docx) file within the workspace.",
            }
        },
        "required": ["path"],
    }

    def __init__(self, workspace_manager: WorkspaceManager, max_output_length: int = 32768):
        super().__init__()
        if docx is None:
            raise ImportError(
                "The 'python-docx' package is required to use the ReadWordTool. "
                "Please install it using 'pip install python-docx'."
            )
        self.workspace_manager = workspace_manager
        self.max_output_length = max_output_length

    def run_impl(
        self,
        tool_input: dict[str, Any],
        dialog_messages: Optional[DialogMessages] = None,
    ) -> ToolImplOutput:
        file_path_str = tool_input["path"]
        try:
            file_path = self.workspace_manager.workspace_path(Path(file_path_str))

            if not file_path.exists() or not file_path.is_file():
                 raise ToolImplOutput(
                    f"File not found or is not a file: {file_path_str}",
                    f"File not found or is not a file: {file_path_str}",
                    {"success": False, "error": "FileNotFoundError"}
                )

            if not file_path.suffix.lower() == ".docx":
                raise ToolImplOutput(
                    "This tool only supports .docx files. For .doc files, conversion might be needed first.",
                    "This tool only supports .docx files. For .doc files, conversion might be needed first.",
                    {"success": False, "error": "FileNotFoundError"}
                )

            document = docx.Document(str(file_path))
            full_text = "\n".join([para.text for para in document.paragraphs if para.text])

            truncated_text = truncate_content(full_text, self.max_output_length)

            return ToolImplOutput(
                tool_output=truncated_text,
                tool_result_message=f"Successfully read content from {file_path_str}.",
                auxiliary_data={"success": True, "truncated": len(full_text) > len(truncated_text)}
            )

        except FileNotFoundError:
            return ToolImplOutput(
                f"Error: File not found at path {file_path_str}",
                f"File not found at {file_path_str}",
                {"success": False, "error": "FileNotFoundError"}
            )
        except Exception as e:
             return ToolImplOutput(
                f"Error reading Word file: {e.message}",
                f"Error reading Word file: {e.message}",
                {"success": False, "error": e.__class__.__name__}
            )