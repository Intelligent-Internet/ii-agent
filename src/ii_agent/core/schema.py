"""Schema definitions for ii-agent."""

from enum import Enum


class ActionType(str, Enum):
    """Enumeration of all possible action types in ii-agent."""
    
    # Core actions
    MESSAGE = "message"
    SYSTEM = "system"
    
    # File operations
    READ = "read"
    WRITE = "write" 
    EDIT = "edit"
    
    # Command execution
    RUN = "run"
    RUN_IPYTHON = "run_ipython"
    
    # Browser operations
    BROWSE = "browse"
    BROWSE_INTERACTIVE = "browse_interactive"
    
    # Agent actions
    THINK = "think"
    FINISH = "finish"
    REJECT = "reject"
    DELEGATE = "delegate"
    CHANGE_AGENT_STATE = "change_agent_state"
    RECALL = "recall"
    
    # Special actions
    NULL = "null"
    TOOL_CALL = "tool_call"  # ii-agent specific
    COMPLETE = "complete"    # ii-agent specific
    MCP = "mcp"  # MCP server action


class ObservationType(str, Enum):
    """Enumeration of all possible observation types in ii-agent."""
    
    # Core observations
    NULL = "null"
    ERROR = "error"
    SUCCESS = "success"
    
    # File operations
    READ = "read"
    WRITE = "write"
    EDIT = "edit"
    
    # Command execution  
    RUN = "run"
    RUN_IPYTHON = "run_ipython"
    
    # Browser operations
    BROWSE = "browse"
    
    # Agent observations
    THINK = "think"
    STATE_CHANGED = "agent_state_changed"
    DELEGATE = "delegate"
    CONDENSATION = "condensation"
    RECALL = "recall"
    
    # Tool operations
    TOOL_RESULT = "tool_result"  # ii-agent specific
    
    # User interactions
    USER_MESSAGE = "user_message"   # ii-agent specific
    SYSTEM_MESSAGE = "system_message"  # ii-agent specific
    USER_REJECT = "user_reject"
    
    # File downloads
    FILE_DOWNLOAD = "file_download"
    
    # MCP operations
    MCP = "mcp"


class AgentState(str, Enum):
    """Enumeration of agent states."""
    
    INIT = "init"
    RUNNING = "running" 
    PAUSED = "paused"
    STOPPED = "stopped"
    FINISHED = "finished"
    ERROR = "error"
    REJECTED = "rejected"


class FileEditSource(str, Enum):
    """Source of file edit implementation."""
    
    LLM_BASED_EDIT = "llm_based_edit"
    DEFAULT = "default"  


class FileReadSource(str, Enum):
    """Source of file read implementation."""
    
    DEFAULT = "default"
    
    
class SecurityRisk(int, Enum):
    """Security risk levels for actions."""
    
    UNKNOWN = -1
    LOW = 0
    MEDIUM = 1
    HIGH = 2


class ConfirmationStatus(str, Enum):
    """Status of action confirmation."""
    
    CONFIRMED = "confirmed"
    REJECTED = "rejected"  
    AWAITING_CONFIRMATION = "awaiting_confirmation"