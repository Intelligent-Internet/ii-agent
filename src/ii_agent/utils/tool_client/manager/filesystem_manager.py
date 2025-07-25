"""Manager for file system operations using external file system tools."""

import logging
import sys
import os
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class FileSystemResponse:
    """Response from file system operations."""
    success: bool
    file_content: str


class FileSystemManager:
    """Manager for file system operations that uses external tools directly."""
    
    def __init__(self, workspace_path: str = "/workspace"):
        self.workspace_path = workspace_path
        self._setup_tools()
    
    def _setup_tools(self):
        """Setup the internal file system tools."""
        # Import and initialize internal tools
        try:
            from ii_agent.tools.file_system_tools import (
                FileReadTool, FileEditTool, FileWriteTool, MultiEditTool,
                LSTool, GlobTool, GrepTool
            )
            from ii_agent.utils.file_system_workspace import FileSystemWorkspace
            # Initialize workspace manager
            self.workspace_manager = FileSystemWorkspace(self.workspace_path)
            
            # Initialize tools
            self.read_tool = FileReadTool(self.workspace_manager)
            self.edit_tool = FileEditTool(self.workspace_manager)
            self.write_tool = FileWriteTool(self.workspace_manager)
            self.multi_edit_tool = MultiEditTool(self.workspace_manager)
            self.ls_tool = LSTool(self.workspace_manager)
            self.glob_tool = GlobTool(self.workspace_manager)
            self.grep_tool = GrepTool(self.workspace_manager)
            
            self.tools_available = True
            logger.info("✅ Successfully initialized internal file system tools")
            print("✅ Successfully initialized internal file system tools")
        except Exception as e:
            logger.warning(f"⚠️  Failed to import internal tools: {e}")
            print(f"⚠️  Failed to import internal tools: {e}")
            self.tools_available = False
    
    def _ensure_tools_available(self) -> FileSystemResponse:
        """Check if tools are available, return error response if not."""
        if not self.tools_available:
            return FileSystemResponse(
                success=False,
                file_content="ERROR: External file system tools not available in this environment"
            )
        return None
    
    def read_file(
        self, 
        file_path: str, 
        limit: Optional[int] = None, 
        offset: Optional[int] = None
    ) -> FileSystemResponse:
        """Read file contents."""
        error_check = self._ensure_tools_available()
        if error_check:
            return error_check
        
        try:
            result = self.read_tool.run_impl(
                file_path=file_path,
                limit=limit,
                offset=offset
            )
            
            # Handle different return types
            if isinstance(result, dict):
                # For images, convert to JSON string
                import json
                content = json.dumps(result)
            else:
                content = str(result)
            
            success = not content.startswith("ERROR:")
            return FileSystemResponse(success=success, file_content=content)
            
        except Exception as e:
            return FileSystemResponse(
                success=False,
                file_content=f"Error reading file: {str(e)}"
            )
    
    def edit_file(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False
    ) -> FileSystemResponse:
        """Edit file contents."""
        error_check = self._ensure_tools_available()
        if error_check:
            return error_check
        
        try:
            result = self.edit_tool.run_impl(
                file_path=file_path,
                old_string=old_string,
                new_string=new_string,
                replace_all=replace_all
            )
            
            success = not result.startswith("ERROR:")
            return FileSystemResponse(success=success, file_content=result)
            
        except Exception as e:
            return FileSystemResponse(
                success=False,
                file_content=f"Error editing file: {str(e)}"
            )
    
    def write_file(self, file_path: str, content: str) -> FileSystemResponse:
        """Write file contents."""
        error_check = self._ensure_tools_available()
        if error_check:
            return error_check
        
        try:
            result = self.write_tool.run_impl(
                file_path=file_path,
                content=content
            )
            
            success = not result.startswith("ERROR:")
            return FileSystemResponse(success=success, file_content=result)
            
        except Exception as e:
            return FileSystemResponse(
                success=False,
                file_content=f"Error writing file: {str(e)}"
            )
    
    def multi_edit(self, file_path: str, edits: List[Dict[str, Any]]) -> FileSystemResponse:
        """Perform multiple edits on a file."""
        error_check = self._ensure_tools_available()
        if error_check:
            return error_check
        
        try:
            result = self.multi_edit_tool.run_impl(
                file_path=file_path,
                edits=edits
            )
            
            success = not result.startswith("ERROR:")
            return FileSystemResponse(success=success, file_content=result)
            
        except Exception as e:
            return FileSystemResponse(
                success=False,
                file_content=f"Error in multi-edit: {str(e)}"
            )
    
    def ls(self, path: str, ignore: Optional[List[str]] = None) -> FileSystemResponse:
        """List directory contents."""
        error_check = self._ensure_tools_available()
        if error_check:
            return error_check
        
        try:
            result = self.ls_tool.run_impl(
                path=path,
                ignore=ignore
            )
            
            success = not result.startswith("ERROR:")
            return FileSystemResponse(success=success, file_content=result)
            
        except Exception as e:
            return FileSystemResponse(
                success=False,
                file_content=f"Error listing directory: {str(e)}"
            )
    
    def glob(self, pattern: str, path: Optional[str] = None) -> FileSystemResponse:
        """Search for files using glob patterns."""
        error_check = self._ensure_tools_available()
        if error_check:
            return error_check
        
        try:
            result = self.glob_tool.run_impl(
                pattern=pattern,
                path=path
            )
            
            success = not result.startswith("ERROR:")
            return FileSystemResponse(success=success, file_content=result)
            
        except Exception as e:
            return FileSystemResponse(
                success=False,
                file_content=f"Error in glob search: {str(e)}"
            )
    
    def grep(
        self, 
        pattern: str, 
        path: Optional[str] = None, 
        include: Optional[str] = None
    ) -> FileSystemResponse:
        """Search for content using regex patterns."""
        error_check = self._ensure_tools_available()
        if error_check:
            return error_check
        
        try:
            result = self.grep_tool.run_impl(
                pattern=pattern,
                path=path,
                include=include
            )
            
            success = not result.startswith("ERROR:")
            return FileSystemResponse(success=success, file_content=result)
            
        except Exception as e:
            return FileSystemResponse(
                success=False,
                file_content=f"Error in grep search: {str(e)}"
            )