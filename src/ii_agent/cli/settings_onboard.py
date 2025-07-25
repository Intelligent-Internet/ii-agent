"""
Settings onboarding module for ii-agent CLI.

This module provides interactive configuration setup for first-time users
and runtime settings management, similar to OpenHands approach.
"""

import os

from prompt_toolkit import PromptSession, print_formatted_text
from prompt_toolkit.completion import FuzzyWordCompleter
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.shortcuts import print_container
from prompt_toolkit.widgets import Frame, TextArea
from pydantic import SecretStr

from ii_agent.core.config.llm_config import LLMConfig, APITypes
from ii_agent.core.config.runtime_config import RuntimeConfig
from ii_agent.core.storage.models.settings import Settings
from ii_agent.core.storage.settings.file_settings_store import FileSettingsStore
from ii_agent.runtime.model.constants import RuntimeMode
from ii_agent.utils.constants import DEFAULT_MODEL
from dotenv import load_dotenv

load_dotenv()


# Verified models for each provider
VERIFIED_ANTHROPIC_MODELS = [
    "claude-sonnet-4@20250514",
    "claude-opus-4@20250514",
    "claude-3-7-sonnet@20250219"
]

VERIFIED_OPENAI_MODELS = [
    "gpt-4o",
    "gpt-4o-mini",
]

VERIFIED_GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
]

VERIFIED_PROVIDERS = ["anthropic", "openai", "gemini"]

# Color constants for styling
COLOR_GREY = "#888888"


class UserCancelledError(Exception):
    """Raised when user cancels the setup process."""
    pass


def cli_confirm(question: str, choices: list[str]) -> int:
    """Simple confirmation dialog."""
    print_formatted_text(HTML(f'<grey>{question}</grey>'))
    for i, choice in enumerate(choices):
        print_formatted_text(HTML(f'<grey>{i + 1}. {choice}</grey>'))
    
    while True:
        try:
            response = input("Enter your choice (number): ").strip()
            choice_num = int(response) - 1
            if 0 <= choice_num < len(choices):
                return choice_num
            else:
                print_formatted_text(HTML('<red>Invalid choice. Please try again.</red>'))
        except ValueError:
            print_formatted_text(HTML('<red>Please enter a valid number.</red>'))
        except KeyboardInterrupt:
            raise UserCancelledError("User cancelled setup")


def display_settings(settings: Settings) -> None:
    """Display current settings in a formatted way."""
    if not settings.llm_configs:
        print_formatted_text(HTML('<grey>No LLM configurations found.</grey>'))
        return
    
    # Display default LLM configuration
    default_llm = settings.llm_configs.get('default')
    if not default_llm:
        print_formatted_text(HTML('<grey>No default LLM configuration found.</grey>'))
        return
    
    # Prepare labels and values
    labels_and_values = [
        ('   Provider', default_llm.api_type.value),
        ('   Model', default_llm.model),
        ('   API Key', 'Vertex AI Auth' if default_llm.api_key and default_llm.api_key.get_secret_value() == 'vertex-ai-auth' else '********' if default_llm.api_key else 'Not Set'),
        ('   Base URL', default_llm.base_url or 'Default'),
        ('   Temperature', str(default_llm.temperature)),
    ]
    
    # Add Vertex AI specific settings if applicable
    if default_llm.api_type in [APITypes.GEMINI, APITypes.ANTHROPIC]:
        labels_and_values.extend(
            [
                ("   Vertex Region", default_llm.vertex_region or "Not Set"),
                ("   Vertex Project ID", default_llm.vertex_project_id or "Not Set"),
            ]
        )

    # Add runtime configuration
    if settings.runtime_config:
        labels_and_values.extend(
            [
                ("   Runtime Mode", settings.runtime_config.mode.value),
                ("   Template ID", settings.runtime_config.template_id or "Not Set"),
                (
                    "   Runtime API Key",
                    "********"
                    if settings.runtime_config.runtime_api_key
                    else "Not Set",
                ),
            ]
        )

    # Calculate max width for alignment
    max_label_width = max(len(label) for label, _ in labels_and_values)
    
    # Construct the summary text
    settings_lines = [
        f'{label + ":":<{max_label_width + 1}} {value}'
        for label, value in labels_and_values
    ]
    settings_text = '\n'.join(settings_lines)
    
    container = Frame(
        TextArea(
            text=settings_text,
            read_only=True,
            style=COLOR_GREY,
            wrap_lines=True,
        ),
        title='Current Settings',
        style=f'fg:{COLOR_GREY}',
    )
    
    print_container(container)


