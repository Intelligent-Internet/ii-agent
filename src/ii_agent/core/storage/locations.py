CONVERSATION_BASE_DIR = "sessions"


def get_conversation_agent_history_filename(sid: str) -> str:
    return f"{CONVERSATION_BASE_DIR}/{sid}/agent_state.json"
