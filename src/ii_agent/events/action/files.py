"""File operation actions for ii-agent."""

from __future__ import annotations

from typing import ClassVar, Optional

from ii_agent.core.schema import ActionType, SecurityRisk, FileEditSource, FileReadSource
from ii_agent.events.action.action import Action


class FileReadAction(Action):
    """Reads a file from a given path.
    
    Can be set to read specific lines using start and end.
    Default lines 0:-1 (whole file).
    """
    
    path: str = ""
    start: int = 0
    end: int = -1
    thought: str = ""
    action: str = ActionType.READ
    runnable: ClassVar[bool] = True
    security_risk: Optional[SecurityRisk] = SecurityRisk.LOW
    impl_source: FileReadSource = FileReadSource.DEFAULT
    view_range: Optional[list[int]] = None  # For OpenHands compatibility
    
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
    action: str = ActionType.WRITE
    runnable: ClassVar[bool] = True
    security_risk: Optional[SecurityRisk] = SecurityRisk.MEDIUM
    
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


class FileEditAction(Action):
    """Edits a file using various commands including view, create, str_replace, and insert.
    
    This class supports multiple modes of operation:
    1. OpenHands ACI mode (command-based)
    2. LLM-based content editing 
    
    Attributes:
        path (str): The path to the file being edited.
        
        # OpenHands ACI mode
        command (str): The editing command ('view', 'create', 'str_replace', 'insert', 'undo_edit').
        file_text (str): Content for file creation.
        old_str (str): The string to be replaced (str_replace mode).
        new_str (str): The replacement string (str_replace/insert modes).
        insert_line (int): Line number for insertion (insert mode).
        
        # LLM-based editing mode
        content (str): Full content for LLM-based editing.
        start (int): Starting line for LLM-based editing (1-indexed).
        end (int): Ending line for LLM-based editing (1-indexed).
    """
    
    path: str = ""
    
    # OpenHands ACI arguments
    command: str = ""
    file_text: Optional[str] = None
    old_str: Optional[str] = None
    new_str: Optional[str] = None
    insert_line: Optional[int] = None
    
    # LLM-based editing arguments  
    content: str = ""
    start: int = 1
    end: int = -1
    
    # Shared arguments
    thought: str = ""
    action: str = ActionType.EDIT
    runnable: ClassVar[bool] = True
    security_risk: Optional[SecurityRisk] = SecurityRisk.MEDIUM
    impl_source: FileEditSource = FileEditSource.OH_ACI
    
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
        ret += f"PATH: [{self.path}]\n"
        ret += f"THOUGHT: {self.thought}\n"
        
        if self.impl_source == FileEditSource.LLM_BASED_EDIT:
            ret += f"RANGE: [L{self.start}:L{self.end}]\n"
            ret += f"CONTENT:\n```\n{self.content}\n```\n"
        else:  # OH_ACI mode
            ret += f"COMMAND: {self.command}\n"
            if self.command == "create":
                ret += f"Created File with Text:\n```\n{self.file_text}\n```\n"
            elif self.command == "str_replace":
                ret += f"Old String: ```\n{self.old_str}\n```\n"
                ret += f"New String: ```\n{self.new_str}\n```\n"
            elif self.command == "insert":
                ret += f"Insert Line: {self.insert_line}\n"
                ret += f"New String: ```\n{self.new_str}\n```\n"
            elif self.command == "undo_edit":
                ret += "Undo Edit\n"
        
        return ret