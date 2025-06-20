import logging
from pathlib import Path
import uuid
from typing import Dict, Optional

from fastapi import WebSocket

from ii_agent.core.config.ii_agent_config import IIAgentConfig
from ii_agent.core.storage.files import FileStore
from ii_agent.server.websocket.chat_session import ChatSession
from ii_agent.utils.workspace_manager import WorkspaceManager

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections and their associated chat sessions."""

    def __init__(
        self,
        file_store: FileStore,
        config: IIAgentConfig,
    ):
        # Active chat sessions mapped by WebSocket
        self.sessions: Dict[WebSocket, ChatSession] = {}
        self.file_store = file_store
        self.config = config

    async def connect(self, websocket: WebSocket) -> ChatSession:
        """Accept a new WebSocket connection and create a chat session."""
        await websocket.accept()

        # Create workspace for this session if not provided
        session_uuid = websocket.query_params.get("session_uuid")
        if session_uuid is None:
            session_uuid = uuid.uuid4()
        else:
            session_uuid = uuid.UUID(session_uuid)

        workspace_path = Path(self.config.workspace_root).resolve()
        connection_workspace = workspace_path / str(session_uuid)
        connection_workspace.mkdir(parents=True, exist_ok=True)
        workspace_manager = WorkspaceManager(
            root=connection_workspace,
            container_workspace=self.config.use_container_workspace,
        )

        # Create a new chat session for this connection
        session = ChatSession(
            websocket,
            workspace_manager,
            session_uuid,
            self.file_store,
            config=self.config,
        )
        self.sessions[websocket] = session

        logger.info(
            f"New WebSocket connection and chat session established: {id(websocket)}"
        )
        return session

    def disconnect(self, websocket: WebSocket):
        """Handle WebSocket disconnection and cleanup."""
        logger.info(f"WebSocket disconnecting: {id(websocket)}")

        if websocket in self.sessions:
            session = self.sessions[websocket]
            session.cleanup()
            del self.sessions[websocket]

    def get_session(self, websocket: WebSocket) -> Optional[ChatSession]:
        """Get the chat session for a WebSocket connection."""
        return self.sessions.get(websocket)

    def get_connection_count(self) -> int:
        """Get the number of active connections."""
        return len(self.sessions)
