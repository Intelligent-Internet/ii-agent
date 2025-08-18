"""
State persistence system for CLI --continue feature.

This module provides functionality to save and restore the complete agent state
including conversation history, configuration, and workspace context.
"""

import os
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from ii_agent.core.config.ii_agent_config import IIAgentConfig
from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.controller.state import State
from ii_agent.core.logger import logger
from ii_agent.core.storage.local import LocalFileStore
from ii_agent.core.storage.locations import get_conversation_metadata_filename


class StateManager:
    """Manages saving and loading of agent state for --continue functionality."""
    
    def __init__(self, workspace_path: Path, continue_session: bool = False, session_id: str = None, local_file_storage="~/.ii_agent"):
        self.workspace_path = str(workspace_path)
        self.ii_agent_dir = workspace_path / ".ii_agent"
        self.ii_agent_dir.mkdir(exist_ok=True)
        self.current_state_link = self.ii_agent_dir / "current_state.json"
        # Use the global file store location
        self.file_store = LocalFileStore(local_file_storage)
        
        # Determine session ID based on whether we're continuing or starting fresh
        if continue_session and self.current_state_link.exists():
            try:
                with open(self.current_state_link, 'r') as f:
                    current_state_info = json.load(f)
                existing_session_id = current_state_info.get("current_session_id")
                if existing_session_id:
                    self.session_id = existing_session_id
                    logger.info(f"Continuing with existing session: {self.session_id}")
                else:
                    self.session_id = uuid.uuid4().hex
                    logger.info(f"No valid session found, creating new session: {self.session_id}")
            except Exception as e:
                logger.warning(f"Error reading existing session, creating new one: {e}")
                self.session_id = uuid.uuid4().hex
        else:
            self.session_id = uuid.uuid4().hex
            if session_id is not None:
                self.session_id = session_id
            if not continue_session:
                logger.info(f"Starting new session: {self.session_id}")
    
    def save_state(
        self, 
        agent_state: State,
        config: IIAgentConfig,
        llm_config: LLMConfig,
        workspace_path: str,
        session_name: Optional[str] = None,
        agent_state_global: State = None
    ) -> None:
        """Save state and metadata using the new JSON format."""
        try:
            # Save core state using State's save_to_session method
            agent_state.save_to_session(self.session_id, self.file_store)
            
            # Save metadata separately
            metadata = {
                "version": "2.0",
                "timestamp": datetime.now().isoformat(),
                "session_id": self.session_id,
                "workspace_path": str(workspace_path),
                "session_name": session_name,
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
            
            metadata_filename = get_conversation_metadata_filename(self.session_id)
            self.file_store.write(metadata_filename, json.dumps(metadata, indent=2, ensure_ascii=False))
            
            # Update current state pointer
            current_state_info = {
                "current_session_id": self.session_id,
                "workspace_path": self.workspace_path,
                "last_updated": datetime.now().isoformat()
            }
            with open(self.current_state_link, 'w') as f:
                json.dump(current_state_info, f, indent=2)
                
            logger.info(f"State saved for session {self.session_id}")
            
        except Exception as e:
            logger.error(f"Error saving state: {e}")
            raise
    
    def load_state(self) -> Optional[Dict[str, Any]]:
        """Load the saved agent state from current state pointer."""
        try:
            # First, check if current_state.json exists
            if not self.current_state_link.exists():
                return None
            
            # Read the current state pointer
            with open(self.current_state_link, 'r') as f:
                current_state_info = json.load(f)
            
            session_id = current_state_info.get("current_session_id")
            workspace_path = current_state_info.get("workspace_path")
            
            if not session_id:
                return None
            
            # Create a new State object and restore from session
            state = State()
            state.restore_from_session(session_id, self.file_store)
            
            # Load metadata
            metadata_filename = get_conversation_metadata_filename(session_id)
            metadata_json = self.file_store.read(metadata_filename)
            metadata = json.loads(metadata_json)
            
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
    
    
    def clear_state(self) -> None:
        """Remove the saved state files."""
        try:
            # Remove current state pointer
            if self.current_state_link.exists():
                self.current_state_link.unlink()
                logger.info(f"Current state pointer {self.current_state_link} removed")
        except Exception as e:
            logger.error(f"Error clearing state: {e}")
    
    def has_saved_state(self) -> bool:
        """Check if there's a saved state file."""
        return self.current_state_link.exists()
    
    def get_state_info(self) -> Optional[Dict[str, Any]]:
        """Get basic info about the saved state without loading it."""
        try:
            if not self.current_state_link.exists():
                return None
            
            # Read current state pointer
            with open(self.current_state_link, 'r') as f:
                current_state_info = json.load(f)
            
            session_id = current_state_info.get("current_session_id")
            workspace_path = current_state_info.get("workspace_path")
            
            if not session_id:
                return None
            
            # Read metadata file
            metadata_filename = get_conversation_metadata_filename(session_id)
            try:
                metadata_json = self.file_store.read(metadata_filename)
                metadata = json.loads(metadata_json)
                
                return {
                    "timestamp": metadata.get("timestamp"),
                    "session_name": metadata.get("session_name"),
                    "workspace_path": metadata.get("workspace_path"),
                    "version": metadata.get("version", "2.0"),
                    "session_id": metadata.get("session_id"),
                    "message_count": metadata.get("agent_state", {}).get("message_count", 0)
                }
            except FileNotFoundError:
                return None
            
        except Exception as e:
            logger.error(f"Error getting state info: {e}")
            return None


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