async def get_validated_input(
    session: PromptSession,
    prompt_text: str,
    completer=None,
    validator=None,
    error_message: str = 'Input cannot be empty',
    is_password: bool = False,
) -> str:
    """Get validated input from user."""
    session.completer = completer
    value = None
    
    while True:
        try:
            if is_password:
                value = await session.prompt_async(prompt_text, is_password=True)
            else:
                value = await session.prompt_async(prompt_text)
            
            if validator:
                is_valid = validator(value)
                if not is_valid:
                    print_formatted_text('')
                    print_formatted_text(HTML(f'<red>{error_message}: {value}</red>'))
                    print_formatted_text('')
                    continue
            elif not value:
                print_formatted_text('')
                print_formatted_text(HTML(f'<red>{error_message}</red>'))
                print_formatted_text('')
                continue
            
            break
        except KeyboardInterrupt:
            raise UserCancelledError("User cancelled setup")
    
    return value


def save_settings_confirmation() -> bool:
    """Ask user if they want to save the settings."""
    return cli_confirm(
        '\nSave new settings? (They will take effect immediately)',
        ['Yes, save', 'No, discard']
    ) == 0


async def setup_llm_configuration(settings_store: FileSettingsStore) -> None:
    """Interactive setup for LLM configuration."""
    session = PromptSession()
    
    try:
        # Step 1: Select provider
        print_formatted_text(HTML('\n<green>Setting up LLM Configuration</green>'))
        print_formatted_text(HTML('<grey>Choose your preferred LLM provider:</grey>\n'))
        
        provider_choice = cli_confirm(
            'Select LLM Provider:',
            VERIFIED_PROVIDERS
        )
        
        provider = VERIFIED_PROVIDERS[provider_choice]
        api_type = APITypes(provider)
        
        # Step 2: Select model
        if provider == 'anthropic':
            available_models = VERIFIED_ANTHROPIC_MODELS
        elif provider == 'openai':
            available_models = VERIFIED_OPENAI_MODELS
        elif provider == 'gemini':
            available_models = VERIFIED_GEMINI_MODELS
        else:
            available_models = [DEFAULT_MODEL]
        
        print_formatted_text(HTML(f'\n<grey>Default model: </grey><green>{available_models[0]}</green>'))
        
        change_model = cli_confirm(
            'Do you want to use a different model?',
            [f'Use {available_models[0]}', 'Select another model']
        ) == 1
        
        if change_model:
            model_completer = FuzzyWordCompleter(available_models)
            
            def model_validator(x):
                if not x.strip():
                    return False
                if x not in available_models:
                    print_formatted_text(HTML(
                        f'<yellow>Warning: {x} is not in the verified list for {provider}. '
                        f'Make sure this model name is correct.</yellow>'
                    ))
                return True
            
            model = await get_validated_input(
                session,
                'Enter model name (TAB for options, CTRL-C to cancel): ',
                completer=model_completer,
                validator=model_validator,
                error_message='Model name cannot be empty'
            )
        else:
            model = available_models[0]
        
        # Step 3: API Key (with Vertex AI support)
        api_key = None
        
        # For Vertex AI providers, check for existing authentication
        if provider in ['anthropic', 'gemini']:
            google_app_creds = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
            if google_app_creds:
                print_formatted_text(HTML(f'<green>Found GOOGLE_APPLICATION_CREDENTIALS: {google_app_creds}</green>'))
                use_existing_creds = cli_confirm(
                    'Use existing Google Application Credentials?',
                    ['Yes, use existing credentials', 'No, enter API key manually']
                ) == 0
                
                if use_existing_creds:
                    api_key = 'vertex-ai-auth'  # Placeholder for Vertex AI auth
                else:
                    api_key = await get_validated_input(
                        session,
                        'Enter API Key (CTRL-C to cancel): ',
                        error_message='API Key cannot be empty',
                        is_password=True
                    )
            else:
                print_formatted_text(HTML('<yellow>No GOOGLE_APPLICATION_CREDENTIALS found.</yellow>'))
                auth_choice = cli_confirm(
                    'How would you like to authenticate?',
                    ['Set up Google Application Credentials', 'Enter API key manually']
                )
                
                if auth_choice == 0:
                    print_formatted_text(HTML('<grey>Please set up Google Application Credentials:</grey>'))
                    print_formatted_text(HTML('<grey>1. Create a service account in Google Cloud Console</grey>'))
                    print_formatted_text(HTML('<grey>2. Download the JSON key file</grey>'))
                    print_formatted_text(HTML('<grey>3. Set GOOGLE_APPLICATION_CREDENTIALS environment variable</grey>'))
                    
                    creds_path = await get_validated_input(
                        session,
                        'Enter path to service account JSON file: ',
                        error_message='Path cannot be empty'
                    )
                    
                    if os.path.exists(creds_path):
                        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = creds_path
                        print_formatted_text(HTML(f'<green>✓ Set GOOGLE_APPLICATION_CREDENTIALS to {creds_path}</green>'))
                        api_key = 'vertex-ai-auth'
                    else:
                        print_formatted_text(HTML(f'<red>File not found: {creds_path}</red>'))
                        api_key = await get_validated_input(
                            session,
                            'Enter API Key (CTRL-C to cancel): ',
                            error_message='API Key cannot be empty',
                            is_password=True
                        )
                else:
                    api_key = await get_validated_input(
                        session,
                        'Enter API Key (CTRL-C to cancel): ',
                        error_message='API Key cannot be empty',
                        is_password=True
                    )
        else:
            # For non-Vertex AI providers (OpenAI, etc.)
            api_key = await get_validated_input(
                session,
                'Enter API Key (CTRL-C to cancel): ',
                error_message='API Key cannot be empty',
                is_password=True
            )
        
        # Step 4: Optional base URL (only for OpenAI)
        base_url = None
        if provider == 'openai':
            if cli_confirm('Do you want to set a custom base URL?', ['No', 'Yes']) == 1:
                base_url = await get_validated_input(
                    session,
                    'Enter base URL (CTRL-C to cancel): ',
                    error_message='Base URL cannot be empty'
                )
        
        # Step 5: Vertex AI specific settings (for Gemini and Anthropic)
        vertex_region = None
        vertex_project_id = None
        
        if provider in ['gemini', 'anthropic']:
            provider_name = 'Gemini' if provider == 'gemini' else 'Anthropic'
            print_formatted_text(HTML(f'\n<grey>Vertex AI Configuration (required for {provider_name}):</grey>'))
            
            vertex_region = await get_validated_input(
                session,
                'Enter Vertex AI region (e.g., us-east5): ',
                error_message='Vertex region cannot be empty'
            )
            
            vertex_project_id = await get_validated_input(
                session,
                'Enter Vertex AI project ID: ',
                error_message='Vertex project ID cannot be empty'
            )
        
        # Step 6: Temperature setting
        temperature = 0.0
        if cli_confirm('Do you want to set a custom temperature?', ['No (use 0.0)', 'Yes']) == 1:
            temp_input = await get_validated_input(
                session,
                'Enter temperature (0.0-1.0): ',
                validator=lambda x: x.replace('.', '').isdigit() and 0.0 <= float(x) <= 1.0,
                error_message='Temperature must be a number between 0.0 and 1.0'
            )
            temperature = float(temp_input)
        
        # Confirm save
        if not save_settings_confirmation():
            return
        
        # Create and save configuration
        llm_config = LLMConfig(
            model=model,
            api_key=SecretStr(api_key),
            base_url=base_url,
            temperature=temperature,
            vertex_region=vertex_region,
            vertex_project_id=vertex_project_id,
            api_type=api_type
        )
        
        # Load existing settings or create new
        settings = await settings_store.load()
        if not settings:
            settings = Settings()
        
        # Set as default LLM config
        settings.llm_configs['default'] = llm_config
        
        # Save settings
        await settings_store.store(settings)

        print_formatted_text(HTML("\n<green>✓ Settings saved successfully!</green>"))

    except UserCancelledError:
        print_formatted_text(HTML("\n<yellow>Setup cancelled by user.</yellow>"))
    except Exception as e:
        print_formatted_text(HTML(f"\n<red>Error during setup: {e}</red>"))


