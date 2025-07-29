"""
Settings onboarding module for ii-agent CLI.

This module provides interactive configuration setup for first-time users
and runtime settings management, with a focus on simplicity and user experience.

ONBOARDING FLOW:
1. LLM Configuration (required)
   - Provider selection (Anthropic, OpenAI, Gemini)
   - Model selection
   - API key setup (with Vertex AI support)
   
2. Basic Tool Configuration (simple, optional)
   - Web Search: Choose provider (Firecrawl, SerpAPI, Jina, Tavily)
   - Web Visit: Choose provider (Firecrawl, Jina, Tavily)  
   - Image Search: Optional SerpAPI setup
   
3. Advanced Google Cloud Tools (optional, separate flow)
   - Video Generation: Google AI Studio OR GCP Vertex AI
   - Image Generation: Google AI Studio OR GCP Vertex AI
   - Shared setup option when configuring both
   - Can be configured later via settings modification

This separation keeps the main onboarding simple while allowing power users
to configure complex tools when needed.
"""

import os

from prompt_toolkit import PromptSession, print_formatted_text
from prompt_toolkit.completion import FuzzyWordCompleter
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.shortcuts import print_container
from prompt_toolkit.widgets import Frame, TextArea
from pydantic import SecretStr

from ii_agent.core.config.llm_config import LLMConfig, APITypes
from ii_agent.core.storage.models.settings import Settings
from ii_agent.core.storage.settings.file_settings_store import FileSettingsStore
from ii_agent.utils.constants import DEFAULT_MODEL
from ii_tool.core.config import (
    WebSearchConfig, 
    WebVisitConfig, 
    ImageSearchConfig, 
    VideoGenerateConfig, 
    ImageGenerateConfig, 
    FullStackDevConfig
)


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
    "gemini-2.5-flash"
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
        labels_and_values.extend([
            ('   Vertex Region', default_llm.vertex_region or 'Not Set'),
            ('   Vertex Project ID', default_llm.vertex_project_id or 'Not Set'),
        ])
    
    # Add tool configurations status
    labels_and_values.extend([
        ('', ''),  # Empty line for separation
        ('Basic Tools:', ''),
        ('   Web Search', 'Configured' if has_tool_config_keys(settings.web_search_config) else 'Not Configured'),
        ('   Web Visit', 'Configured' if has_tool_config_keys(settings.web_visit_config) else 'Not Configured'),
        ('   Image Search', 'Configured' if settings.image_search_config and has_tool_config_keys(settings.image_search_config) else 'Not Configured'),
        ('', ''),  # Empty line for separation
        ('Advanced Google Cloud Tools:', ''),
        ('   Video Generation', 'Configured' if settings.video_generate_config and has_tool_config_keys(settings.video_generate_config) else 'Not Configured'),
        ('   Image Generation', 'Configured' if settings.image_generate_config and has_tool_config_keys(settings.image_generate_config) else 'Not Configured'),
    ])
    
    # Calculate max width for alignment
    max_label_width = max(len(label) for label, _ in labels_and_values)
    
    # Construct the summary text
    settings_lines = [
        f'{label + ":":<{max_label_width + 1}} {value}' if label and value else label + value
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


def has_tool_config_keys(config) -> bool:
    """Check if a tool config has any API keys configured."""
    if not config:
        return False
    
    # Check for common API key attributes
    api_key_attrs = [
        'firecrawl_api_key', 'serpapi_api_key', 'jina_api_key', 'tavily_api_key',
        'google_ai_studio_api_key', 'gcp_project_id', 'gcp_location', 'gcs_output_bucket'
    ]
    
    for attr in api_key_attrs:
        if hasattr(config, attr) and getattr(config, attr):
            return True
    
    return False


async def get_validated_input(
    session: PromptSession,
    prompt_text: str,
    completer=None,
    validator=None,
    error_message: str = 'Input cannot be empty',
    is_password: bool = False,
    allow_empty: bool = False,
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
            elif not value and not allow_empty:
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


async def setup_web_search_configuration(settings_store: FileSettingsStore) -> WebSearchConfig:
    """Interactive setup for web search configuration."""
    session = PromptSession()
    
    print_formatted_text(HTML('\n<green>Setting up Web Search Configuration</green>'))
    print_formatted_text(HTML('<grey>Choose your preferred web search provider:</grey>\n'))
    
    # Available search providers
    search_providers = [
        'Firecrawl',
        'SerpAPI', 
        'Jina',
        'Tavily',
    ]
    
    provider_choice = cli_confirm(
        'Select Web Search Provider:',
        search_providers
    )
    
    # Get API key for selected provider
    provider_name = search_providers[provider_choice]
    api_key = await get_validated_input(
        session,
        f'Enter {provider_name} API Key: ',
        error_message='API Key cannot be empty',
        is_password=True
    )
    
    # Create config with only the selected provider's key
    config_kwargs = {}
    if provider_choice == 0:  # Firecrawl
        config_kwargs['firecrawl_api_key'] = api_key
    elif provider_choice == 1:  # SerpAPI
        config_kwargs['serpapi_api_key'] = api_key
    elif provider_choice == 2:  # Jina
        config_kwargs['jina_api_key'] = api_key
    elif provider_choice == 3:  # Tavily
        config_kwargs['tavily_api_key'] = api_key
    
    return WebSearchConfig(**config_kwargs)


async def setup_web_visit_configuration(settings_store: FileSettingsStore) -> WebVisitConfig:
    """Interactive setup for web visit configuration."""
    session = PromptSession()
    
    print_formatted_text(HTML('\n<green>Setting up Web Visit Configuration</green>'))
    print_formatted_text(HTML('<grey>Choose your preferred web visit provider:</grey>\n'))
    
    # Available web visit providers
    web_visit_providers = [
        'Firecrawl',
        'Jina',
        'Tavily',
    ]
    
    provider_choice = cli_confirm(
        'Select Web Visit Provider:',
        web_visit_providers
    )
    
    # Get API key for selected provider
    provider_name = web_visit_providers[provider_choice]
    api_key = await get_validated_input(
        session,
        f'Enter {provider_name} API Key: ',
        error_message='API Key cannot be empty',
        is_password=True
    )
    
    # Create config with only the selected provider's key
    config_kwargs = {}
    if provider_choice == 0:  # Firecrawl
        config_kwargs['firecrawl_api_key'] = api_key
    elif provider_choice == 1:  # Jina
        config_kwargs['jina_api_key'] = api_key
    elif provider_choice == 2:  # Tavily
        config_kwargs['tavily_api_key'] = api_key
    
    return WebVisitConfig(**config_kwargs)


async def setup_image_search_configuration(settings_store: FileSettingsStore) -> ImageSearchConfig | None: 
    """Interactive setup for image search configuration."""
    session = PromptSession()
    
    print_formatted_text(HTML('\n<green>Setting up Image Search Configuration</green>'))
    print_formatted_text(HTML('<grey>Configure image search provider:</grey>\n'))
    
    # Check if user wants to configure image search
    if cli_confirm('Do you want to configure image search?', ['Yes, configure SerpAPI', 'Skip image search configuration']) == 1:
        return None
    
    # Get SerpAPI key
    serpapi_api_key = await get_validated_input(
        session,
        'Enter SerpAPI Key: ',
        error_message='API Key cannot be empty',
        is_password=True
    )
    
    return ImageSearchConfig(
        serpapi_api_key=serpapi_api_key,
    )


async def setup_video_generate_configuration(settings_store: FileSettingsStore) -> VideoGenerateConfig | None:
    """Interactive setup for video generation configuration."""
    session = PromptSession()
    
    print_formatted_text(HTML('\n<green>Setting up Video Generation Configuration</green>'))
    print_formatted_text(HTML('<grey>Video generation requires either Google AI Studio or Google Cloud Platform setup.</grey>\n'))
    
    # Check if user wants to configure video generation
    if cli_confirm('Do you want to configure video generation?', ['Yes, configure video generation', 'Skip video generation configuration']) == 1:
        return None
    
    # Choose between Google AI Studio or GCP
    provider_choice = cli_confirm(
        'Choose video generation provider:',
        ['Google AI Studio (API Key)', 'Google Cloud Platform (Vertex AI)', 'Skip video generation']
    )
    
    if provider_choice == 2:  # Skip
        return None
    
    if provider_choice == 0:  # Google AI Studio
        print_formatted_text(HTML('<grey>Using Google AI Studio for video generation:</grey>\n'))
        
        google_ai_studio_api_key = await get_validated_input(
            session,
            'Enter Google AI Studio API Key: ',
            error_message='Google AI Studio API Key cannot be empty',
            is_password=True
        )
        
        return VideoGenerateConfig(
            google_ai_studio_api_key=google_ai_studio_api_key,
        )
    
    else:  # GCP Vertex AI
        print_formatted_text(HTML('<grey>Using Google Cloud Platform for video generation:</grey>'))
        print_formatted_text(HTML('<grey>This requires GCP Project ID, Location, and GCS Output Bucket.</grey>\n'))
        
        gcp_project_id = await get_validated_input(
            session,
            'Enter GCP Project ID: ',
            error_message='GCP Project ID cannot be empty'
        )
        
        gcp_location = await get_validated_input(
            session,
            'Enter GCP Location (e.g., us-central1): ',
            error_message='GCP Location cannot be empty'
        )
        
        gcs_output_bucket = await get_validated_input(
            session,
            'Enter GCS Output Bucket (e.g., gs://my-bucket-name): ',
            error_message='GCS Output Bucket cannot be empty'
        )
        
        # Validate GCS bucket format
        if not gcs_output_bucket.startswith('gs://'):
            print_formatted_text(HTML('<yellow>Warning: GCS bucket should start with gs://. Adding prefix...</yellow>'))
            gcs_output_bucket = f'gs://{gcs_output_bucket}'
        
        return VideoGenerateConfig(
            gcp_project_id=gcp_project_id,
            gcp_location=gcp_location,
            gcs_output_bucket=gcs_output_bucket,
        )


async def setup_image_generate_configuration(settings_store: FileSettingsStore) -> ImageGenerateConfig | None:
    """Interactive setup for image generation configuration."""
    session = PromptSession()
    
    print_formatted_text(HTML('\n<green>Setting up Image Generation Configuration</green>'))
    print_formatted_text(HTML('<grey>Image generation requires either Google AI Studio or Google Cloud Platform setup.</grey>\n'))
    
    # Check if user wants to configure image generation
    if cli_confirm('Do you want to configure image generation?', ['Yes, configure image generation', 'Skip image generation configuration']) == 1:
        return None
    
    # Choose between Google AI Studio or GCP
    provider_choice = cli_confirm(
        'Choose image generation provider:',
        ['Google AI Studio (API Key)', 'Google Cloud Platform (Vertex AI)', 'Skip image generation']
    )
    
    if provider_choice == 2:  # Skip
        return None
    
    if provider_choice == 0:  # Google AI Studio
        print_formatted_text(HTML('<grey>Using Google AI Studio for image generation:</grey>\n'))
        
        google_ai_studio_api_key = await get_validated_input(
            session,
            'Enter Google AI Studio API Key: ',
            error_message='Google AI Studio API Key cannot be empty',
            is_password=True
        )
        
        return ImageGenerateConfig(
            google_ai_studio_api_key=google_ai_studio_api_key,
        )
    
    else:  # GCP Vertex AI
        print_formatted_text(HTML('<grey>Using Google Cloud Platform for image generation:</grey>'))
        print_formatted_text(HTML('<grey>This requires GCP Project ID and Location.</grey>\n'))
        
        gcp_project_id = await get_validated_input(
            session,
            'Enter GCP Project ID: ',
            error_message='GCP Project ID cannot be empty'
        )
        
        gcp_location = await get_validated_input(
            session,
            'Enter GCP Location (e.g., us-central1): ',
            error_message='GCP Location cannot be empty'
        )
        
        return ImageGenerateConfig(
            gcp_project_id=gcp_project_id,
            gcp_location=gcp_location,
        )


async def setup_tools_configuration(settings_store: FileSettingsStore) -> tuple[WebSearchConfig, WebVisitConfig, FullStackDevConfig, ImageSearchConfig, VideoGenerateConfig, ImageGenerateConfig]:
    """Interactive setup for all tool configurations."""
    print_formatted_text(HTML('\n<blue>Tool Configuration Setup</blue>'))
    print_formatted_text(HTML('<grey>Configure API keys for basic tools. You can skip any tools you don\'t plan to use.</grey>\n'))
    
    # Configure simple tools only
    web_search_config = await setup_web_search_configuration(settings_store)
    web_visit_config = await setup_web_visit_configuration(settings_store)
    image_search_config = await setup_image_search_configuration(settings_store)
    fullstack_dev_config = FullStackDevConfig()  # No configuration needed for this one
    
    # Set complex tools to None for now
    video_generate_config = None
    image_generate_config = None
    
    # Ask if user wants to configure advanced Google Cloud tools
    if cli_confirm('\nDo you want to configure advanced Google Cloud tools (video/image generation)?', ['No, keep it simple', 'Yes, configure advanced tools']) == 1:
        video_generate_config, image_generate_config = await setup_advanced_google_tools(settings_store)
    
    return (
        web_search_config,
        web_visit_config,
        fullstack_dev_config,
        image_search_config,
        video_generate_config,
        image_generate_config,
    )


async def setup_advanced_google_tools(settings_store: FileSettingsStore) -> tuple[VideoGenerateConfig | None, ImageGenerateConfig | None]:
    """Setup advanced Google Cloud tools (video and image generation)."""
    print_formatted_text(HTML('\n<blue>Advanced Google Cloud Tools Setup</blue>'))
    print_formatted_text(HTML('<grey>These tools require Google Cloud Platform or Google AI Studio setup.</grey>\n'))
    
    # Ask what the user wants to configure
    tools_choice = cli_confirm(
        'Which Google Cloud tools do you want to configure?',
        ['Video generation only', 'Image generation only', 'Both video and image generation', 'Skip advanced tools']
    )
    
    if tools_choice == 3:  # Skip
        return None, None
    
    video_config = None
    image_config = None
    
    # Determine if we need shared Google Cloud setup
    need_video = tools_choice in [0, 2]  # Video only or both
    need_image = tools_choice in [1, 2]  # Image only or both
    
    if need_video and need_image:
        # Both tools - offer shared setup
        shared_setup = cli_confirm(
            'You selected both video and image generation. Do you want to use the same Google Cloud settings for both?',
            ['Yes, use shared settings', 'No, configure separately']
        ) == 0
        
        if shared_setup:
            print_formatted_text(HTML('\n<green>Shared Google Cloud Setup</green>'))
            print_formatted_text(HTML('<grey>These settings will be used for both video and image generation.</grey>\n'))
            
            provider_choice = cli_confirm(
                'Choose your Google Cloud provider:',
                ['Google AI Studio (API Key)', 'Google Cloud Platform (Vertex AI)']
            )
            
            if provider_choice == 0:  # Google AI Studio
                google_ai_studio_api_key = await get_validated_input(
                    PromptSession(),
                    'Enter Google AI Studio API Key: ',
                    error_message='Google AI Studio API Key cannot be empty',
                    is_password=True
                )
                
                video_config = VideoGenerateConfig(google_ai_studio_api_key=google_ai_studio_api_key)
                image_config = ImageGenerateConfig(google_ai_studio_api_key=google_ai_studio_api_key)
                
            else:  # GCP Vertex AI
                print_formatted_text(HTML('<grey>Note: Video generation also requires a GCS bucket for temporary storage.</grey>\n'))
                
                session = PromptSession()
                gcp_project_id = await get_validated_input(
                    session,
                    'Enter GCP Project ID: ',
                    error_message='GCP Project ID cannot be empty'
                )
                
                gcp_location = await get_validated_input(
                    session,
                    'Enter GCP Location (e.g., us-central1): ',
                    error_message='GCP Location cannot be empty'
                )
                
                gcs_output_bucket = await get_validated_input(
                    session,
                    'Enter GCS Output Bucket for video generation (e.g., gs://my-bucket): ',
                    error_message='GCS Output Bucket cannot be empty'
                )
                
                if not gcs_output_bucket.startswith('gs://'):
                    gcs_output_bucket = f'gs://{gcs_output_bucket}'
                
                video_config = VideoGenerateConfig(
                    gcp_project_id=gcp_project_id,
                    gcp_location=gcp_location,
                    gcs_output_bucket=gcs_output_bucket,
                )
                image_config = ImageGenerateConfig(
                    gcp_project_id=gcp_project_id,
                    gcp_location=gcp_location,
                )
        else:
            # Configure separately
            if need_video:
                video_config = await setup_video_generate_configuration(settings_store)
            if need_image:
                image_config = await setup_image_generate_configuration(settings_store)
    
    elif need_video:
        video_config = await setup_video_generate_configuration(settings_store)
    elif need_image:
        image_config = await setup_image_generate_configuration(settings_store)
    
    return video_config, image_config


async def setup_llm_configuration(settings_store: FileSettingsStore) -> LLMConfig | None:
    """Interactive setup for LLM configuration. Returns the config without saving."""
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
        
        # Create and return configuration (don't save yet)
        llm_config = LLMConfig(
            model=model,
            api_key=SecretStr(api_key),
            base_url=base_url,
            temperature=temperature,
            vertex_region=vertex_region,
            vertex_project_id=vertex_project_id,
            api_type=api_type
        )
        
        print_formatted_text(HTML('\n<green>✓ LLM configuration ready!</green>'))
        return llm_config
        
    except UserCancelledError:
        print_formatted_text(HTML('\n<yellow>LLM setup cancelled by user.</yellow>'))
        return None
    except Exception as e:
        print_formatted_text(HTML(f'\n<red>Error during LLM setup: {e}</red>'))
        return None


async def run_first_time_setup(settings_store: FileSettingsStore) -> bool:
    """Run the first-time setup flow."""
    print_formatted_text(HTML('\n<blue>Welcome to ii-agent!</blue>'))
    print_formatted_text(HTML('<grey>No settings found. Let\'s set up your configuration.</grey>\n'))
    
    try:
        # First setup LLM configuration
        llm_config = await setup_llm_configuration(settings_store)
        if llm_config:
            # Then setup tool configurations
            (web_search_config, web_visit_config, fullstack_dev_config, 
             image_search_config, video_generate_config, image_generate_config) = await setup_tools_configuration(settings_store)

            # Confirm save for all configurations
            if save_settings_confirmation():
                # Create new settings with all configurations
                settings = Settings(
                    web_search_config=web_search_config,
                    web_visit_config=web_visit_config,
                    fullstack_dev_config=fullstack_dev_config,
                    image_search_config=image_search_config,
                    video_generate_config=video_generate_config,
                    image_generate_config=image_generate_config,
                )
                
                # Set the LLM config
                settings.llm_configs['default'] = llm_config
                
                # Save all settings at once
                await settings_store.store(settings)
                print_formatted_text(HTML('\n<green>✓ Complete setup saved successfully!</green>'))
                return True
            else:
                print_formatted_text(HTML('\n<yellow>Setup cancelled - settings not saved.</yellow>'))
                return False
        else:
            return False
    except Exception as e:
        print_formatted_text(HTML(f'\n<red>Setup failed: {e}</red>'))
        return False


async def modify_settings(settings_store: FileSettingsStore) -> None:
    """Modify existing settings."""
    settings = await settings_store.load()
    
    if settings:
        display_settings(settings)
        
        modify_choice = cli_confirm(
            '\nWhat would you like to modify?',
            ['LLM Configuration', 'Basic Tool Configurations', 'Advanced Google Cloud Tools', 'Go back']
        )
        
        if modify_choice == 0:
            llm_config = await setup_llm_configuration(settings_store)
            if llm_config:
                # Just update the LLM config, keep existing tool configs
                settings.llm_configs['default'] = llm_config
                
                if save_settings_confirmation():
                    await settings_store.store(settings)
                    print_formatted_text(HTML('\n<green>✓ LLM configuration updated successfully!</green>'))
        elif modify_choice == 1:
            # Basic tools only
            web_search_config = await setup_web_search_configuration(settings_store)
            web_visit_config = await setup_web_visit_configuration(settings_store)
            image_search_config = await setup_image_search_configuration(settings_store)
            fullstack_dev_config = FullStackDevConfig()
            
            # Keep existing advanced tool configs
            video_generate_config = settings.video_generate_config
            image_generate_config = settings.image_generate_config
            
            # Update settings with new basic tool configurations
            settings.web_search_config = web_search_config
            settings.web_visit_config = web_visit_config
            settings.image_search_config = image_search_config
            settings.fullstack_dev_config = fullstack_dev_config
            
            if save_settings_confirmation():
                await settings_store.store(settings)
                print_formatted_text(HTML('\n<green>✓ Basic tool configurations updated successfully!</green>'))
                
        elif modify_choice == 2:
            # Advanced Google Cloud tools
            video_generate_config, image_generate_config = await setup_advanced_google_tools(settings_store)
            
            # Update settings with new advanced tool configurations
            settings.video_generate_config = video_generate_config
            settings.image_generate_config = image_generate_config
            
            if save_settings_confirmation():
                await settings_store.store(settings)
                print_formatted_text(HTML('\n<green>✓ Advanced tool configurations updated successfully!</green>'))
    else:
        print_formatted_text(HTML('<grey>No settings found. Running first-time setup...</grey>'))
        await run_first_time_setup(settings_store)