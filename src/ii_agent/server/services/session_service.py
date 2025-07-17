"""Session service for managing chat sessions."""

import uuid
from pathlib import Path
from typing import Optional

from fastapi import WebSocket

from ii_agent.core.config.ii_agent_config import IIAgentConfig
from ii_agent.core.storage.files import FileStore
from ii_agent.server.services.agent_service import AgentService
from ii_agent.server.services.message_service import MessageService
from ii_agent.server.websocket.chat_session import ChatSession
from ii_agent.utils.workspace_manager import WorkspaceManager


class SessionService:
    """Service for creating and managing chat sessions."""

    def __init__(
        self,
        agent_service: AgentService,
        message_service: MessageService,
        file_store: FileStore,
        config: IIAgentConfig,
    ):
        self.agent_service = agent_service
        self.message_service = message_service
        self.file_store = file_store
        self.config = config

    def create_session(
        self,
        websocket: WebSocket,
        session_uuid: Optional[uuid.UUID] = None,
    ) -> ChatSession:
        """Create a new chat session.
        
        Args:
            websocket: WebSocket connection
            session_uuid: Optional session UUID, will generate if not provided
            
        Returns:
            ChatSession instance
        """
        # Generate session UUID if not provided
        if session_uuid is None:
            session_uuid = uuid.uuid4()
        
        # Create workspace for this session
        workspace_path = Path(self.config.workspace_root).resolve()
        connection_workspace = workspace_path / str(session_uuid)
        connection_workspace.mkdir(parents=True, exist_ok=True)
        
        workspace_manager = WorkspaceManager(
            root=connection_workspace,
            container_workspace=self.config.use_container_workspace,
        )
        
        # Create chat session
        session = ChatSession(
            websocket=websocket,
            workspace_manager=workspace_manager,
            session_uuid=session_uuid,
            agent_service=self.agent_service,
            message_service=self.message_service,
            file_store=self.file_store,
            config=self.config,
        )
        
        return session