async def setup_runtime_configuration(settings_store: FileSettingsStore) -> None:
    """Interactive setup for runtime configuration."""
    session = PromptSession()

    try:
        # Step 1: Select runtime mode
        print_formatted_text(HTML("\n<green>Setting up Runtime Configuration</green>"))
        print_formatted_text(HTML("<grey>Choose your preferred runtime mode:</grey>\n"))

        runtime_choices = [mode.value for mode in RuntimeMode]

        mode_choice = cli_confirm(
            "Select Runtime Mode:",
            runtime_choices,
        )
        runtime_mode = RuntimeMode(runtime_choices[mode_choice])

        # Step 2: E2B specific configuration
        template_id = None
        runtime_api_key = None

        if runtime_mode == RuntimeMode.E2B:
            print_formatted_text(
                HTML("\n<grey>E2B Configuration (required for E2B runtime):</grey>")
            )

            template_id = await get_validated_input(
                session,
                "Enter E2B template ID: ",
                error_message="Template ID cannot be empty",
            )

            runtime_api_key = await get_validated_input(
                session,
                "Enter E2B API key: ",
                error_message="API key cannot be empty",
                is_password=True,
            )

        # Confirm save
        if not save_settings_confirmation():
            return

        # Create runtime configuration
        runtime_config = RuntimeConfig(
            mode=runtime_mode,
            template_id=template_id,
            runtime_api_key=SecretStr(runtime_api_key) if runtime_api_key else None,
        )

        # Load existing settings or create new
        settings = await settings_store.load()
        if not settings:
            settings = Settings()

        # Set runtime config
        settings.runtime_config = runtime_config

        # Save settings
        await settings_store.store(settings)

        print_formatted_text(
            HTML("\n<green>✓ Runtime settings saved successfully!</green>")
        )
        print_formatted_text(
            HTML(
                "<yellow>Note: Runtime changes will take effect on the next startup, not the current session.</yellow>"
            )
        )

    except UserCancelledError:
        print_formatted_text(
            HTML("\n<yellow>Runtime setup cancelled by user.</yellow>")
        )
    except Exception as e:
        print_formatted_text(HTML(f"\n<red>Error during runtime setup: {e}</red>"))


