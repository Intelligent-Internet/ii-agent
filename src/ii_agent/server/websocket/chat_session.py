import asyncio
import json
import logging
import uuid
from typing import Optional, Dict, Any, TYPE_CHECKING

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from ii_agent.agents.function_call import FunctionCallAgent
from ii_agent.controller.agent_controller import AgentController
from ii_agent.core.event import RealtimeEvent, EventType
from ii_agent.core.config.ii_agent_config import IIAgentConfig
from ii_agent.core.storage.files import FileStore
from ii_agent.server.models.messages import WebSocketMessage
from ii_agent.utils.workspace_manager import WorkspaceManager

if TYPE_CHECKING:
    from ii_agent.server.services.agent_service import AgentService
    from ii_agent.server.services.message_service import MessageService

logger = logging.getLogger(__name__)


class ChatSession:
    """Manages a single standalone chat session with its own agent, workspace, and message handling."""

    def __init__(
        self,
        websocket: WebSocket,
        workspace_manager: WorkspaceManager,
        session_uuid: uuid.UUID,
        agent_service: "AgentService",
        message_service: "MessageService",
        file_store: FileStore,
        config: IIAgentConfig,
    ):
        self.websocket = websocket
        self.workspace_manager = workspace_manager
        self.session_uuid = session_uuid
        self.agent_service = agent_service
        self.message_service = message_service
        self.file_store = file_store
        self.config = config
        
        # Session state
        self.agent_controller: Optional[AgentController] = None
        self.reviewer_controller: Optional[AgentController] = None
        self.active_task: Optional[asyncio.Task] = None
        self.first_message = True
        self.enable_reviewer = False

    async def send_event(self, event: RealtimeEvent):
        """Send an event to the client via WebSocket."""
        if self.websocket:
            try:
                await self.websocket.send_json(event.model_dump())
            except Exception as e:
                logger.error(f"Error sending event to client: {e}")

    async def start_chat_loop(self):
        """Start the chat loop for this session."""
        await self.handshake()
        try:
            while True:
                message_text = await self.websocket.receive_text()
                message_data = json.loads(message_text)
                await self.handle_message(message_data)
        except json.JSONDecodeError:
            await self.send_event(
                RealtimeEvent(
                    type=EventType.ERROR,
                    content={"message": "Invalid JSON format"},
                )
            )
        except WebSocketDisconnect:
            logger.info("Client disconnected")
            if self.agent_controller:
                self.agent_controller.cancel()

            # Wait for active task to complete before cleanup
            if self.active_task and not self.active_task.done():
                try:
                    await self.active_task
                except asyncio.CancelledError:
                    logger.info("Active task was cancelled")
                except Exception as e:
                    logger.error(f"Error waiting for active task completion: {e}")

            self.cleanup()

    async def handshake(self):
        """Handle handshake message."""
        await self.send_event(
            RealtimeEvent(
                type=EventType.CONNECTION_ESTABLISHED,
                content={
                    "message": "Connected to Agent WebSocket Server",
                    "workspace_path": str(self.workspace_manager.root),
                },
            )
        )

    async def handle_message(self, message_data: dict):
        """Handle incoming WebSocket messages for this session."""
        try:
            # Validate message structure
            ws_message = WebSocketMessage(**message_data)
            msg_type = ws_message.type
            content = ws_message.content

            # Delegate to message service
            await self.message_service.process_message(msg_type, content, self)

        except ValidationError as e:
            await self.send_event(
                RealtimeEvent(
                    type=EventType.ERROR,
                    content={"message": f"Invalid message format: {str(e)}"},
                )
            )
        except Exception as e:
            logger.error(f"Error handling message: {str(e)}")
            await self.send_event(
                RealtimeEvent(
                    type=EventType.ERROR,
                    content={"message": f"Error processing request: {str(e)}"},
                )
            )

    def has_active_task(self) -> bool:
        """Check if there's an active task for this session."""
        return self.active_task is not None and not self.active_task.done()

    def cleanup(self):
        """Clean up resources associated with this session."""
        # Set websocket to None but keep controllers running
        if self.agent_controller:
            if hasattr(self.agent_controller, 'state') and self.agent_controller.state:
                self.agent_controller.state.save_to_session(
                    str(self.session_uuid), self.file_store
                )

        # Cancel any running tasks
        if self.active_task and not self.active_task.done():
            self.active_task.cancel()
            self.active_task = None

        # Clean up references
        self.websocket = None
        self.agent_controller = None
        self.reviewer_controller = None

