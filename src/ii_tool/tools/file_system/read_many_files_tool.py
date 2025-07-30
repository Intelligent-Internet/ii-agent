"""Tool for reading multiple files at once using paths or glob patterns."""

import glob
from pathlib import Path
from typing import Optional, Any, List
from ii_tool.core.workspace import WorkspaceManager, FileSystemValidationError
from ii_tool.tools.base import BaseTool, ToolResult
from ii_tool.tools.file_system.file_read_tool import (
    _detect_file_type, 
    _read_pdf_file, 
    _read_image_file, 
    _truncate_text_content
)


# Constants
MAX_FILES = 50
MAX_TOTAL_CONTENT_SIZE = 500000  # 500KB limit for total content
DEFAULT_EXCLUDES = [
    "**/node_modules/**",
    "**/.git/**",
    "**/.vscode/**",
    "**/.idea/**",
    "**/venv/**",
    "**/__pycache__/**",
    "**/*.pyc",
    "**/*.pyo",
    "**/dist/**",
    "**/build/**",
    "**/.next/**",
    "**/.nuxt/**"
]

# Name
NAME = "ReadManyFiles"
DISPLAY_NAME = "Read many files"

# Tool description
DESCRIPTION = """Reads content from multiple files specified by paths or glob patterns. Useful for analyzing codebases, reviewing documentation, or gathering context from multiple files at once.

Usage:
- Provide array of file paths or glob patterns in 'paths' parameter
- Optionally specify 'include' patterns to include additional files
- Optionally specify 'exclude' patterns to exclude specific files/directories
- Set 'recursive' to true for recursive directory searches (default: true)
- Set 'use_default_excludes' to false to disable default exclusion patterns
- Files are processed in alphabetical order with clear separators
- Binary files are automatically skipped unless explicitly requested
- Total content size is limited to prevent memory issues"""

# Input schema
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "paths": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Array of file paths or glob patterns to read"
        },
        "include": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Additional glob patterns to include files"
        },
        "exclude": {
            "type": "array", 
            "items": {"type": "string"},
            "description": "Glob patterns to exclude files/directories"
        },
        "recursive": {
            "type": "boolean",
            "description": "Search directories recursively (default: true)"
        },
        "use_default_excludes": {
            "type": "boolean", 
            "description": "Apply default exclusion patterns for common build/cache directories (default: true)"
        },
        "include_binary": {
            "type": "boolean",
            "description": "Include binary files in results (default: false)"
        }
    },
    "required": ["paths"]
}


def _discover_files(
    paths: List[str], 
    workspace_path: Path,
    include: Optional[List[str]] = None,
    exclude: Optional[List[str]] = None,
    recursive: bool = True,
    use_default_excludes: bool = True
) -> List[Path]:
    """Discover files based on paths and patterns."""
    discovered_files = set()
    
    # Process main paths
    for path_pattern in paths:
        if path_pattern.startswith('/'):
            # Absolute path
            pattern_path = Path(path_pattern)
            if pattern_path.is_file():
                discovered_files.add(pattern_path)
            else:
                # Treat as glob pattern
                matches = glob.glob(path_pattern, recursive=recursive)
                for match in matches:
                    match_path = Path(match)
                    if match_path.is_file():
                        discovered_files.add(match_path)
        else:
            # Relative path - search within workspace
            full_pattern = workspace_path / path_pattern
            if full_pattern.is_file():
                discovered_files.add(full_pattern)
            else:
                # Use glob pattern
                pattern_str = str(workspace_path / path_pattern)
                matches = glob.glob(pattern_str, recursive=recursive)
                for match in matches:
                    match_path = Path(match)
                    if match_path.is_file():
                        discovered_files.add(match_path)
    
    # Process include patterns
    if include:
        for include_pattern in include:
            if include_pattern.startswith('/'):
                matches = glob.glob(include_pattern, recursive=recursive)
            else:
                pattern_str = str(workspace_path / include_pattern)
                matches = glob.glob(pattern_str, recursive=recursive)
            
            for match in matches:
                match_path = Path(match)
                if match_path.is_file():
                    discovered_files.add(match_path)
    
    # Apply exclusions
    exclude_patterns = []
    if use_default_excludes:
        exclude_patterns.extend(DEFAULT_EXCLUDES)
    if exclude:
        exclude_patterns.extend(exclude)
    
    if exclude_patterns:
        filtered_files = set()
        for file_path in discovered_files:
            should_exclude = False
            for exclude_pattern in exclude_patterns:
                # Convert to relative path for pattern matching
                try:
                    rel_path = file_path.relative_to(workspace_path)
                    if rel_path.match(exclude_pattern) or str(rel_path).find(exclude_pattern.replace('*', '')) != -1:
                        should_exclude = True
                        break
                except ValueError:
                    # File is outside workspace, check absolute path
                    if file_path.match(exclude_pattern):
                        should_exclude = True
                        break
            
            if not should_exclude:
                filtered_files.add(file_path)
        
        discovered_files = filtered_files
    
    # Sort files for consistent output
    return sorted(list(discovered_files))


