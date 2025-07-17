import logging
import uuid
from typing import Dict, Optional

from fastapi import WebSocket

from ii_agent.core.config.ii_agent_config import IIAgentConfig
from ii_agent.server.services.session_service import SessionService
from ii_agent.server.websocket.chat_session import ChatSession

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections and their associated chat sessions."""

    def __init__(
        self,
        session_service: SessionService,
        config: IIAgentConfig,
    ):
        # Active chat sessions mapped by WebSocket
        self.sessions: Dict[WebSocket, ChatSession] = {}
        self.session_service = session_service
        self.config = config

    async def connect(self, websocket: WebSocket) -> ChatSession:
        """Accept a new WebSocket connection and create a chat session."""
        await websocket.accept()

        # Get session UUID from query params or generate new one
        session_uuid = websocket.query_params.get("session_uuid")
        if session_uuid is not None:
            session_uuid = uuid.UUID(session_uuid)

        # Create a new chat session using the session service
        session = self.session_service.create_session(
            websocket=websocket,
            session_uuid=session_uuid,
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
