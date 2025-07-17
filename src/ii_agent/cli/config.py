"""
Configuration management for CLI.

This module handles loading, saving, and managing CLI configuration options.
"""

import os
from typing import Optional

from ii_agent.core.config.ii_agent_config import IIAgentConfig
from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.core.storage.settings.file_settings_store import FileSettingsStore
from ii_agent.cli.settings_onboard import run_first_time_setup
from pydantic import SecretStr


async def setup_cli_config(
    workspace: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    temperature: Optional[float] = None,
) -> tuple[IIAgentConfig, LLMConfig, str]:
    """Setup CLI configuration using the standard configuration pattern."""
    
    # Create config with defaults
    config = IIAgentConfig()
    
    # Load settings from store
    settings_store = await FileSettingsStore.get_instance(config=config, user_id=None)
    settings = await settings_store.load()
    
    # If no settings exist, run first-time setup
    if not settings or not settings.llm_configs or not settings.llm_configs.get('default'):
        print("No configuration found. Running first-time setup...")
        setup_success = await run_first_time_setup(settings_store)
        if not setup_success:
            raise RuntimeError("Failed to complete initial setup")
        
        # Reload settings after setup
        settings = await settings_store.load()
    
    # Create LLM config from settings
    llm_config = LLMConfig()
    
    if settings and settings.llm_configs:
        # Get the default LLM config if it exists
        default_llm_config = settings.llm_configs.get('default')
        if default_llm_config:
            llm_config = default_llm_config
    
    # Override with passed parameters (CLI arguments take precedence)
    if model:
        llm_config.model = model
    if api_key:
        llm_config.api_key = SecretStr(api_key)
    if base_url:
        llm_config.base_url = base_url
    if temperature is not None:
        llm_config.temperature = temperature
    
    # Handle vertex configuration with fallback to environment variables
    # Note: vertex args are removed from CLI, so only check environment variables
    if not llm_config.vertex_region:
        llm_config.vertex_region = os.environ.get('VERTEX_REGION')
    
    if not llm_config.vertex_project_id:
        llm_config.vertex_project_id = os.environ.get('VERTEX_PROJECT_ID')
    
    # Determine workspace path
    workspace_path = workspace or "."
    
    return config, llm_config, workspace_path