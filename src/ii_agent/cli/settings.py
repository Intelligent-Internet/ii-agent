"""CLI settings management for ii-agent."""

import argparse
import os
import sys
from typing import Optional

from prompt_toolkit import print_formatted_text
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.shortcuts import prompt

from ii_agent.core.config.ii_agent_config import IIAgentConfig
from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.core.storage.settings.file_settings_store import FileSettingsStore
from ii_agent.core.storage.models.settings import Settings


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='II-Agent CLI - Intelligent Agent Platform',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  ii-agent                          # Interactive mode
  ii-agent --task "Build a website" # Direct task execution
  ii-agent --file task.txt          # Task from file
  ii-agent --name "My Session"      # Named session
        '''
    )
    
    parser.add_argument(
        '--task',
        type=str,
        help='Task to execute directly'
    )
    
    parser.add_argument(
        '--file',
        type=str,
        help='File containing task to execute'
    )
    
    parser.add_argument(
        '--name',
        type=str,
        help='Name for the session'
    )
    
    parser.add_argument(
        '--config',
        type=str,
        help='Path to configuration file'
    )
    
    parser.add_argument(
        '--workspace',
        type=str,
        help='Workspace directory path'
    )
    
    parser.add_argument(
        '--model',
        type=str,
        help='LLM model to use'
    )
    
    parser.add_argument(
        '--api-key',
        type=str,
        help='API key for LLM'
    )
    
    parser.add_argument(
        '--base-url',
        type=str,
        help='Base URL for LLM API'
    )
    
    parser.add_argument(
        '--max-turns',
        type=int,
        default=200,
        help='Maximum number of turns (default: 200)'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug mode'
    )
    
    return parser.parse_args()


def setup_config_from_args(args) -> IIAgentConfig:
    """Setup configuration from command line arguments."""
    config = IIAgentConfig()
    
    if args.workspace:
        config.file_store_path = args.workspace
    
    if args.max_turns:
        config.max_turns = args.max_turns
    
    if args.verbose:
        config.minimize_stdout_logs = False
    
    # Set workspace base to current directory if not specified
    if not hasattr(config, 'workspace_base') or not config.workspace_base:
        config.workspace_base = os.getcwd()
    
    return config


async def modify_llm_settings_basic(config: IIAgentConfig, settings_store: FileSettingsStore):
    """Modify LLM settings with basic setup flow."""
    print_formatted_text(HTML('<b><cyan>LLM Configuration Setup</cyan></b>\\n'))
    
    # Load existing settings
    settings = await settings_store.load()
    if not settings:
        settings = Settings()
    
    # Initialize LLM config
    llm_config = LLMConfig()
    
    # Provider selection
    print_formatted_text(HTML('<b>Select LLM Provider:</b>'))
    print_formatted_text(HTML('1. OpenAI (GPT-4, GPT-3.5, etc.)'))
    print_formatted_text(HTML('2. Anthropic (Claude)'))
    print_formatted_text(HTML('3. Google (Gemini)'))
    print_formatted_text(HTML('4. Custom/Other'))
    
    while True:
        try:
            provider_choice = prompt(HTML('<yellow>Enter choice (1-4): </yellow>'))
            if provider_choice in ['1', '2', '3', '4']:
                break
            else:
                print_formatted_text(HTML('<red>Invalid choice. Please enter 1, 2, 3, or 4.</red>'))
        except KeyboardInterrupt:
            print_formatted_text(HTML('<red>\\nSetup cancelled by user</red>'))
            return
    
    # Model selection based on provider
    if provider_choice == '1':  # OpenAI
        print_formatted_text(HTML('<b>\\nSelect OpenAI Model:</b>'))
        print_formatted_text(HTML('1. gpt-4o (recommended)'))
        print_formatted_text(HTML('2. gpt-4o-mini'))
        print_formatted_text(HTML('3. gpt-4-turbo'))
        print_formatted_text(HTML('4. gpt-3.5-turbo'))
        print_formatted_text(HTML('5. Custom model'))
        
        model_choice = prompt(HTML('<yellow>Enter choice (1-5): </yellow>'))
        model_map = {
            '1': 'gpt-4o',
            '2': 'gpt-4o-mini',
            '3': 'gpt-4-turbo',
            '4': 'gpt-3.5-turbo',
        }
        
        if model_choice in model_map:
            llm_config.model = model_map[model_choice]
        else:
            llm_config.model = prompt(HTML('<yellow>Enter custom model name: </yellow>'))
        
        llm_config.base_url = None  # Use default OpenAI URL
        
    elif provider_choice == '2':  # Anthropic
        print_formatted_text(HTML('<b>\\nSelect Anthropic Model:</b>'))
        print_formatted_text(HTML('1. claude-3-5-sonnet-20241022 (recommended)'))
        print_formatted_text(HTML('2. claude-3-opus-20240229'))
        print_formatted_text(HTML('3. claude-3-haiku-20240307'))
        print_formatted_text(HTML('4. Custom model'))
        
        model_choice = prompt(HTML('<yellow>Enter choice (1-4): </yellow>'))
        model_map = {
            '1': 'claude-3-5-sonnet-20241022',
            '2': 'claude-3-opus-20240229',
            '3': 'claude-3-haiku-20240307',
        }
        
        if model_choice in model_map:
            llm_config.model = model_map[model_choice]
        else:
            llm_config.model = prompt(HTML('<yellow>Enter custom model name: </yellow>'))
        
        llm_config.base_url = None  # Use default Anthropic URL
        
    elif provider_choice == '3':  # Google
        print_formatted_text(HTML('<b>\\nSelect Google Model:</b>'))
        print_formatted_text(HTML('1. gemini-1.5-pro (recommended)'))
        print_formatted_text(HTML('2. gemini-1.5-flash'))
        print_formatted_text(HTML('3. gemini-pro'))
        print_formatted_text(HTML('4. Custom model'))
        
        model_choice = prompt(HTML('<yellow>Enter choice (1-4): </yellow>'))
        model_map = {
            '1': 'gemini-1.5-pro',
            '2': 'gemini-1.5-flash',
            '3': 'gemini-pro',
        }
        
        if model_choice in model_map:
            llm_config.model = model_map[model_choice]
        else:
            llm_config.model = prompt(HTML('<yellow>Enter custom model name: </yellow>'))
        
        llm_config.base_url = None  # Use default Google URL
        
    else:  # Custom
        llm_config.model = prompt(HTML('<yellow>Enter model name: </yellow>'))
        base_url = prompt(HTML('<yellow>Enter base URL (optional): </yellow>'))
        if base_url.strip():
            llm_config.base_url = base_url
    
    # API Key
    print_formatted_text(HTML('<b>\\nAPI Key Configuration:</b>'))
    # Check if there's an existing default LLM config
    current_llm_config = settings.llm_configs.get('default') if settings.llm_configs else None
    current_key = current_llm_config.api_key if current_llm_config else None
    
    if current_key:
        current_key_str = current_key.get_secret_value() if hasattr(current_key, 'get_secret_value') else str(current_key)
        masked_key = current_key_str[:8] + '*' * (len(current_key_str) - 8)
        print_formatted_text(HTML(f'<grey>Current API key: {masked_key}</grey>'))
        change_key = prompt(HTML('<yellow>Change API key? (y/n): </yellow>'))
        if change_key.lower() not in ['y', 'yes']:
            print_formatted_text(HTML('<green>Keeping existing API key</green>'))
            llm_config.api_key = current_key
        else:
            from pydantic import SecretStr
            new_api_key_str = prompt(HTML('<yellow>Enter new API key: </yellow>'), is_password=True)
            llm_config.api_key = SecretStr(new_api_key_str)
    else:
        from pydantic import SecretStr
        api_key_str = prompt(HTML('<yellow>Enter API key: </yellow>'), is_password=True)
        llm_config.api_key = SecretStr(api_key_str)
    
    # Store the LLM config in settings
    if not settings.llm_configs:
        settings.llm_configs = {}
    settings.llm_configs['default'] = llm_config
    
    # CLI-specific preferences (stored separately)
    print_formatted_text(HTML('<b>\\nCLI Preferences:</b>'))
    
    # Agent configuration
    agent_name = prompt(HTML('<yellow>Agent name (default: FunctionCallAgent): </yellow>'))
    if not agent_name.strip():
        agent_name = 'FunctionCallAgent'
    
    # Confirmation settings
    confirmation = prompt(HTML('<yellow>Enable confirmation mode for dangerous operations? (y/n): </yellow>'))
    confirmation_mode = confirmation.lower() in ['y', 'yes']
    
    # Memory settings
    condenser = prompt(HTML('<yellow>Enable default memory condenser? (y/n): </yellow>'))
    enable_condenser = condenser.lower() in ['y', 'yes']
    
    # Save settings
    try:
        await settings_store.store(settings)
        print_formatted_text(HTML('<green>✅ Settings saved successfully!</green>\\n'))
    except Exception as e:
        print_formatted_text(HTML(f'<red>❌ Error saving settings: {e}</red>'))
        sys.exit(1)


async def display_current_settings(settings_store: FileSettingsStore):
    """Display current settings."""
    settings = await settings_store.load()
    if not settings:
        print_formatted_text(HTML('<yellow>No settings found. Run setup first.</yellow>'))
        return
    
    print_formatted_text(HTML('<b><cyan>Current Settings:</cyan></b>\\n'))
    
    # LLM settings
    default_llm = settings.llm_configs.get('default') if settings.llm_configs else None
    
    print_formatted_text(HTML('<b>LLM Configuration:</b>'))
    if default_llm:
        print_formatted_text(HTML(f'<cyan>Model:</cyan> {default_llm.model or "Not set"}'))
        print_formatted_text(HTML(f'<cyan>Base URL:</cyan> {default_llm.base_url or "Default"}'))
        
        if default_llm.api_key:
            api_key_str = default_llm.api_key.get_secret_value() if hasattr(default_llm.api_key, 'get_secret_value') else str(default_llm.api_key)
            masked_key = api_key_str[:8] + '*' * (len(api_key_str) - 8)
            print_formatted_text(HTML(f'<cyan>API Key:</cyan> {masked_key}'))
        else:
            print_formatted_text(HTML('<cyan>API Key:</cyan> <red>Not set</red>'))
    else:
        print_formatted_text(HTML('<yellow>No LLM configuration found</yellow>'))
    
    # Other configurations
    if settings.search_config:
        print_formatted_text(HTML('<b>\\nSearch Configuration:</b>'))
        print_formatted_text(HTML(f'<cyan>Provider:</cyan> {settings.search_config.provider}'))
    
    if settings.media_config:
        print_formatted_text(HTML('<b>\\nMedia Configuration:</b>'))
        print_formatted_text(HTML('<cyan>Media settings configured</cyan>'))
    
    if settings.audio_config:
        print_formatted_text(HTML('<b>\\nAudio Configuration:</b>'))
        print_formatted_text(HTML('<cyan>Audio settings configured</cyan>'))
    
    print_formatted_text('')


async def reset_settings(settings_store: FileSettingsStore):
    """Reset settings to defaults."""
    print_formatted_text(HTML('<b><yellow>⚠️ Reset Settings</yellow></b>\\n'))
    print_formatted_text(HTML('<yellow>This will delete all current settings.</yellow>'))
    
    confirm = prompt(HTML('<yellow>Are you sure? (y/n): </yellow>'))
    if confirm.lower() not in ['y', 'yes']:
        print_formatted_text(HTML('<green>Reset cancelled</green>'))
        return
    
    try:
        # Create empty settings and store them (effectively resetting)
        empty_settings = Settings()
        await settings_store.store(empty_settings)
        print_formatted_text(HTML('<green>✅ Settings reset successfully!</green>'))
    except Exception as e:
        print_formatted_text(HTML(f'<red>❌ Error resetting settings: {e}</red>'))


def validate_settings(settings: Settings) -> bool:
    """Validate settings configuration."""
    if not settings or not settings.llm_configs:
        print_formatted_text(HTML('<red>❌ No LLM configurations found</red>'))
        return False
    
    default_llm = settings.llm_configs.get('default')
    if not default_llm:
        print_formatted_text(HTML('<red>❌ No default LLM configuration found</red>'))
        return False
    
    if not default_llm.model:
        print_formatted_text(HTML('<red>❌ LLM model not configured</red>'))
        return False
    
    if not default_llm.api_key:
        print_formatted_text(HTML('<red>❌ API key not configured</red>'))
        return False
    
    return True


def get_workspace_path(args) -> str:
    """Get workspace path from args or current directory."""
    if args.workspace:
        return os.path.abspath(args.workspace)
    return os.getcwd()


def check_dependencies():
    """Check if required dependencies are installed."""
    try:
        import prompt_toolkit
        import rich
        # Add other required imports for CLI
        return True
    except ImportError as e:
        print_formatted_text(HTML(f'<red>❌ Missing dependency: {e}</red>'))
        print_formatted_text(HTML('<yellow>Please install with: pip install ii-agent[cli]</yellow>'))
        return False