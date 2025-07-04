"""File operation observations for ii-agent."""
from __future__ import annotations

from typing import Optional
from difflib import unified_diff

from ii_agent.core.schema import ObservationType, FileEditSource
from ii_agent.events.observation.observation import Observation

class FileReadObservation(Observation):
    """Observation from a file read operation."""
    
    path: str = ""
    success: bool = True
    error_message: Optional[str] = None
    lines_read: Optional[int] = None
    observation: str = ObservationType.READ
    
    @property
    def message(self) -> str:
        if self.success:
            return f"Successfully read file: {self.path}"
        else:
            return f"Failed to read file: {self.path} - {self.error_message}"
    
    def __str__(self) -> str:
        if self.success:
            line_info = f" ({self.lines_read} lines)" if self.lines_read else ""
            return f"[Read from {self.path} successful{line_info}]\n{self.content}"
        else:
            return f"[Error reading {self.path}]: {self.error_message}"

class FileWriteObservation(Observation):
    """Observation from a file write operation."""
    
    path: str = ""
    success: bool = True
    error_message: Optional[str] = None
    bytes_written: Optional[int] = None
    observation: str = ObservationType.WRITE
    
    @property
    def message(self) -> str:
        if self.success:
            return f"Successfully wrote to file: {self.path}"
        else:
            return f"Failed to write to file: {self.path} - {self.error_message}"
    
    def __str__(self) -> str:
        if self.success:
            size_info = f" ({self.bytes_written} bytes)" if self.bytes_written else ""
            return f"[Write to {self.path} successful{size_info}]\n{self.content}"
        else:
            return f"[Error writing to {self.path}]: {self.error_message}"
  
class FileEditObservation(Observation):
    """Observation from a file edit operation.
    
    Includes both old and new content and can generate diff visualizations.
    The diff is computed lazily and cached for performance.
    """
    
    path: str = ""
    success: bool = True
    error_message: Optional[str] = None
    prev_exist: bool = False
    old_content: Optional[str] = None
    new_content: Optional[str] = None
    impl_source: FileEditSource = FileEditSource.OH_ACI
    diff: Optional[str] = None  # Raw diff between old and new content
    _diff_cache: Optional[str] = None  # Cached diff visualization
    observation: str = ObservationType.EDIT
    
    @property
    def message(self) -> str:
        if self.success:
            if not self.prev_exist:
                return f"Successfully created file: {self.path}"
            else:
                return f"Successfully edited file: {self.path}"
        else:
            return f"Failed to edit file: {self.path} - {self.error_message}"
    
    def get_diff(self, context_lines: int = 3) -> str:
        """Generate a unified diff between old and new content."""
        if self.old_content is None or self.new_content is None:
            return ""
        
        old_lines = self.old_content.splitlines(keepends=True)
        new_lines = self.new_content.splitlines(keepends=True)
        
        diff_lines = list(unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{self.path}",
            tofile=f"b/{self.path}",
            n=context_lines
        ))
        
        return "".join(diff_lines)
    
    def visualize_diff(self, context_lines: int = 3) -> str:
        """Generate a human-readable diff visualization."""
        if self._diff_cache is not None:
            return self._diff_cache
        
        if not self.success:
            self._diff_cache = f"[Error editing {self.path}]: {self.error_message}"
            return self._diff_cache
        
        if not self.prev_exist:
            self._diff_cache = f"[New file {self.path} created]\n{self.content}"
            return self._diff_cache
        
        if self.old_content == self.new_content:
            self._diff_cache = f"[No changes detected in {self.path}]"
            return self._diff_cache
        
        diff = self.get_diff(context_lines)
        if diff:
            self._diff_cache = f"[File {self.path} edited]\n{diff}"
        else:
            self._diff_cache = f"[File {self.path} modified]"
        
        return self._diff_cache
    
    def __str__(self) -> str:
        if self.impl_source == FileEditSource.OH_ACI:
            return self.visualize_diff()
        else:
            # For LLM-based editing, use the content directly
            return self.content if self.content else self.visualize_diff()