"""Directory listing tool for exploring file system structure."""

import os
import fnmatch

from pathlib import Path
from typing import Optional, List, NamedTuple, Any
from ii_tool.core.workspace import WorkspaceManager, FileSystemValidationError
from ii_tool.tools.base import BaseTool, ToolResult


# Constants
MAX_FILES = 1000
TRUNCATED_MESSAGE = f"There are more than {MAX_FILES} files in the repository. Use the LS tool (passing a specific path), Bash tool, and other tools to explore nested directories. The first {MAX_FILES} files and directories are included below:\n\n"

# Name
NAME = "LS"
DISPLAY_NAME = "List directory"

# Tool description
DESCRIPTION = """Lists files and directories in a given path. The path parameter must be an absolute path, not a relative path. You can optionally provide an array of glob patterns to ignore with the ignore parameter. You should generally prefer the Glob and Grep tools, if you know which directories to search."""

# Input schema
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "The absolute path to the directory to list (must be absolute, not relative)"
        },
        "ignore": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of glob patterns to ignore"
        }
    },
    "required": ["path"]
}


class TreeNode(NamedTuple):
    """Represents a node in the file tree."""
    name: str
    path: str
    type: str  # 'file' or 'directory'
    children: Optional[List['TreeNode']] = None

def _should_skip(path: Path, ignore_patterns: Optional[List[str]] = None) -> bool:
    """
    Determine if a path should be skipped based on filtering rules.
    
    Args:
        path: The file or directory Path to check
        ignore_patterns: Optional list of glob patterns to ignore
        
    Returns:
        True if the path should be skipped, False otherwise
    """
    # Skip dotfiles and directories (except current directory ".")
    if path.name.startswith(".") and path.name not in (".", ".."):
        return True
        
    # Check if any part of the path contains hidden directories
    for part in path.parts:
        if part.startswith(".") and part not in (".", ".."):
            return True
        
    # Skip __pycache__ directories
    if "__pycache__" in path.parts:
        return True
        
    # Check custom ignore patterns
    if ignore_patterns:
        for pattern in ignore_patterns:
            if fnmatch.fnmatch(path.name, pattern):
                return True
                
    return False

def _list_directory(initial_path: Path, base_path: Path, ignore_patterns: Optional[List[str]] = None) -> List[str]:
    """
    List files and directories in the specified directory (non-recursive).
    
    Args:
        initial_path: The starting directory Path
        base_path: Base directory Path for relative path calculation
        ignore_patterns: Optional list of glob patterns to ignore
        
    Returns:
        List of relative paths from base_path as strings
    """
    results = []
    
    # Only process the initial directory, not recursively
    try:
        entries = list(initial_path.iterdir())
        entries.sort(key=lambda p: p.name.lower())  # Sort entries for consistent output
        
        for entry_path in entries:
            if _should_skip(entry_path, ignore_patterns):
                continue
                
            try:
                relative_path = entry_path.relative_to(base_path)
                if entry_path.is_dir():
                    # Add directory with trailing slash
                    results.append(str(relative_path) + os.sep)
                else:
                    # Add file
                    results.append(str(relative_path))
            except ValueError:
                # Skip if we can't make it relative
                continue
                
            # Check if we've hit the limit
            if len(results) > MAX_FILES:
                return results[:MAX_FILES]
                
    except (OSError, PermissionError):
        # Return empty list if we can't read the directory
        return []
            
    return results

def _create_file_tree(sorted_paths: List[str]) -> List[TreeNode]:
    """
    Create a simple flat tree structure from a list of sorted paths.
    
    Args:
        sorted_paths: List of relative file paths as strings (single level only)
        
    Returns:
        List of TreeNode objects representing the flat structure
    """
    root = []
    
    for path_str in sorted_paths:
        # For non-recursive listing, each path is just a filename or dirname
        name = path_str.rstrip(os.sep)  # Remove trailing slash
        node_type = "directory" if path_str.endswith(os.sep) else "file"
        
        new_node = TreeNode(
            name=name,
            path=path_str,
            type=node_type,
            children=None
        )
        
        root.append(new_node)
                
    return root

def _print_tree(tree: List[TreeNode], level: int = 0, prefix: str = "", root_path: Optional[Path] = None) -> str:
    """
    Format tree structure as a readable string.
    
    Args:
        tree: List of TreeNode objects to format
        level: Current indentation level
        prefix: Current line prefix
        root_path: The root path to display at the top level
        
    Returns:
        Formatted tree string
    """
    result = ""
    
    # Add absolute path at root level
    if level == 0 and root_path:
        result += f"- {root_path}{os.sep}\n"
        prefix = "  "
        
    for node in tree:
        # Add current node
        suffix = os.sep if node.type == "directory" else ""
        result += f"{prefix}- {node.name}{suffix}\n"
        
        # Recursively add children
        if node.children:
            result += _print_tree(node.children, level + 1, f"{prefix}  ", root_path)
            
    return result


class LSTool(BaseTool):
    """Tool for listing files and directories."""
    
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
        """
        Execute the directory listing operation.
        
        Args:
            tool_input: Dictionary containing path and optional ignore patterns
            
        Returns:
            ToolResult with formatted directory tree
        """
        path = tool_input.get("path")
        ignore = tool_input.get("ignore")

        try:
            self.workspace_manager.validate_existing_directory_path(path)
            
            target_path = Path(path).resolve()

            # List directory contents
            file_paths = _list_directory(target_path, target_path, ignore)
            
            # Check if directory is empty
            if not file_paths:
                return ToolResult(
                    llm_content=f"Directory {target_path} is empty.",
                    is_error=False
                )
            
            # Check if we hit the limit
            is_truncated = len(file_paths) > MAX_FILES
            if is_truncated:
                file_paths = file_paths[:MAX_FILES]
            
            # Sort file paths (directories first, then alphabetically)
            def sort_key(p: str) -> tuple:
                # Remove trailing slash for comparison
                clean_path = p.rstrip(os.sep)
                # Check if it's a directory by looking for trailing slash in original
                is_dir = p.endswith(os.sep)
                # Return tuple for sorting: (not is_dir, lowercase path)
                # not is_dir so directories (True -> False -> 0) come before files (False -> True -> 1)
                return (not is_dir, clean_path.lower())
            
            file_paths.sort(key=sort_key)
            
            # Create tree structure
            tree = _create_file_tree(file_paths)
            
            # Generate formatted output
            result = ""
            if is_truncated:
                result += TRUNCATED_MESSAGE
            
            result += _print_tree(tree, root_path=target_path)
            
            return ToolResult(
                llm_content=result.rstrip(),
                is_error=False
            )
        
        except (FileSystemValidationError) as e:
            return ToolResult(
                llm_content=f"ERROR: {e}",
                is_error=True
            )

    async def execute_mcp_wrapper(
        self,
        path: str,
        ignore: Optional[List[str]] = None,
    ):
        return await self._mcp_wrapper(
            tool_input={
                "path": path,
                "ignore": ignore,
            }
        )