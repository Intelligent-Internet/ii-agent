"""
File input handling for CLI.

This module provides utilities for handling file inputs and attachments.
"""

import mimetypes
import os
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple


class FileHandler:
    """Handler for file inputs and attachments."""
    
    def __init__(self, workspace_path: Path):
        self.workspace_path = workspace_path
        
        # Supported file types for attachments
        self.supported_text_extensions = {
            '.txt', '.md', '.py', '.js', '.ts', '.html', '.css', '.json', '.xml',
            '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf', '.sh', '.bash',
            '.sql', '.csv', '.log', '.java', '.cpp', '.c', '.h', '.hpp',
            '.rs', '.go', '.php', '.rb', '.swift', '.kt', '.scala', '.r',
            '.dockerfile', '.makefile', '.gitignore', '.env'
        }
        
        self.supported_image_extensions = {
            '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.svg', '.webp'
        }
        
        self.max_text_file_size = 1024 * 1024  # 1MB
        self.max_image_file_size = 10 * 1024 * 1024  # 10MB
    
    def validate_file(self, file_path: str) -> Tuple[bool, Optional[str]]:
        """Validate a file for attachment."""
        path = Path(file_path)
        
        # Check if file exists
        if not path.exists():
            return False, f"File not found: {file_path}"
        
        # Check if it's a file (not directory)
        if not path.is_file():
            return False, f"Not a file: {file_path}"
        
        # Check file extension
        extension = path.suffix.lower()
        if extension not in self.supported_text_extensions and extension not in self.supported_image_extensions:
            return False, f"Unsupported file type: {extension}"
        
        # Check file size
        file_size = path.stat().st_size
        if extension in self.supported_text_extensions:
            if file_size > self.max_text_file_size:
                return False, f"Text file too large: {file_size} bytes (max: {self.max_text_file_size})"
        elif extension in self.supported_image_extensions:
            if file_size > self.max_image_file_size:
                return False, f"Image file too large: {file_size} bytes (max: {self.max_image_file_size})"
        
        return True, None
    
    def process_attachments(self, attachments: List[str]) -> Tuple[List[str], List[str]]:
        """Process and validate attachment files."""
        valid_attachments = []
        errors = []
        
        for attachment in attachments:
            # Resolve relative paths
            if not os.path.isabs(attachment):
                attachment = str(self.workspace_path / attachment)
            
            is_valid, error = self.validate_file(attachment)
            if is_valid:
                valid_attachments.append(attachment)
            else:
                errors.append(error)
        
        return valid_attachments, errors
    
    def read_instruction_file(self, file_path: str) -> Tuple[Optional[str], Optional[str]]:
        """Read instruction from file."""
        path = Path(file_path)
        
        # Resolve relative paths
        if not path.is_absolute():
            path = self.workspace_path / path
        
        try:
            if not path.exists():
                return None, f"Instruction file not found: {file_path}"
            
            if not path.is_file():
                return None, f"Not a file: {file_path}"
            
            # Check file size
            file_size = path.stat().st_size
            if file_size > self.max_text_file_size:
                return None, f"Instruction file too large: {file_size} bytes"
            
            # Read file content
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            
            return content, None
            
        except UnicodeDecodeError:
            return None, f"Unable to read file as text: {file_path}"
        except Exception as e:
            return None, f"Error reading file: {e}"
    
    def get_file_info(self, file_path: str) -> Dict[str, Any]:
        """Get information about a file."""
        path = Path(file_path)
        
        try:
            stat = path.stat()
            mime_type, _ = mimetypes.guess_type(str(path))
            
            return {
                'path': str(path),
                'name': path.name,
                'size': stat.st_size,
                'extension': path.suffix.lower(),
                'mime_type': mime_type,
                'is_text': path.suffix.lower() in self.supported_text_extensions,
                'is_image': path.suffix.lower() in self.supported_image_extensions,
                'modified': stat.st_mtime,
            }
        except Exception as e:
            return {
                'path': str(path),
                'name': path.name,
                'error': str(e)
            }
    
    def find_files(self, pattern: str, recursive: bool = True) -> List[str]:
        """Find files matching a pattern."""
        import glob
        
        # Make pattern relative to workspace
        if not os.path.isabs(pattern):
            pattern = str(self.workspace_path / pattern)
        
        try:
            if recursive:
                matches = glob.glob(pattern, recursive=True)
            else:
                matches = glob.glob(pattern)
            
            # Filter out directories and validate files
            valid_files = []
            for match in matches:
                if os.path.isfile(match):
                    is_valid, _ = self.validate_file(match)
                    if is_valid:
                        valid_files.append(match)
            
            return valid_files
            
        except Exception:
            return []
    
    def list_supported_extensions(self) -> Dict[str, List[str]]:
        """List supported file extensions."""
        return {
            'text': sorted(list(self.supported_text_extensions)),
            'image': sorted(list(self.supported_image_extensions))
        }
    
    def get_relative_path(self, file_path: str) -> str:
        """Get relative path from workspace."""
        path = Path(file_path)
        try:
            return str(path.relative_to(self.workspace_path))
        except ValueError:
            return str(path)
    
    def format_file_size(self, size_bytes: int) -> str:
        """Format file size in human-readable format."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
    
    def create_file_summary(self, file_paths: List[str]) -> str:
        """Create a summary of attached files."""
        if not file_paths:
            return "No files attached"
        
        lines = [f"Attached files ({len(file_paths)}):"]
        
        for file_path in file_paths:
            info = self.get_file_info(file_path)
            relative_path = self.get_relative_path(file_path)
            
            if 'error' in info:
                lines.append(f"  ❌ {relative_path} - Error: {info['error']}")
            else:
                size_str = self.format_file_size(info['size'])
                file_type = "📄" if info['is_text'] else "🖼️" if info['is_image'] else "📁"
                lines.append(f"  {file_type} {relative_path} ({size_str})")
        
        return "\n".join(lines)