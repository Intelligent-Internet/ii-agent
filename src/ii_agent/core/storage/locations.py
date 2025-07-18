import hashlib

CONVERSATION_BASE_DIR = "sessions"


def get_conversation_agent_history_filename(sid: str) -> str:
    """Returns path to state file (core conversation data only)"""
    return f"{CONVERSATION_BASE_DIR}/{sid}/agent_state.json"


def get_conversation_metadata_filename(sid: str) -> str:
    """Returns path to metadata file"""
    return f"{CONVERSATION_BASE_DIR}/{sid}/metadata.json"
