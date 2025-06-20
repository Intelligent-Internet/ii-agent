from fastapi import Request

from ii_agent.core.storage.models.settings import Settings
from ii_agent.core.storage.settings.settings_store import SettingsStore
from ii_agent.server import shared
from ii_agent.server.shared import SettingsStoreImpl


async def get_settings_store(request: Request) -> SettingsStore:
    settings_store: SettingsStore | None = getattr(request.state, 'settings_store', None)
    if settings_store:
        return settings_store
    settings_store = await SettingsStoreImpl.get_instance(shared.config, user_id=None)
    request.state.settings_store = settings_store
    return settings_store

async def get_settings(request: Request) -> Settings:
    settings_store = await get_settings_store(request)
    return await settings_store.load()