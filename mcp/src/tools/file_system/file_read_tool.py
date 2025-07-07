"""File reading tool for reading file contents."""

import base64
import mimetypes
import PyPDF2

from pathlib import Path
from typing import Annotated, Optional, Dict, Any
from pydantic import Field
from src.core.workspace import WorkspaceManager
from src.tools.constants import MAX_FILE_READ_LINES, MAX_LINE_LENGTH
from .base import BaseFileSystemTool
from .utils import encode_image


DESCRIPTION = f"""Reads and returns the content of a specified file from the local filesystem. Handles text files, images (PNG, JPG, GIF, WEBP, SVG, BMP), and PDF files.

Usage:
- The file_path parameter must be an absolute path, not a relative path
- For text files and PDFs: reads up to {MAX_FILE_READ_LINES} lines by default with optional offset/limit parameters
- For images: returns base64-encoded content with MIME type information
- For PDFs: extracts and returns readable text content (falls back to base64 if text extraction fails)
- Any lines longer than {MAX_LINE_LENGTH} characters will be truncated
- Results are returned using cat -n format, with line numbers starting at 1
- If you read a file that exists but has empty contents you will receive a system reminder warning in place of file contents."""


class FileReadTool(BaseFileSystemTool):
    """Tool for reading file contents with optional line range specification."""
    
    name = "Read"
    description = DESCRIPTION
    
    def __init__(self, workspace_manager: WorkspaceManager):
        super().__init__(workspace_manager)

    def _detect_file_type(self, file_path: Path) -> str:
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
        if self._is_binary_file(file_path):
            return 'binary'
        
        return 'text'

    def _is_binary_file(self, file_path: Path) -> bool:
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

    def _read_text_file(self, file_path: Path, offset: Optional[int] = None, 
                       limit: Optional[int] = None) -> Dict[str, Any]:
        """Read a text file with optional line range."""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()
            
            # Remove trailing newlines from each line for processing
            lines = [line.rstrip('\n\r') for line in lines]
            original_line_count = len(lines)
            
            # Handle empty file
            if original_line_count == 0:
                return {
                    'content': '[Empty file]',
                    'is_truncated': False,
                    'original_line_count': 0,
                    'lines_shown': [1, 0]
                }
            
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
            is_truncated = content_range_truncated or lines_truncated_in_length
            
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
            content = '\n'.join(content_parts)
            
            return {
                'content': content,
                'is_truncated': is_truncated,
                'original_line_count': original_line_count,
                'lines_shown': [actual_start + 1, end_line]
            }
            
        except UnicodeDecodeError:
            return {
                'content': f"Error: File appears to be binary or uses unsupported encoding",
                'is_truncated': False,
                'original_line_count': 0,
                'lines_shown': [1, 0]
            }

    def _read_pdf_file(self, file_path: Path, offset: Optional[int] = None, 
                       limit: Optional[int] = None) -> Dict[str, Any]:
        """Extract text from a PDF file with optional line range."""
        with open(file_path, 'rb') as f:
            pdf_reader = PyPDF2.PdfReader(f)
            
            # Extract text from all pages
            text_content = []
            for page in pdf_reader.pages:
                try:
                    page_text = page.extract_text()
                    if page_text.strip():  # Only add non-empty pages
                        text_content.append(page_text.strip())
                except Exception:
                    # Skip pages that can't be extracted
                    continue
            
            if not text_content:
                return {
                    'content': '[PDF contains no extractable text]',
                    'is_truncated': False,
                    'original_line_count': 0,
                    'lines_shown': [1, 0]
                }
            
            # Join all pages and split into lines
            full_text = '\n\n'.join(text_content)
            lines = full_text.split('\n')
            original_line_count = len(lines)
            
            # Apply offset and limit (same logic as text files)
            start_line = offset if offset is not None else 0
            effective_limit = limit if limit is not None else MAX_FILE_READ_LINES
            end_line = min(start_line + effective_limit, original_line_count)
            
            # Ensure we don't go beyond array bounds
            actual_start = min(start_line, original_line_count)
            selected_lines = lines[actual_start:end_line]
            
            # Format with line numbers and handle long lines
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
            is_truncated = content_range_truncated or lines_truncated_in_length
            
            # Build content with headers if truncated
            content_parts = []
            content_parts.append("[Extracted text from PDF]")
            
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
            content = '\n'.join(content_parts)
            
            return {
                'content': content,
                'is_truncated': is_truncated,
                'original_line_count': original_line_count,
                'lines_shown': [actual_start + 1, end_line]
            }

    def _read_image_file(self, file_path: Path) -> Dict[str, Any]:
        """Read an image and return base64 encoded content."""
        
        # Get MIME type
        mime_type, _ = mimetypes.guess_type(str(file_path))
        if not mime_type:
            mime_type = "image/png"  # Default to PNG if type cannot be determined
        
        # Encode to base64
        base64_image = encode_image(str(file_path))
        
        return {
            "type": "base64",
            "media_type": mime_type,
            "data": base64_image,
        }

    def run_impl(
        self,
        file_path: Annotated[str, Field(description="The absolute path to the file to read")],
        limit: Annotated[Optional[int], Field(description="The number of lines to read. Only provide if the file is too large to read at once.")] = None,
        offset: Annotated[Optional[int], Field(description="The line number to start reading from. Only provide if the file is too large to read at once")] = None,
    ):
        """Implementation of the file reading functionality."""
        try:
            # Convert to Path object
            path = Path(file_path).resolve()
            
            # Check if file exists
            if not path.exists():
                return f"Error: File not found: {file_path}"
            
            # Check if it's a directory
            if path.is_dir():
                return f"Error: Path is a directory, not a file: {file_path}"
            
            # ensure file is within workspace
            if not self.workspace_manager.validate_boundary(path):
                return f"Error: File path must be within workspace: {file_path}"
            
            # Validate parameters
            if offset is not None and offset < 0:
                return "Error: Offset must be a non-negative number"
            
            if limit is not None and limit <= 0:
                return "Error: Limit must be a positive number"
            
            # Detect file type
            file_type = self._detect_file_type(path)
            if file_type == 'binary':
                return f"Cannot display content of binary file: {path}"
            
            elif file_type == 'text':
                result = self._read_text_file(path, offset, limit)
                return result['content']
            
            elif file_type == 'pdf':
                result = self._read_pdf_file(path, offset, limit)
                return result['content']
            
            elif file_type == 'image':
                result = self._read_image_file(path)
                return result
            
            else:
                return f"Error: Unsupported file type: {file_type}"
                
        except Exception as e:
            return f"Error processing file: {str(e)}"