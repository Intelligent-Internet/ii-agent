"""File reading tool for reading file contents."""

import mimetypes
import pymupdf
import puremagic

from pathlib import Path
from typing import Optional, Any
from ii_tool.core.workspace import WorkspaceManager, FileSystemValidationError
from ii_tool.tools.base import BaseTool, ToolResult, ImageContent
from ii_tool.tools.file_system.utils import encode_image


# Constants
MAX_FILE_READ_LINES = 2000
MAX_LINE_LENGTH = 2000
SUPPORTED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}

# Name
NAME = "Read"
DISPLAY_NAME = "Read file"

# Tool description
DESCRIPTION = f"""Reads and returns the content of a specified file from the local filesystem. Supports text files, images ({', '.join(SUPPORTED_IMAGE_EXTENSIONS)}), and PDF files.

Usage:
- file_path must be an absolute path
- Text/PDF: reads up to {MAX_FILE_READ_LINES} lines with optional offset/limit
  - Use offset and limit parameters for large files to read specific sections
  - Lines longer than {MAX_LINE_LENGTH} chars are truncated
  - Text results are returned in `cat -n` format (line numbers start at 1)
- Images: returns base64-encoded content with MIME type"""

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
            "description": f"Optional number of lines to read from the text file. Use for large files to limit output. Must be 1 or greater. If omitted, reads up to {MAX_FILE_READ_LINES} lines by default"
        },
        "offset": {
            "type": "integer",
            "description": "Optional line number to start reading from (1-based). Use with limit to read specific sections of large files. Must be 1 or greater. If omitted, starts from line 1"
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
    
    # Check for PDF first (specific document type)
    if suffix == '.pdf' or mime_type == 'application/pdf':
        return 'pdf'
    
    # Check for images (but treat SVG as text since it's XML-based)
    image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.ico', '.tiff', '.tga'}
    if suffix in image_extensions or (mime_type and mime_type.startswith('image/') and suffix != '.svg'):
        return 'image'
    
    # Check for known text extensions first (optimization)
    text_extensions = {
        '.txt', '.md', '.rst', '.py', '.js', '.ts', '.html', '.htm', '.css', '.scss', '.sass',
        '.json', '.xml', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf', '.log',
        '.sql', '.sh', '.bash', '.zsh', '.fish', '.ps1', '.bat', '.cmd', '.c', '.cpp', '.cxx',
        '.cc', '.h', '.hpp', '.hxx', '.java', '.kt', '.scala', '.go', '.rs', '.php', '.rb',
        '.pl', '.lua', '.r', '.m', '.swift', '.dart', '.vim', '.tex', '.csv', '.tsv',
        '.dockerfile', '.gitignore', '.gitattributes', '.editorconfig', '.svg', '.makefile'
    }
    if suffix in text_extensions or (mime_type and mime_type.startswith('text/')):
        return 'text'
    
    # Check for known binary extensions
    binary_extensions = {
        # Archives and compressed files
        '.zip', '.tar', '.gz', '.bz2', '.xz', '.7z', '.rar', '.lz4', '.zst',
        # Executables and libraries
        '.exe', '.dll', '.so', '.dylib', '.a', '.lib', '.o', '.obj',
        # Java/JVM files
        '.class', '.jar', '.war', '.ear',
        # Media files
        '.mp4', '.avi', '.mov', '.wmv', '.flv', '.mkv', '.webm', '.m4v',
        '.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a',
        # Microsoft Office (binary formats)
        '.doc', '.xls', '.ppt', '.mdb', '.accdb',
        # OpenDocument (compressed XML)
        '.odt', '.ods', '.odp', '.odg', '.odf',
        # Microsoft Office (XML-based but compressed)
        '.docx', '.xlsx', '.pptx',
        # Other binary formats
        '.bin', '.dat', '.wasm', '.pyc', '.pyo', '.sqlite', '.db', '.dbf',
        # Font files
        '.ttf', '.otf', '.woff', '.woff2', '.eot',
        # 3D and CAD files
        '.stl', '.obj', '.fbx', '.blend', '.dwg', '.dxf'
    }
    if suffix in binary_extensions:
        return 'binary'
    
    # For files with no extension or unknown extensions, use MIME type
    if mime_type:
        if mime_type.startswith('application/'):
            # Most application MIME types are binary
            known_text_apps = {'application/json', 'application/xml', 'application/javascript'}
            if mime_type in known_text_apps:
                return 'text'
            return 'binary'
        elif mime_type.startswith('audio/') or mime_type.startswith('video/'):
            return 'binary'
    
    # Final fallback: content-based detection
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


class UnreadableImageError(Exception):
    """Exception raised when an image is not readable."""
    pass

def _read_image_file(path: Path):
    """Read an image and return base64 encoded content."""

    # Detect actual image format from file content
    try:
        # puremagic.from_file returns a list of matches, get the first one
        magic_info = puremagic.from_file(str(path))[0]
        actual_format = magic_info.extension.lstrip('.').lower()
    except (IndexError, Exception):
        # Fallback to extension-based detection if puremagic fails
        actual_format = path.suffix.lstrip('.').lower()

    # Map imghdr format to MIME type
    format_to_mime = {
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        'gif': 'image/gif',
        'webp': 'image/webp',
    }

    mime_type = None
    # Use detected format, fallback to extension-based detection
    if actual_format and actual_format.lower() in format_to_mime:
        mime_type = format_to_mime[actual_format.lower()]
    else:
        # Fallback to extension-based detection
        mime_type, _ = mimetypes.guess_type(str(path))
    
    if not mime_type:
        raise UnreadableImageError(f"Unreadable image: {path}")

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
        tool_input: dict[str, Any],
    ) -> ToolResult:
        """Implementation of the file reading functionality."""
        file_path = tool_input.get("file_path")
        limit = tool_input.get("limit")
        offset = tool_input.get("offset")

        # Validate parameters
        if offset is not None and offset < 1:
            return ToolResult(
                llm_content="ERROR: Offset must be a positive number (starts from 1)",
                is_error=True
            )
        
        if limit is not None and limit < 1:
            return ToolResult(
                llm_content="ERROR: Limit must be a positive number (greater than 1)",
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
                    user_display_content=full_content,
                    is_error=False
                )
            
            elif file_type == 'pdf':
                full_content = _read_pdf_file(path)
                return ToolResult(
                    llm_content=_truncate_text_content(full_content, offset, limit),
                    user_display_content=full_content,
                    is_error=False
                )
            
            elif file_type == 'image':
                if path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
                    return ToolResult(
                        llm_content=f"ERROR: Unsupported {path.suffix} type. Supported image file types: {', '.join(SUPPORTED_IMAGE_EXTENSIONS)}",
                        is_error=True
                    )
                
                try:
                    image_content = _read_image_file(path)
                except UnreadableImageError as e:
                    return ToolResult(
                        llm_content=f"ERROR: {e}",
                        is_error=True
                    )
                return ToolResult(
                    llm_content=image_content,
                    user_display_content="Image processed by agent successfully.",
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
        return await self._mcp_wrapper(
            tool_input={
                "file_path": file_path,
                "limit": limit,
                "offset": offset,
            }
        )