"""Directory listing tool for exploring file system structure."""

import os
import fnmatch

from pathlib import Path
from typing import Annotated, Optional, List, NamedTuple
from pydantic import Field
from .base import BaseFileSystemTool, FileSystemValidationError
from ii_agent.utils.file_system_workspace import FileSystemWorkspace


DESCRIPTION = """Lists files and directories in a given path. The path parameter must be an absolute path, not a relative path. You can optionally provide an array of glob patterns to ignore with the ignore parameter. You should generally prefer the Glob and Grep tools, if you know which directories to search."""

# Constants
MAX_FILES = 1000
TRUNCATED_MESSAGE = f"There are more than {MAX_FILES} files in the repository. Use the LS tool (passing a specific path), Bash tool, and other tools to explore nested directories. The first {MAX_FILES} files and directories are included below:\n\n"


class TreeNode(NamedTuple):
    """Represents a node in the file tree."""
    name: str
    path: str
    type: str  # 'file' or 'directory'
    children: Optional[List['TreeNode']] = None


class LSTool(BaseFileSystemTool):
    """Tool for listing files and directories."""
    
    name = "LS"
    description = DESCRIPTION

    def __init__(self, workspace_manager: FileSystemWorkspace):
        super().__init__(workspace_manager)

    def _should_skip(self, path: Path, ignore_patterns: Optional[List[str]] = None) -> bool:
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

    def _list_directory(self, initial_path: Path, base_path: Path, ignore_patterns: Optional[List[str]] = None) -> List[str]:
        """
        Recursively list files and directories.
        
        Args:
            initial_path: The starting directory Path
            base_path: Base directory Path for relative path calculation
            ignore_patterns: Optional list of glob patterns to ignore
            
        Returns:
            List of relative paths from base_path as strings
        """
        results = []
        queue = [initial_path]
        
        while queue and len(results) <= MAX_FILES:
            current_path = queue.pop(0)
            
            if self._should_skip(current_path, ignore_patterns):
                continue
                
            # Add directory to results if it's not the initial path
            if current_path != initial_path:
                try:
                    relative_path = current_path.relative_to(base_path)
                    results.append(str(relative_path) + os.sep)
                except ValueError:
                    # Skip if we can't make it relative
                    continue
                
            # Try to read directory contents
            try:
                entries = list(current_path.iterdir())
                entries.sort(key=lambda p: p.name.lower())  # Sort entries for consistent output
                
                for entry_path in entries:
                    if self._should_skip(entry_path, ignore_patterns):
                        continue
                        
                    if entry_path.is_dir():
                        # Add directory to queue for processing
                        queue.append(entry_path)
                    else:
                        # Add file to results
                        try:
                            relative_path = entry_path.relative_to(base_path)
                            results.append(str(relative_path))
                        except ValueError:
                            # Skip if we can't make it relative
                            continue
                        
                    # Check if we've hit the limit
                    if len(results) > MAX_FILES:
                        return results
                        
            except (OSError, PermissionError):
                # Log error but continue processing
                continue
                
        return results

    def _create_file_tree(self, sorted_paths: List[str]) -> List[TreeNode]:
        """
        Create a tree structure from a list of sorted paths.
        
        Args:
            sorted_paths: List of relative file paths as strings
            
        Returns:
            List of TreeNode objects representing the tree structure
        """
        root = []
        
        for path_str in sorted_paths:
            path = Path(path_str)
            parts = path.parts
            current_level = root
            current_path_parts = []
            
            for i, part in enumerate(parts):
                current_path_parts.append(part)
                current_path_str = str(Path(*current_path_parts))
                is_last_part = i == len(parts) - 1
                
                # Find existing node at current level
                existing_node = None
                for node in current_level:
                    if node.name == part:
                        existing_node = node
                        break
                        
                if existing_node:
                    # Use existing node
                    current_level = existing_node.children if existing_node.children else []
                else:
                    # Create new node
                    node_type = "file" if is_last_part else "directory"
                    children = [] if not is_last_part else None
                    
                    new_node = TreeNode(
                        name=part,
                        path=current_path_str, 
                        type=node_type,
                        children=children
                    )
                    
                    current_level.append(new_node)
                    current_level = children if children is not None else []
                    
        return root

    def _print_tree(self, tree: List[TreeNode], level: int = 0, prefix: str = "") -> str:
        """
        Format tree structure as a readable string.
        
        Args:
            tree: List of TreeNode objects to format
            level: Current indentation level
            prefix: Current line prefix
            
        Returns:
            Formatted tree string
        """
        result = ""
        
        # Add absolute path at root level
        if level == 0:
            result += f"- {Path.cwd()}{os.sep}\n"
            prefix = "  "
            
        for node in tree:
            # Add current node
            suffix = os.sep if node.type == "directory" else ""
            result += f"{prefix}- {node.name}{suffix}\n"
            
            # Recursively add children
            if node.children:
                result += self._print_tree(node.children, level + 1, f"{prefix}  ")
                
        return result

    def run_impl(
        self,
        path: Annotated[str, Field(description="The absolute path to the directory to list (must be absolute, not relative)")],
        ignore: Annotated[Optional[List[str]], Field(description="List of glob patterns to ignore")] = None,
    ) -> str:
        """
        Execute the directory listing operation.
        
        Args:
            path: Absolute path to the directory to list
            ignore: Optional list of glob patterns to ignore
            
        Returns:
            Formatted directory tree as string
        """

        try:
            self.validate_existing_directory_path(path)
            
            target_path = Path(path).resolve()

            # List directory contents
            file_paths = self._list_directory(target_path, target_path, ignore)
            
            # Check if directory is empty
            if not file_paths:
                return f"Directory {target_path} is empty."
            
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
            tree = self._create_file_tree(file_paths)
            
            # Generate formatted output
            result = ""
            if is_truncated:
                result += TRUNCATED_MESSAGE
            
            result += self._print_tree(tree)
            
            return result.rstrip()
        
        except (FileSystemValidationError) as e:
            return f"ERROR: {e}"