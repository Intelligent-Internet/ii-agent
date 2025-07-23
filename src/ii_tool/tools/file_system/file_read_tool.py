"""File reading tool for reading file contents."""

import mimetypes
import pymupdf

from pathlib import Path
from typing import Optional
from ii_tool.core.workspace import WorkspaceManager, FileSystemValidationError
from ii_tool.tools.base import BaseTool, ToolResult, ImageContent
from ii_tool.tools.file_system.utils import encode_image


# Constants
MAX_FILE_READ_LINES = 2000
MAX_LINE_LENGTH = 2000

# Name
NAME = "Read"
DISPLAY_NAME = "Read file"

# Tool description
DESCRIPTION = f"""Reads and returns the content of a specified file from the local filesystem. Handles text files, images (PNG, JPG, GIF, WEBP, SVG, BMP), and PDF files.

Usage:
- The file_path parameter must be an absolute path, not a relative path
- For text files and PDFs: reads up to {MAX_FILE_READ_LINES} lines by default with optional offset/limit parameters
- For images: returns base64-encoded content with MIME type information
- For PDFs: extracts and returns readable text content (falls back to base64 if text extraction fails)
- Any lines longer than {MAX_LINE_LENGTH} characters will be truncated
- Results are returned using cat -n format, with line numbers starting at 1
- If you read a file that exists but has empty contents you will receive a system reminder warning in place of file contents."""

# Input schema
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "file_path": {
            "type": "string",
            "description": "The absolute path to the file to read"
        },
        "limit": {
            "type": "integer",
            "description": "The number of lines to read. Only provide if the file is too large to read at once"
        },
        "offset": {
            "type": "integer",
            "description": "The line number to start reading from. Only provide if the file is too large to read at once"
        }
    },
    "required": ["file_path"]
}

def _is_binary_file(file_path: Path) -> bool:
    """Determine if a file is binary by checking its content."""
    try:
        with open(file_path, 'rb') as f:
            chunk = f.read(4096)  # Read first 4KB
            if not chunk:
                return False  # Empty file is not binary
            
            # Check for null bytes (strong binary indicator)
            if b'\x00' in chunk:
                return True
            
            # Count non-printable characters
            non_printable = sum(1 for byte in chunk 
                                if byte < 9 or (13 < byte < 32))
            
            # If >30% non-printable characters, consider it binary
            return non_printable / len(chunk) > 0.3
    except (OSError, IOError):
        return False

def _detect_file_type(file_path: Path) -> str:
    """Detect the type of file based on extension and MIME type."""
    suffix = file_path.suffix.lower()
    mime_type, _ = mimetypes.guess_type(str(file_path))
    
    # Check for images
    image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.bmp'}
    if suffix in image_extensions or (mime_type and mime_type.startswith('image/')):
        return 'image'
    
    # Check for PDF
    if suffix == '.pdf' or mime_type == 'application/pdf':
        return 'pdf'
    
    # Check for known binary extensions
    binary_extensions = {
        '.zip', '.tar', '.gz', '.exe', '.dll', '.so', '.class', '.jar', '.war',
        '.7z', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.odt', '.ods',
        '.odp', '.bin', '.dat', '.obj', '.o', '.a', '.lib', '.wasm', '.pyc', '.pyo'
    }
    if suffix in binary_extensions:
        return 'binary'
    
    # Check if file is binary by content
    if _is_binary_file(file_path):
        return 'binary'
    
    return 'text'

def _read_pdf_file(path: Path):
    """Read a PDF file and return the content."""
    doc = pymupdf.open(path)
    text = ""
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        text += page.get_text("text")
    doc.close()

    if text == "":
        return "[PDF file is empty or no readable text could be extracted]"

    return text

def _read_image_file(path: Path):
    """Read an image and return base64 encoded content."""
    
    # Get MIME type
    mime_type, _ = mimetypes.guess_type(str(path))
    if not mime_type:
        mime_type = "image/png"  # Default to PNG if type cannot be determined
    
    # Encode to base64
    base64_image = encode_image(str(path))
    
    image_content = ImageContent(
        type="image",
        mime_type=mime_type,
        data=base64_image,
    )

    return [image_content]
    
