from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from ii_agent.core.storage.models.settings import Settings
from ii_agent.core.storage.settings.settings_store import SettingsStore
from ii_agent.server.models.messages import GETSettingsModel
from ii_agent.server.settings import get_settings, get_settings_store


settings_router = APIRouter(prefix="/api", tags=["settings"])


@settings_router.get("/settings", response_model=GETSettingsModel)
async def load_settings(settings: Settings = Depends(get_settings)):
    if not settings:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": "Settings not found"},
        )

    # Check if any LLM config has an API key set
    llm_api_key_set = (
        any(config.api_key is not None for config in settings.llm_configs.values())
        if settings.llm_configs
        else False
    )

    # Check if search config has an API key set
    search_api_key_set = (
        settings.search_config is not None
        and hasattr(settings.search_config, "api_key")
        and settings.search_config.api_key is not None
    )

    settings_with_api_keys = GETSettingsModel(
        llm_api_key_set=llm_api_key_set,
        search_api_key_set=search_api_key_set,
        **settings.model_dump(exclude={"secrets_store"}),
    )

    # Set API keys to None
    for model_name in settings_with_api_keys.llm_configs.keys():
        settings_with_api_keys.llm_configs[model_name].api_key = None
    settings_with_api_keys.audio_config.openai_api_key = None
    settings_with_api_keys.search_config.firecrawl_api_key = None
    settings_with_api_keys.search_config.serpapi_api_key = None
    settings_with_api_keys.search_config.tavily_api_key = None
    settings_with_api_keys.search_config.jina_api_key = None
    settings_with_api_keys.media_config.google_ai_studio_api_key = None
    settings_with_api_keys.sandbox_config.sandbox_api_key = None
    settings_with_api_keys.sandbox_config.template_id = None
    settings_with_api_keys.third_party_integration_config.vercel_api_key = None
    settings_with_api_keys.third_party_integration_config.openai_api_key = None
    settings_with_api_keys.third_party_integration_config.neon_db_api_key = None

    return settings_with_api_keys


async def store_llm_settings(
    settings: Settings, settings_store: SettingsStore
) -> Settings:
    existing_settings = await settings_store.load()
    if existing_settings:
        settings.update(existing_settings)

    return settings


@settings_router.post("/settings", response_model=None)
async def store_settings(
    settings: Settings, settings_store: SettingsStore = Depends(get_settings_store)
):
    try:
        existing_settings = await settings_store.load()
        if existing_settings:
            # Keep existing LLM settings if not provided
            settings = await store_llm_settings(settings, settings_store)

        await settings_store.store(settings)

        return JSONResponse(
            content={"message": "Settings stored"}, status_code=status.HTTP_200_OK
        )
    except Exception as e:
        return JSONResponse(
            content={"message": f"Error storing settings: {e}"},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
