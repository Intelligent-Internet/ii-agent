"""
Configuration management for CLI.

This module handles loading, saving, and managing CLI configuration options.
"""

import asyncio
import os
from pathlib import Path
from typing import Optional

from ii_agent.core.config.ii_agent_config import IIAgentConfig
from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.core.storage.settings.file_settings_store import FileSettingsStore
from pydantic import SecretStr


async def setup_cli_config(
    workspace: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    temperature: Optional[float] = None,
    vertex_region: Optional[str] = None,
    vertex_project_id: Optional[str] = None
) -> tuple[IIAgentConfig, LLMConfig, str]:
    """Setup CLI configuration using the standard configuration pattern."""
    
    # Don't parse arguments here - they're already parsed in main
    # Just create config with defaults
    config = IIAgentConfig()
    
    # Load settings from store
    settings_store = await FileSettingsStore.get_instance(config=config, user_id=None)
    settings = await settings_store.load()
    
    # Create LLM and agent configs from settings
    llm_config = LLMConfig()
    
    if settings and settings.llm_configs:
        # Get the default LLM config if it exists
        default_llm_config = settings.llm_configs.get('default')
        if default_llm_config:
            llm_config = default_llm_config
    
    # CLI arguments are passed as parameters, no need to parse them again
    
    # Override with passed parameters
    if model:
        llm_config.model = model
    if api_key:
        llm_config.api_key = SecretStr(api_key)
    if base_url:
        llm_config.base_url = base_url
    if temperature is not None:
        llm_config.temperature = temperature
    
    # Handle vertex configuration with fallback to environment variables
    if vertex_region:
        llm_config.vertex_region = vertex_region
    elif not llm_config.vertex_region:
        llm_config.vertex_region = os.environ.get('VERTEX_REGION')
    
    if vertex_project_id:
        llm_config.vertex_project_id = vertex_project_id
    elif not llm_config.vertex_project_id:
        llm_config.vertex_project_id = os.environ.get('VERTEX_PROJECT_ID')
    
    # Determine workspace path
    workspace_path = workspace or "."
    
    return config, llm_config, workspace_path