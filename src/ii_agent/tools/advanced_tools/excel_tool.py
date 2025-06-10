"""Tool for reading data from Excel (.xlsx, .xls) files."""

import logging
from pathlib import Path
from typing import Any, Optional, Dict

try:
    import pandas as pd
except ImportError:
    pd = None

from ii_agent.tools.base import (
    DialogMessages,
    LLMTool,
    ToolImplOutput,
)
from ii_agent.tools.utils import truncate_content
from ii_agent.utils import WorkspaceManager

logger = logging.getLogger(__name__)

class ReadExcelTool(LLMTool):
    name = "read_excel_spreadsheet"
    description = "Reads data from an Excel spreadsheet (.xlsx or .xls) and returns the content of all sheets as text."

    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "The path to the Excel file within the workspace.",
            },
             "max_rows_per_sheet": {
                 "type": "integer",
                 "description": "Optional maximum number of rows to include from each sheet in the output.",
                 "default": 500 # Default to limit output size
            }
        },
        "required": ["path"],
    }

    def __init__(self, workspace_manager: WorkspaceManager, max_output_length: int = 32768):
        super().__init__()
        if pd is None:
            raise ImportError(
                "The 'pandas' package (and its dependencies like 'openpyxl', 'xlrd') is required to use the ReadExcelTool. "
                "Please install it using 'pip install pandas openpyxl xlrd'."
            )
        self.workspace_manager = workspace_manager
        self.max_output_length = max_output_length

    def run_impl(
        self,
        tool_input: dict[str, Any],
        dialog_messages: Optional[DialogMessages] = None,
    ) -> ToolImplOutput:
        file_path_str = tool_input["path"]
        max_rows = tool_input.get("max_rows_per_sheet", 50)
        try:
            file_path = self.workspace_manager.workspace_path(Path(file_path_str))

            # --- Security Check ---
            if not file_path.is_file():
                 raise ToolImplOutput(
                    f"File not found or is not a file: {file_path_str}",
                    f"File not found or is not a file: {file_path_str}",
                    {"success": False, "error": "FileNotFoundError"}
                )
            # ----------------------

            if file_path.suffix.lower() not in [".xlsx", ".xls"]:
                 raise ToolImplOutput(
                    "This tool only supports .xlsx and .xls files.",
                    "This tool only supports .xlsx and .xls files.",
                    {"success": False, "error": "FileNotFoundError"}
                )

            # Read all sheets into a dictionary of DataFrames
            # Use try-except block to handle potential errors during read_excel
            try:
                excel_data: Dict[str, pd.DataFrame] = pd.read_excel(str(file_path), sheet_name=None)
            except Exception as read_error:
                 raise ToolImplOutput(
                    f"Error reading Excel file structure or content: {read_error}",
                    f"Error reading Excel file structure or content: {read_error}",
                    {"success": False, "error": "FileNotFoundError"}
                ) from read_error

            output_parts = []
            total_content_length = 0
            truncated_sheets = False

            for sheet_name, df in excel_data.items():
                sheet_header = f"--- Sheet: {sheet_name} ---"
                # Convert DataFrame to string, limiting rows if necessary
                if max_rows is not None and len(df) > max_rows:
                    sheet_content = df.head(max_rows).to_string(index=False)
                    sheet_content += f"\n... (Sheet truncated to first {max_rows} rows)"
                else:
                    sheet_content = df.to_string(index=False)

                sheet_output = f"{sheet_header}\n{sheet_content}\n"
                total_content_length += len(sheet_output)

                # Check if adding this sheet exceeds max total output length
                if total_content_length > self.max_output_length and output_parts:
                    truncated_sheets = True
                    output_parts.append(f"\n... (Remaining sheets truncated due to output length limit)")
                    break # Stop adding more sheets

                output_parts.append(sheet_output)


            final_output = "\n".join(output_parts)

            # Final truncation if somehow still too long (unlikely with sheet limit logic, but safe)
            final_output_truncated = truncate_content(final_output, self.max_output_length)
            was_truncated = truncated_sheets or (len(final_output) > len(final_output_truncated))

            return ToolImplOutput(
                tool_output=final_output_truncated,
                tool_result_message=f"Successfully read content from Excel file {file_path_str}.",
                auxiliary_data={"success": True, "truncated": was_truncated}
            )

        except FileNotFoundError:
            return ToolImplOutput(
                f"Error: File not found at path {file_path_str}",
                f"File not found at {file_path_str}",
                {"success": False, "error": "FileNotFoundError"}
            )
        except Exception as e:
            return ToolImplOutput(
                f"An unexpected error occurred while reading {file_path_str}: {str(e)}",
                f"Failed to read Excel file {file_path_str}.",
                {"success": False, "error": e.__class__.__name__}
            )