async def run_first_time_setup(settings_store: FileSettingsStore) -> bool:
    """Run the first-time setup flow."""
    print_formatted_text(HTML('\n<blue>Welcome to ii-agent!</blue>'))
    print_formatted_text(HTML('<grey>No settings found. Let\'s set up your LLM configuration.</grey>\n'))
    
    try:
        # Step 1: Setup LLM configuration
        await setup_llm_configuration(settings_store)

        # Step 2: Setup runtime configuration
        await setup_runtime_configuration(settings_store)

        return True
    except Exception as e:
        print_formatted_text(HTML(f'\n<red>Setup failed: {e}</red>'))
        return False


async def modify_settings(settings_store: FileSettingsStore) -> None:
    """Modify existing settings."""
    settings = await settings_store.load()
    
    if settings:
        display_settings(settings)
        
        modify_choice = cli_confirm(
            "\nWhat would you like to modify?",
            ["LLM Configuration", "Runtime Configuration", "Go back"],
        )
        
        if modify_choice == 0:
            await setup_llm_configuration(settings_store)
        elif modify_choice == 1:
            await setup_runtime_configuration(settings_store)
    else:
        print_formatted_text(HTML('<grey>No settings found. Running first-time setup...</grey>'))
        await run_first_time_setup(settings_store)