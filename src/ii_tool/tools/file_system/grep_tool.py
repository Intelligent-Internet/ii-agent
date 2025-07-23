"""Content search tool using regular expressions."""

import subprocess
import re

from pathlib import Path
from typing import Dict, List, Optional
from ii_tool.core.workspace import WorkspaceManager, FileSystemValidationError
from ii_tool.tools.base import BaseTool, ToolResult


# Constants
MAX_GLOB_RESULTS = 100
COMMAND_TIMEOUT = 30

# Name
NAME = "Grep"
DISPLAY_NAME = "Search file contents"

# Tool description
DESCRIPTION = """\
- Fast content search tool that works with any codebase size
- Searches file contents using regular expressions
- Supports full regex syntax (eg. "log.*Error", "function\\s+\\w+", etc.)
- Filter files by pattern with the include parameter (eg. "*.js", "*.{ts,tsx}")
- Returns file paths with at least one match sorted by modification time
- Use this tool when you need to find files containing specific patterns
- If you need to identify/count the number of matches within files, use the Bash tool with `rg` (ripgrep) directly. Do NOT use `grep`.
- When you are doing an open ended search that may require multiple rounds of globbing and grepping, use the Agent tool instead
"""

# Input schema
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "pattern": {
            "type": "string",
            "description": "The regular expression pattern to search for within file contents"
        },
        "path": {
            "type": "string",
            "description": "The absolute path to the directory to search within. If omitted, searches the current working directory"
        },
        "include": {
            "type": "string",
            "description": "A glob pattern to filter which files are searched. If omitted, searches all files"
        }
    },
    "required": ["pattern"]
}


class GrepToolError(Exception):
    """Custom exception for grep tool errors."""
    pass

def run_ripgrep(pattern: str, search_path: Path, include: Optional[str] = None) -> List[Dict[str, str]]:
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
                                timeout=COMMAND_TIMEOUT)
        
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
            matches.append({
                'file_path': parts[0],
                'line_number': parts[1],
                'content': parts[2]
            })
        
        return matches
        
    except subprocess.TimeoutExpired:
        raise GrepToolError("Search operation timed out")
    except subprocess.CalledProcessError as e:
        raise GrepToolError(f"Ripgrep command failed: {e.stderr.strip()}")

class GrepTool(BaseTool):
    """Tool for searching file contents using regular expressions."""
    
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = True

    def __init__(self, workspace_manager: WorkspaceManager):
        self.workspace_manager = workspace_manager

    def _validate_regex_pattern(self, pattern: str) -> bool:
        """Validate if the pattern is a valid regular expression."""
        try:
            re.compile(pattern)
            return True
        except re.error:
            return False

    def _format_results(self, matches: List[Dict[str, str]], pattern: str, search_path: Path, include: Optional[str] = None) -> str:
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

    async def execute(
        self,
        pattern: str,
        path: Optional[str] = None,
        include: Optional[str] = None,
    ) -> ToolResult:
        """
        Search for pattern in files using ripgrep.
        """
        
        # Validate the regex pattern
        if not self._validate_regex_pattern(pattern):
            return ToolResult(
                llm_content=f"ERROR: Invalid regular expression pattern: {pattern}",
                is_error=True
            )
        
        try:
            # Determine search directory using Path
            if path is None:
                search_dir = self.workspace_manager.get_workspace_path()
            else:
                self.workspace_manager.validate_existing_directory_path(path)
                search_dir = Path(path).resolve()
            
            matches = run_ripgrep(pattern, search_dir, include)

            # Format and return results
            result_content = self._format_results(matches, pattern, search_dir, include)
            return ToolResult(
                llm_content=result_content,
                is_error=False
            )
        except (subprocess.CalledProcessError, OSError, FileSystemValidationError, GrepToolError) as e:
            return ToolResult(
                llm_content=f"ERROR: {e}",
                is_error=True
            )

    async def execute_mcp_wrapper(
        self,
        pattern: str,
        path: Optional[str] = None,
        include: Optional[str] = None,
    ):
        return await self._mcp_wrapper(pattern, path, include)