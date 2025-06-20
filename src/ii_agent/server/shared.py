from ii_agent.core.config.ii_agent_config import IIAgentConfig
from ii_agent.core.config.utils import load_ii_agent_config
from dotenv import load_dotenv

from ii_agent.core.storage import get_file_store
from ii_agent.core.storage.settings.file_settings_store import FileSettingsStore
from ii_agent.server.websocket.manager import ConnectionManager


load_dotenv()


config: IIAgentConfig = load_ii_agent_config()

file_store = get_file_store(config.file_store, config.file_store_path)

connection_manager = ConnectionManager(
    file_store=file_store,
    config=config,
)

SettingsStoreImpl = FileSettingsStore
