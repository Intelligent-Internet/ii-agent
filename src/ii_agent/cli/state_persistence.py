"""
State persistence system for CLI --continue feature.

This module provides functionality to save and restore the complete agent state
including conversation history, configuration, and workspace context.
"""

import json
import os
import glob
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
import uuid

from ii_agent.cli.session_config import SessionConfig
from ii_agent.core.config.ii_agent_config import IIAgentConfig
from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.controller.state import State
from ii_agent.core.logger import logger
from ii_agent.core.storage.local import LocalFileStore
from ii_agent.core.storage.locations import get_conversation_agent_history_filename, get_conversation_metadata_filename, CONVERSATION_BASE_DIR
from ii_agent.core.storage.models.settings import Settings
from ii_agent.runtime.model.constants import RuntimeMode


class StateManager:
    """Manages saving and loading of agent state for --continue functionality."""

    def __init__(
        self, config: IIAgentConfig, settings: Settings
    ):
        self.workspace_path = config.file_store_path
        self.config = config
        self.settings = settings
        self.file_store = LocalFileStore(self.workspace_path)
    
    def get_metadata(self, session_id: str) -> Optional[Dict[str, Any]]:
        try:
            metadata_filename = get_conversation_metadata_filename(session_id)
            metadata = self.file_store.read(metadata_filename)
            metadata = json.loads(metadata)
            return metadata
        except Exception:
            return None
    
    def get_state_config(self, session_id: Optional[str] = None) -> SessionConfig:
        if not session_id or not self.is_valid_session(session_id):
            session_id = uuid.uuid4().hex
            session_name = None
            runtime_mode = self.settings.runtime_config.mode
            return SessionConfig(session_id=session_id, session_name=session_name, mode=runtime_mode)
        else:
            metadata = self.get_metadata(session_id)
            if "runtime_mode" not in metadata: # type: ignore
                runtime_mode = self.settings.runtime_config.mode
            return SessionConfig(session_id=session_id, session_name=metadata["session_name"], mode=RuntimeMode(metadata["runtime_mode"])) # type: ignore
            
    def is_valid_session(self, session_id: str) -> bool:
        return self.get_metadata(session_id) is not None and self.get_state(session_id) is not None
    
    def get_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        try:
            state_filename = get_conversation_agent_history_filename(session_id)
            state = self.file_store.read(state_filename)
            state = json.loads(state)
            return state
        except Exception as e:
            return None

    def get_available_sessions(self) -> list[str]:
        try:
            sessions_dir = Path(os.path.join(self.workspace_path, CONVERSATION_BASE_DIR))
            if not sessions_dir.exists():
                return []
            
            sessions = []
            for session_dir in sessions_dir.glob("*"):
                if session_dir.is_dir():
                    json_files = list(session_dir.glob("*.json"))
                    if json_files:
                        sessions.append(session_dir.name)
            
            return sorted(sessions)
        except Exception as e:
            return []
    
    def save_state(
        self, 
        session_id: str,
        agent_state: State,
        config: IIAgentConfig,
        llm_config: LLMConfig,
        workspace_path: str,
        session_name: Optional[str] = None
    ) -> None:
        """Save state and metadata using the new JSON format."""
        try:
            # Save core state using State's save_to_session method
            agent_state.save_to_session(session_id, self.file_store)
            
            # Save metadata separately
            metadata = {
                "version": "2.0",
                "timestamp": datetime.now().isoformat(),
                "session_id": session_id,
                "workspace_path": str(workspace_path),
                "session_name": session_name,
                "runtime_mode": self.settings.runtime_config.mode.value,
                "agent_state": {
                    "message_count": len(agent_state.message_lists)
                },
                "config": {
                    "max_output_tokens_per_turn": config.max_output_tokens_per_turn,
                    "max_turns": config.max_turns,
                    "debug": getattr(config, 'debug', False)
                },
                "llm_config": {
                    "model": llm_config.model,
                    "temperature": llm_config.temperature,
                    "max_message_chars": llm_config.max_message_chars,
                    "api_type": llm_config.api_type.value if llm_config.api_type else 'anthropic',
                    "max_retries": llm_config.max_retries
                }
            }
            
            metadata_filename = get_conversation_metadata_filename(session_id)
            self.file_store.write(metadata_filename, json.dumps(metadata, indent=2, ensure_ascii=False))
            logger.info(f"State saved for session {session_id}")
            
        except Exception as e:
            raise
    
    def load_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Load the saved agent state from current state pointer."""
        try:
            # First, check if current_state.json exists
            chat_history = self.get_state(session_id)
            metadata = self.get_metadata(session_id)

            if not chat_history or not metadata:
                return None
            
            # Create a new State object and restore from session
            state = State()
            state.restore_from_session(session_id, self.file_store)
            
            # Combine state and metadata into return format
            return {
                "version": metadata.get("version", "2.0"),
                "timestamp": metadata.get("timestamp"),
                "workspace_path": metadata.get("workspace_path"),
                "session_name": metadata.get("session_name"),
                "session_id": metadata.get("session_id"),
                "agent_state": {
                    "message_lists": state.message_lists,
                    "last_user_prompt_index": state.last_user_prompt_index
                },
                "config": metadata.get("config", {}),
                "llm_config": metadata.get("llm_config", {})
            }
                
        except Exception as e:
            logger.error(f"Error loading state: {e}")
            return None
    
    def load_state_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get basic info about the saved state without loading it."""
        try:
            chat_history = self.get_state(session_id)
            metadata = self.get_metadata(session_id)
            if not chat_history or not metadata:
                return None
            return {
                "timestamp": metadata.get("timestamp"),
                "session_name": metadata.get("session_name"),
                "workspace_path": metadata.get("workspace_path"),
                "version": metadata.get("version", "2.0"),
                "session_id": metadata.get("session_id"),
                "message_count": metadata.get("agent_state", {}).get("message_count", 0)
            }
        except Exception as e:
            logger.error(f"Error getting state info: {e}")
            return None
    
    def load_state_summary(self, session_id: str) -> str:
        sessions_dir = Path.home() / ".ii_agent" / "sessions"
        state_file = sessions_dir / session_id / "agent_state.json"
        if state_file.exists():
            with open(state_file, "r") as f:
                data = json.load(f)

            # Extract meaningful information
            info_lines = []

            # User Message
            if "last_user_prompt_index" in data:
                last_user_prompt = data["message_lists"][
                    int(data["last_user_prompt_index"])
                ][0]["text"]
                if len(last_user_prompt) > 50:
                    last_user_prompt = "..." + last_user_prompt[-47:]
                info_lines.append(f"User: {last_user_prompt}")

            # Message count
            if "message_lists" in data and data["message_lists"]:
                message_count = len(data["message_lists"])
                info_lines.append(f"💬 Messages: {message_count}")

                # Get last few message summaries
                recent_messages = []
                for msg_list in data["message_lists"][
                    -2:
                ]:  # Last 2 message lists
                    messages = msg_list
                    for msg in messages[-3:]:  # Last 3 messages from each list
                        if msg.get("text"):
                            content = msg["text"][:100]
                            if len(msg["text"]) > 100:
                                content += "..."
                            recent_messages.append(content)

                if recent_messages:
                    info_lines.append("📝 Recent messages:")
                    info_lines.extend(recent_messages[-3:])  # Show only last 3

            # File size info
            file_size = state_file.stat().st_size
            size_str = f"{file_size} bytes"
            if file_size > 1024:
                size_str = f"{file_size / 1024:.1f} KB"
            if file_size > 1024 * 1024:
                size_str = f"{file_size / (1024 * 1024):.1f} MB"
            info_lines.append(f"📊 File size: {size_str}")

            return (
                "\n".join(info_lines) if info_lines else "No details available"
            )
        else:
            return "❌ No state file found"


def restore_agent_state(state_data: Dict[str, Any]) -> State:
    """Restore a State object from saved state data."""
    agent_state = State()
    
    if "agent_state" in state_data:
        saved_agent_state = state_data["agent_state"]
        
        # Restore message lists
        if "message_lists" in saved_agent_state:
            agent_state.message_lists = saved_agent_state["message_lists"]
        
        # Restore last user prompt index
        if "last_user_prompt_index" in saved_agent_state:
            agent_state.last_user_prompt_index = saved_agent_state["last_user_prompt_index"]
    
    return agent_state


def restore_configs(state_data: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Extract configuration data from saved state."""
    from ii_agent.core.config.llm_config import APITypes
    
    config_data = state_data.get("config", {})
    llm_config_data = state_data.get("llm_config", {})
    
    # Convert api_type string back to enum if present
    if "api_type" in llm_config_data and isinstance(llm_config_data["api_type"], str):
        try:
            llm_config_data["api_type"] = APITypes(llm_config_data["api_type"])
        except ValueError:
            # If invalid enum value, default to anthropic
            llm_config_data["api_type"] = APITypes.ANTHROPIC
    
    return config_data, llm_config_data