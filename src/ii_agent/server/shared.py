from ii_agent.core.config.ii_agent_config import config
from dotenv import load_dotenv

from ii_agent.core.storage import get_file_store
from ii_agent.core.storage.settings.file_settings_store import FileSettingsStore
from ii_agent.server.services.agent_service import AgentService
from ii_agent.server.services.message_service import MessageService
from ii_agent.server.services.session_service import SessionService
from ii_agent.server.websocket.manager import ConnectionManager


load_dotenv()


file_store = get_file_store(config.file_store, config.file_store_path)

# Create service layer
agent_service = AgentService(
    config=config,
    file_store=file_store,
)

message_service = MessageService(
    agent_service=agent_service,
    config=config,
)

session_service = SessionService(
    agent_service=agent_service,
    message_service=message_service,
    file_store=file_store,
    config=config,
)

connection_manager = ConnectionManager(
    session_service=session_service,
    config=config,
)

SettingsStoreImpl = FileSettingsStore