def _truncate_text_content(content: str, offset: Optional[int] = None, limit: Optional[int] = None):
    """Truncate text content with optional line range."""
    lines = content.split('\n')
    
    # Remove trailing newlines from each line for processing
    lines = [line.rstrip('\n\r') for line in lines]
    original_line_count = len(lines)
    
    # Handle empty file
    if original_line_count == 0:
        return '[Empty file]'
    
    # Apply offset and limit
    start_line = offset - 1 if offset is not None else 0 # offset starts at 1, need to subtract 1
    effective_limit = limit if limit is not None else MAX_FILE_READ_LINES
    end_line = min(start_line + effective_limit, original_line_count)
    
    # Ensure we don't go beyond array bounds
    actual_start = min(start_line, original_line_count)
    selected_lines = lines[actual_start:end_line]
    
    # Truncate long lines and format with line numbers
    lines_truncated_in_length = False
    formatted_lines = []
    
    for i, line in enumerate(selected_lines):
        line_number = actual_start + i + 1  # 1-based line numbers
        
        if len(line) > MAX_LINE_LENGTH:
            lines_truncated_in_length = True
            line = line[:MAX_LINE_LENGTH] + '... [truncated]'
        
        formatted_lines.append(f"{line_number:6d}\t{line}")
    
    # Check if content was truncated
    content_range_truncated = end_line < original_line_count
    
    # Build content with headers if truncated
    content_parts = []
    if content_range_truncated:
        content_parts.append(
            f"[File content truncated: showing lines {actual_start + 1}-{end_line} "
            f"of {original_line_count} total lines. Use offset/limit parameters to view more.]"
        )
    elif lines_truncated_in_length:
        content_parts.append(
            f"[File content partially truncated: some lines exceeded maximum "
            f"length of {MAX_LINE_LENGTH} characters.]"
        )
    
    content_parts.extend(formatted_lines)
    truncated_content = '\n'.join(content_parts)
    
    return truncated_content


class FileReadTool(BaseTool):
    """Tool for reading file contents with optional line range specification."""
    
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = True

    def __init__(self, workspace_manager: WorkspaceManager):
        self.workspace_manager = workspace_manager

    async def execute(
        self,
        file_path: str,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> ToolResult:
        """Implementation of the file reading functionality."""

        # Validate parameters
        if offset is not None and offset < 0:
            return ToolResult(
                llm_content="ERROR: Offset must be a non-negative number",
                is_error=True
            )
        
        if limit is not None and limit <= 0:
            return ToolResult(
                llm_content="ERROR: Limit must be a positive number",
                is_error=True
            )

        try:
            self.workspace_manager.validate_existing_file_path(file_path)

            path = Path(file_path).resolve()
        
            # Detect file type
            file_type = _detect_file_type(path)
            if file_type == 'binary':
                return ToolResult(
                    llm_content=f"ERROR: Cannot display content of binary file: {path}",
                    is_error=True
                )

            elif file_type == 'text':
                full_content = path.read_text(encoding='utf-8')
                return ToolResult(
                    llm_content=_truncate_text_content(full_content, offset, limit),
                    is_error=False
                )
            
            elif file_type == 'pdf':
                full_content = _read_pdf_file(path)
                return ToolResult(
                    llm_content=_truncate_text_content(full_content, offset, limit),
                    is_error=False
                )
            
            elif file_type == 'image':
                return ToolResult(
                    llm_content=_read_image_file(path),
                    is_error=False
                )
            
            else:
                return ToolResult(
                    llm_content=f"ERROR: Unsupported file type: {file_type}",
                    is_error=True
                )

        except (FileSystemValidationError) as e:
            return ToolResult(
                llm_content=f"ERROR: {e}",
                is_error=True
            )

    async def execute_mcp_wrapper(
        self,
        file_path: str,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ):
        return await self._mcp_wrapper(file_path, limit, offset)