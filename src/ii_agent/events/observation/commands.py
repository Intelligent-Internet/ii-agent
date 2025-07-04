"""Command execution observations for ii-agent."""
from __future__ import annotations

from typing import Any, Dict, Optional
from pydantic import BaseModel

from ii_agent.core.schema import ObservationType
from ii_agent.events.observation.observation import Observation

class CmdOutputMetadata(BaseModel):
    """Metadata for command execution."""
    
    command: str = ""
    exit_code: int = 0
    pid: Optional[int] = None
    working_directory: str = ""
    timeout: Optional[float] = None
    
class CmdOutputObservation(Observation):
    """Observation from a shell command execution."""
    
    command: str = ""
    exit_code: int = 0
    metadata: Optional[CmdOutputMetadata] = None
    observation: str = ObservationType.RUN
    
    def get_metadata(self) -> CmdOutputMetadata:
        """Get or create metadata for this command output."""
        if self.metadata is None:
            return CmdOutputMetadata(
                command=self.command,
                exit_code=self.exit_code
            )
        return self.metadata
    
    @property
    def message(self) -> str:
        if self.exit_code == 0:
            return f"Command executed successfully: {self.command}"
        else:
            return f"Command failed with exit code {self.exit_code}: {self.command}"
    
    def __str__(self) -> str:
        status = "✓" if self.exit_code == 0 else "✗"
        header = f"[{status} Command: {self.command}]"
        if self.exit_code != 0:
            header += f" (exit code: {self.exit_code})"
        
        if self.content:
            return f"{header}\n{self.content}"
        else:
            return header

class IPythonRunCellObservation(Observation):
    """Observation from Python code execution in IPython/Jupyter."""
    
    code: str = ""
    image_urls: list[str] = []
    observation: str = ObservationType.RUN_IPYTHON
    
    @property
    def message(self) -> str:
        return f"Python code executed: {self.code[:50]}{'...' if len(self.code) > 50 else ''}"
    
    def __str__(self) -> str:
        header = "[Python Code Execution]"
        result = f"{header}\nCode:\n{self.code}\n"
        
        if self.content:
            result += f"Output:\n{self.content}\n"
        
        if self.image_urls:
            result += f"Images generated: {len(self.image_urls)}\n"
            
        return result.rstrip()