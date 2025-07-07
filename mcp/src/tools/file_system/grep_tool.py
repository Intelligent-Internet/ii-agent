"""Content search tool using regular expressions."""

import os
import subprocess
import re
from pathlib import Path
from typing import Annotated, Dict, List, Optional, Union
from pydantic import Field
from src.core.workspace import WorkspaceManager
from .base import BaseFileSystemTool


DESCRIPTION = """
- Fast content search tool that works with any codebase size
- Searches file contents using regular expressions
- Supports full regex syntax (eg. "log.*Error", "function\\s+\\w+", etc.)
- Filter files by pattern with the include parameter (eg. "*.js", "*.{ts,tsx}")
- Returns file paths with at least one match sorted by modification time
- Use this tool when you need to find files containing specific patterns
- If you need to identify/count the number of matches within files, use the Bash tool with `rg` (ripgrep) directly. Do NOT use `grep`.
- When you are doing an open ended search that may require multiple rounds of globbing and grepping, use the Agent tool instead
"""

MAX_GLOB_RESULTS = 100


class GrepTool(BaseFileSystemTool):
    """Tool for searching file contents using regular expressions."""
    
    name = "Grep"
    description = DESCRIPTION

    def __init__(self, workspace_manager: WorkspaceManager):
        super().__init__(workspace_manager)

    def _validate_regex_pattern(self, pattern: str) -> bool:
        """Validate if the pattern is a valid regular expression."""
        try:
            re.compile(pattern)
            return True
        except re.error:
            return False

    def _is_ripgrep_available(self) -> bool:
        """Check if ripgrep (rg) command is available."""
        try:
            result = subprocess.run(['rg', '--version'], 
                                    capture_output=True, 
                                    text=True, 
                                    timeout=5)
            return result.returncode == 0
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def _run_ripgrep(self, pattern: str, search_path: Path, include: Optional[str] = None) -> List[Dict[str, Union[str, int]]]:
        """Execute ripgrep command and parse results."""
        try:
            # Build ripgrep command
            cmd = ['rg', '--line-number', '--no-heading', '--color=never']
            
            # Add include pattern if specified
            if include:
                cmd.extend(['--glob', include])
            
            # Add the pattern and search path (convert Path to string for subprocess)
            cmd.extend([pattern, str(search_path)])
            
            # Execute ripgrep
            result = subprocess.run(cmd, 
                                    capture_output=True, 
                                    text=True, 
                                    timeout=30)
            
            if result.returncode == 1:
                # No matches found
                return []
            elif result.returncode != 0:
                # Error occurred
                raise subprocess.CalledProcessError(result.returncode, cmd, result.stderr)
            
            # Parse the output
            matches = []
            for line in result.stdout.strip().split('\n'):
                if not line:
                    continue
                
                # ripgrep output format: file:line_number:content
                parts = line.split(':', 2)
                if len(parts) >= 3:
                    file_path = parts[0]
                    line_number = int(parts[1])
                    content = parts[2]
                    
                    matches.append({
                        'file_path': file_path,
                        'line_number': line_number,
                        'content': content
                    })
            
            return matches
            
        except subprocess.TimeoutExpired:
            raise Exception("Search operation timed out")
        except subprocess.CalledProcessError as e:
            raise Exception(f"Ripgrep command failed: {e.stderr.strip()}")
        except Exception as e:
            raise Exception(f"Error running ripgrep: {str(e)}")

    def _fallback_search(self, pattern: str, search_path: Path, include: Optional[str] = None) -> List[Dict[str, Union[str, int]]]:
        """Fallback search implementation using Python when ripgrep is not available."""
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            raise Exception(f"Invalid regular expression: {e}")
        
        matches = []
        
        try:
            # Determine file pattern
            if include:
                # Convert glob pattern to pathlib format
                if include.startswith('**/'):
                    glob_pattern = include
                elif include.startswith('*.'):
                    glob_pattern = f"**/{include}"
                else:
                    glob_pattern = f"**/*{include}*" if '*' not in include else include
            else:
                glob_pattern = "**/*"
            
            # Find files matching the pattern
            for file_path in search_path.glob(glob_pattern):
                if not file_path.is_file():
                    continue
                    
                try:
                    # Read file and search for pattern
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        for line_num, line in enumerate(f, 1):
                            if regex.search(line):
                                # Convert to relative path
                                rel_path = file_path.relative_to(search_path)
                                matches.append({
                                    'file_path': str(rel_path),
                                    'line_number': line_num,
                                    'content': line.rstrip('\n\r')
                                })
                                
                                # Limit results to prevent memory issues
                                if len(matches) >= MAX_GLOB_RESULTS * 10:
                                    return matches
                except (UnicodeDecodeError, PermissionError, OSError):
                    # Skip files that can't be read
                    continue
            
            return matches
            
        except Exception as e:
            raise Exception(f"Error during fallback search: {str(e)}")

    def _format_results(self, matches: List[Dict[str, Union[str, int]]], pattern: str, search_path: Path, include: Optional[str] = None) -> str:
        """Format search results for display."""
        if not matches:
            search_desc = f"pattern \"{pattern}\" in {search_path}"
            if include:
                search_desc += f" (filter: {include})"
            return f"No matches found for {search_desc}"
        
        # Group matches by file
        files_with_matches = {}
        for match in matches:
            file_path = match['file_path']
            if file_path not in files_with_matches:
                files_with_matches[file_path] = []
            files_with_matches[file_path].append(match)
        
        # Sort files by name
        sorted_files = sorted(files_with_matches.keys())
        
        # Limit total results
        total_matches = len(matches)
        if total_matches > MAX_GLOB_RESULTS:
            # Truncate results
            truncated_matches = []
            for file_path in sorted_files:
                for match in files_with_matches[file_path]:
                    truncated_matches.append(match)
                    if len(truncated_matches) >= MAX_GLOB_RESULTS:
                        break
                if len(truncated_matches) >= MAX_GLOB_RESULTS:
                    break
            matches = truncated_matches
            
            # Recalculate files with matches
            files_with_matches = {}
            for match in matches:
                file_path = match['file_path']
                if file_path not in files_with_matches:
                    files_with_matches[file_path] = []
                files_with_matches[file_path].append(match)
            sorted_files = sorted(files_with_matches.keys())
        
        # Format output
        result_lines = []
        search_desc = f"pattern \"{pattern}\" in {search_path}"
        if include:
            search_desc += f" (filter: {include})"
        
        result_lines.append(f"Found {len(matches)} matches for {search_desc}:")
        result_lines.append("---")
        
        for file_path in sorted_files:
            result_lines.append(f"File: {file_path}")
            for match in files_with_matches[file_path]:
                line_content = match['content'].strip()
                result_lines.append(f"L{match['line_number']}: {line_content}")
            result_lines.append("---")
        
        if total_matches > MAX_GLOB_RESULTS:
            result_lines.append(f"Note: Results limited to {MAX_GLOB_RESULTS} matches. Total matches found: {total_matches}")
        
        return '\n'.join(result_lines)

    def run_impl(
        self,
        pattern: Annotated[str, Field(description="The regular expression pattern to search for in file contents")],
        path: Annotated[Optional[str], Field(description="The directory to search in. Defaults to the current working directory.")] = None,
        include: Annotated[Optional[str], Field(description="File pattern to include in the search (e.g. \"*.js\", \"*.{ts,tsx}\")")] = None,
    ) -> str:
        """
        Search for pattern in files using ripgrep.
        """

        workspace_path = self.workspace_manager.get_workspace_path()
        
        # Validate the regex pattern
        if not self._validate_regex_pattern(pattern):
            return f"ERROR: Invalid regular expression pattern: {pattern}"
        
        # Determine search directory using Path
        if path is None:
            search_dir = workspace_path
        else:
            # Convert to Path object and resolve to absolute path
            search_dir = Path(path).resolve()

            # Check if path is in workspace
            if not self.workspace_manager.validate_boundary(search_dir):
                return f"ERROR: Path `{search_dir}` is not in workspace boundary `{workspace_path}`"
            
            # Verify the directory exists using Path methods
            if not search_dir.exists():
                return f"ERROR: Directory `{search_dir}` does not exist"
            
            if not search_dir.is_dir():
                return f"ERROR: Path `{search_dir}` is not a directory"
        
        try:
            # Try ripgrep first, fallback to Python implementation
            if self._is_ripgrep_available():
                matches = self._run_ripgrep(pattern, search_dir, include)
            else:
                matches = self._fallback_search(pattern, search_dir, include)
            
            # Format and return results
            return self._format_results(matches, pattern, search_dir, include)
            
        except Exception as e:
            return f"ERROR: Search failed: {str(e)}"