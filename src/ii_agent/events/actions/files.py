"""File operation actions for ii-agent."""

from dataclasses import dataclass
from enum import Enum
from typing import ClassVar, Optional

from ...core.schema import ActionType
from ..action import Action, ActionSecurityRisk
from ..event import EventSource


class FileEditSource(str, Enum):
    """Source/mode for file editing operations."""
    LLM_BASED_EDIT = "llm_based_edit"
    STR_REPLACE = "str_replace"  # String replacement mode
    DEFAULT = "default"


@dataclass
class FileReadAction(Action):
    """Reads a file from a given path.
    
    Can be set to read specific lines using start and end.
    Default lines 0:-1 (whole file).
    """
    
    path: str = ""
    start: int = 0
    end: int = -1
    thought: str = ""
    runnable: ClassVar[bool] = True
    security_risk: Optional[ActionSecurityRisk] = ActionSecurityRisk.LOW
    
    @property 
    def message(self) -> str:
        if self.start == 0 and self.end == -1:
            return f"Reading file: {self.path}"
        else:
            return f"Reading file: {self.path} (lines {self.start}-{self.end})"
    
    def __str__(self) -> str:
        ret = "**FileReadAction**\n"
        if self.thought:
            ret += f"THOUGHT: {self.thought}\n"
        ret += f"PATH: {self.path}"
        if self.start != 0 or self.end != -1:
            ret += f"\nRANGE: [L{self.start}:L{self.end}]"
        return ret


@dataclass 
class FileWriteAction(Action):
    """Writes content to a file at a given path.
    
    Can be set to write specific lines using start and end.
    Default lines 0:-1 (whole file).
    """
    
    path: str = ""
    content: str = ""
    start: int = 0
    end: int = -1
    thought: str = ""
    runnable: ClassVar[bool] = True
    security_risk: Optional[ActionSecurityRisk] = ActionSecurityRisk.MEDIUM
    
    @property
    def message(self) -> str:
        return f"Writing file: {self.path}"
    
    def __str__(self) -> str:
        ret = "**FileWriteAction**\n"
        if self.thought:
            ret += f"THOUGHT: {self.thought}\n"
        ret += f"PATH: {self.path}\n"
        ret += f"RANGE: [L{self.start}:L{self.end}]\n"
        ret += f"CONTENT:\n```\n{self.content}\n```"
        return ret


@dataclass
class FileEditAction(Action):
    """Edits a file using various commands including view, create, str_replace, and insert.
    
    This class supports multiple modes of operation:
    1. String replacement mode (str_replace)
    2. LLM-based content editing 
    3. Line insertion
    4. File creation
    
    Attributes:
        path (str): The path to the file being edited.
        command (str): The editing command ('view', 'create', 'str_replace', 'insert').
        old_str (str): The string to be replaced (str_replace mode).
        new_str (str): The replacement string (str_replace/insert modes).
        insert_line (int): Line number for insertion (insert mode).
        content (str): Full content for create/write operations.
        start (int): Starting line for LLM-based editing (1-indexed).
        end (int): Ending line for LLM-based editing (1-indexed).
    """
    
    path: str = ""
    command: str = "str_replace"  # Default to str_replace mode
    
    # String replacement mode
    old_str: Optional[str] = None
    new_str: Optional[str] = None
    insert_line: Optional[int] = None
    
    # Content-based editing
    content: str = ""
    start: int = 1
    end: int = -1
    
    # Metadata
    thought: str = ""
    runnable: ClassVar[bool] = True
    security_risk: Optional[ActionSecurityRisk] = ActionSecurityRisk.MEDIUM
    impl_source: FileEditSource = FileEditSource.STR_REPLACE
    
    @property
    def message(self) -> str:
        if self.command == "create":
            return f"Creating file: {self.path}"
        elif self.command == "str_replace":
            return f"Editing file: {self.path} (string replacement)"
        elif self.command == "insert":
            return f"Inserting into file: {self.path} at line {self.insert_line}"
        else:
            return f"Editing file: {self.path}"
    
    def __str__(self) -> str:
        ret = "**FileEditAction**\n"
        ret += f"PATH: {self.path}\n"
        if self.thought:
            ret += f"THOUGHT: {self.thought}\n"
        ret += f"COMMAND: {self.command}\n"
        
        if self.command == "create":
            ret += f"CONTENT:\n```\n{self.content}\n```"
        elif self.command == "str_replace":
            ret += f"OLD_STR:\n```\n{self.old_str}\n```\n"
            ret += f"NEW_STR:\n```\n{self.new_str}\n```"
        elif self.command == "insert":
            ret += f"INSERT_LINE: {self.insert_line}\n"
            ret += f"NEW_STR:\n```\n{self.new_str}\n```"
        elif self.impl_source == FileEditSource.LLM_BASED_EDIT:
            ret += f"RANGE: [L{self.start}:L{self.end}]\n"
            ret += f"CONTENT:\n```\n{self.content}\n```"
        
        return ret