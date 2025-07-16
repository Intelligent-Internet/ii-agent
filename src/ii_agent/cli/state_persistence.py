"""
State persistence system for CLI --continue feature.

This module provides functionality to save and restore the complete agent state
including conversation history, configuration, and workspace context.
"""

import json
import pickle
import base64
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from ii_agent.core.config.ii_agent_config import IIAgentConfig
from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.controller.state import State
from ii_agent.core.logger import logger


class StateManager:
    """Manages saving and loading of agent state for --continue functionality."""
    
    def __init__(self, workspace_path: Path):
        self.workspace_path = workspace_path
        self.state_file_path = workspace_path / ".ii-agent-state.json"
    
    def save_state(
        self, 
        agent_state: State,
        config: IIAgentConfig,
        llm_config: LLMConfig,
        workspace_path: str,
        session_name: Optional[str] = None
    ) -> None:
        """Save the complete agent state to file."""
        try:
            # Serialize the agent state (message history)
            pickled_state = pickle.dumps(agent_state.message_lists)
            encoded_state = base64.b64encode(pickled_state).decode('utf-8')
            
            # Create state data structure
            state_data = {
                "version": "1.0",
                "timestamp": datetime.now().isoformat(),
                "workspace_path": str(workspace_path),
                "session_name": session_name,
                "agent_state": {
                    "message_lists": encoded_state,
                    "last_user_prompt_index": agent_state.last_user_prompt_index
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
            
            # Write to file
            with open(self.state_file_path, 'w') as f:
                json.dump(state_data, f, indent=2)
                
            logger.info(f"State saved to {self.state_file_path}")
            
        except Exception as e:
            logger.error(f"Error saving state: {e}")
            raise
    
    def load_state(self) -> Optional[Dict[str, Any]]:
        """Load the saved agent state from file."""
        try:
            if not self.state_file_path.exists():
                return None
                
            with open(self.state_file_path, 'r') as f:
                state_data = json.load(f)
            
            # Validate version compatibility
            if state_data.get("version") != "1.0":
                logger.warning(f"State version {state_data.get('version')} may not be compatible")
            
            # Decode agent state
            if "agent_state" in state_data and "message_lists" in state_data["agent_state"]:
                encoded_state = state_data["agent_state"]["message_lists"]
                pickled_state = base64.b64decode(encoded_state)
                message_lists = pickle.loads(pickled_state)
                state_data["agent_state"]["message_lists"] = message_lists
            
            logger.info(f"State loaded from {self.state_file_path}")
            return state_data
            
        except Exception as e:
            logger.error(f"Error loading state: {e}")
            return None
    
    def clear_state(self) -> None:
        """Remove the saved state file."""
        try:
            if self.state_file_path.exists():
                self.state_file_path.unlink()
                logger.info(f"State file {self.state_file_path} removed")
        except Exception as e:
            logger.error(f"Error clearing state: {e}")
    
    def has_saved_state(self) -> bool:
        """Check if there's a saved state file."""
        return self.state_file_path.exists()
    
    def get_state_info(self) -> Optional[Dict[str, Any]]:
        """Get basic info about the saved state without loading it."""
        try:
            if not self.state_file_path.exists():
                return None
                
            with open(self.state_file_path, 'r') as f:
                state_data = json.load(f)
            
            return {
                "timestamp": state_data.get("timestamp"),
                "session_name": state_data.get("session_name"),
                "workspace_path": state_data.get("workspace_path"),
                "version": state_data.get("version"),
                "message_count": len(state_data.get("agent_state", {}).get("message_lists", []))
            }
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