def _read_file_content(file_path: Path, include_binary: bool = False) -> tuple[str, bool]:
    """Read content from a single file. Returns (content, is_error)."""
    try:
        file_type = _detect_file_type(file_path)
        
        if file_type == 'binary' and not include_binary:
            return f"[Skipped binary file: {file_path}]", False
        elif file_type == 'binary':
            return f"[Binary file: {file_path} - content not displayable]", False
        elif file_type == 'text':
            content = file_path.read_text(encoding='utf-8')
            return _truncate_text_content(content), False
        elif file_type == 'pdf':
            content = _read_pdf_file(file_path)
            return _truncate_text_content(content), False
        elif file_type == 'image':
            return f"[Image file: {file_path} - use Read tool to view image content]", False
        else:
            return f"[Unsupported file type: {file_type}]", False
            
    except Exception as e:
        return f"[Error reading {file_path}: {str(e)}]", True


class ReadManyFilesTool(BaseTool):
    """Tool for reading multiple files at once."""
    
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
        """Execute the multi-file reading operation."""
        paths = tool_input.get("paths", [])
        include = tool_input.get("include")
        exclude = tool_input.get("exclude")
        recursive = tool_input.get("recursive", True)
        use_default_excludes = tool_input.get("use_default_excludes", True)
        include_binary = tool_input.get("include_binary", False)
        
        if not paths:
            return ToolResult(
                llm_content="ERROR: No paths provided",
                is_error=True
            )

        try:
            workspace_path = self.workspace_manager.get_workspace_path()
            
            # Discover files
            discovered_files = _discover_files(
                paths=paths,
                workspace_path=workspace_path,
                include=include,
                exclude=exclude,
                recursive=recursive,
                use_default_excludes=use_default_excludes
            )
            
            if not discovered_files:
                return ToolResult(
                    llm_content="No files found matching the specified patterns",
                    is_error=False
                )
            
            # Limit number of files
            if len(discovered_files) > MAX_FILES:
                return ToolResult(
                    llm_content=f"ERROR: Too many files found ({len(discovered_files)}). Maximum allowed is {MAX_FILES}. Use more specific patterns or exclusions.",
                    is_error=True
                )
            
            # Read file contents
            content_parts = []
            total_size = 0
            files_read = 0
            files_skipped = 0
            files_with_errors = 0
            
            for file_path in discovered_files:
                # Validate file access
                try:
                    self.workspace_manager.validate_existing_file_path(str(file_path))
                except FileSystemValidationError:
                    content_parts.append(f"\n{'='*60}\nFile: {file_path}\n{'='*60}\n[ERROR: File access denied or not found]")
                    files_with_errors += 1
                    continue
                
                content, is_error = _read_file_content(file_path, include_binary)
                
                # Add file separator and content
                separator = f"\n{'='*60}\nFile: {file_path}\n{'='*60}\n"
                file_content = separator + content
                
                # Check size limit
                if total_size + len(file_content) > MAX_TOTAL_CONTENT_SIZE:
                    content_parts.append(f"\n{'='*60}\n[TRUNCATED: Content size limit reached. Processed {files_read} of {len(discovered_files)} files]\n{'='*60}")
                    break
                
                content_parts.append(file_content)
                total_size += len(file_content)
                
                if is_error:
                    files_with_errors += 1
                elif "[Skipped" in content:
                    files_skipped += 1
                else:
                    files_read += 1
            
            # Build summary
            summary_parts = [f"Read {files_read} files"]
            if files_skipped > 0:
                summary_parts.append(f"skipped {files_skipped} files")
            if files_with_errors > 0:
                summary_parts.append(f"{files_with_errors} files had errors")
            
            summary = f"[{', '.join(summary_parts)} from {len(discovered_files)} discovered files]\n"
            
            final_content = summary + ''.join(content_parts)
            
            return ToolResult(
                llm_content=final_content,
                is_error=False
            )
            
        except Exception as e:
            return ToolResult(
                llm_content=f"ERROR: {str(e)}",
                is_error=True
            )

    async def execute_mcp_wrapper(
        self,
        paths: List[str],
        include: Optional[List[str]] = None,
        exclude: Optional[List[str]] = None,
        recursive: bool = True,
        use_default_excludes: bool = True,
        include_binary: bool = False,
    ):
        return await self._mcp_wrapper(
            tool_input={
                "paths": paths,
                "include": include,
                "exclude": exclude,
                "recursive": recursive,
                "use_default_excludes": use_default_excludes,
                "include_binary": include_binary,
            }
        )