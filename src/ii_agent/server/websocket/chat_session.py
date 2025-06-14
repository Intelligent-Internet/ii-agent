import asyncio
import json
import logging
from typing import Optional
from fastapi import WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from ii_agent.agents.base import BaseAgent
from ii_agent.core.event import RealtimeEvent, EventType
from ii_agent.core.storage.files import FileStore
from ii_agent.db.manager import Sessions, Events
from ii_agent.utils.prompt_generator import enhance_user_prompt
from ii_agent.utils.workspace_manager import WorkspaceManager
from ii_agent.server.models.messages import (
    WebSocketMessage,
    QueryContent,
    InitAgentContent,
    EnhancePromptContent,
    EditQueryContent,
)
from ii_agent.server.factories import ClientFactory, AgentFactory

logger = logging.getLogger(__name__)


class ChatSession:
    """Manages a single chat session with its own agent, workspace, and message handling."""

    def __init__(
        self,
        websocket: WebSocket,
        workspace_manager: WorkspaceManager,
        client_factory: ClientFactory,
        agent_factory: AgentFactory,
        file_store: FileStore,
    ):
        self.websocket = websocket
        self.workspace_manager = workspace_manager
        self.session_uuid = workspace_manager.session_id
        self.client_factory = client_factory
        self.agent_factory = agent_factory
        self.file_store = file_store
        # Session state
        self.agent: Optional[BaseAgent] = None
        self.active_task: Optional[asyncio.Task] = None
        self.message_processor: Optional[asyncio.Task] = None
        self.first_message = True

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

            # Route to appropriate handler
            handlers = {
                "init_agent": self._handle_init_agent,
                "query": self._handle_query,
                "workspace_info": self._handle_workspace_info,
                "ping": self._handle_ping,
                "cancel": self._handle_cancel,
                "edit_query": self._handle_edit_query,
                "enhance_prompt": self._handle_enhance_prompt,
            }

            handler = handlers.get(msg_type)
            if handler:
                await handler(content)
            else:
                await self.send_event(
                    RealtimeEvent(
                        type=EventType.ERROR,
                        content={"message": f"Unknown message type: {msg_type}"},
                    )
                )

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

    async def _handle_init_agent(self, content: dict):
        """Handle agent initialization."""
        try:
            init_content = InitAgentContent(**content)

            # Create LLM client using factory
            client = self.client_factory.create_client(
                init_content.model_name, thinking_tokens=init_content.thinking_tokens
            )

            # Create agent using factory
            self.agent = self.agent_factory.create_agent(
                client,
                self.workspace_manager,
                self.websocket,
                init_content.tool_args,
                self.file_store,
            )

            # Start message processor for this session
            self.message_processor = self.agent.start_message_processing()

            await self.send_event(
                RealtimeEvent(
                    type=EventType.AGENT_INITIALIZED,
                    content={"message": "Agent initialized"},
                )
            )
        except ValidationError as e:
            await self.send_event(
                RealtimeEvent(
                    type=EventType.ERROR,
                    content={"message": f"Invalid init_agent content: {str(e)}"},
                )
            )
        except Exception as e:
            await self.send_event(
                RealtimeEvent(
                    type=EventType.ERROR,
                    content={"message": f"Error initializing agent: {str(e)}"},
                )
            )

    async def _handle_query(self, content: dict):
        """Handle query processing."""
        try:
            query_content = QueryContent(**content)

            # Set session name from first message
            if self.first_message and query_content.text.strip():
                # Extract first few words as session name (max 100 characters)
                session_name = query_content.text.strip()[:100]
                Sessions.update_session_name(self.session_uuid, session_name)
                self.first_message = False

            # Check if there's an active task for this session
            if self.has_active_task():
                await self.send_event(
                    RealtimeEvent(
                        type=EventType.ERROR,
                        content={"message": "A query is already being processed"},
                    )
                )
                return

            # Send acknowledgment
            await self.send_event(
                RealtimeEvent(
                    type=EventType.PROCESSING,
                    content={"message": "Processing your request..."},
                )
            )

            # Run the agent with the query in a separate task
            self.active_task = asyncio.create_task(
                self._run_agent_async(
                    query_content.text, query_content.resume, query_content.files
                )
            )

        except ValidationError as e:
            await self.send_event(
                RealtimeEvent(
                    type=EventType.ERROR,
                    content={"message": f"Invalid query content: {str(e)}"},
                )
            )

    async def _handle_workspace_info(self, content: dict = None):
        """Handle workspace info request."""
        await self.send_event(
            RealtimeEvent(
                type=EventType.WORKSPACE_INFO,
                content={"path": str(self.workspace_manager.root)},
            )
        )

    async def _handle_ping(self, content: dict = None):
        """Handle ping message."""
        await self.send_event(RealtimeEvent(type=EventType.PONG, content={}))

    async def _handle_cancel(self, content: dict = None):
        """Handle query cancellation."""
        if not self.agent:
            await self.send_event(
                RealtimeEvent(
                    type=EventType.ERROR,
                    content={"message": "No active agent for this session"},
                )
            )
            return

        self.agent.cancel()

        # Send acknowledgment that cancellation was received
        await self.send_event(
            RealtimeEvent(
                type=EventType.SYSTEM,
                content={"message": "Query cancelled"},
            )
        )

    async def _handle_edit_query(self, content: dict):
        """Handle query editing."""
        try:
            edit_content = EditQueryContent(**content)

            if not self.agent:
                await self.send_event(
                    RealtimeEvent(
                        type=EventType.ERROR,
                        content={"message": "No active agent for this session"},
                    )
                )
                return

            # Cancel the agent and clear history
            self.agent.cancel()
            self.agent.history.clear_from_last_to_user_message()

            # Delete events from database up to last user message if we have a session ID
            if self.agent.session_id:
                try:
                    Events.delete_events_from_last_to_user_message(
                        self.agent.session_id
                    )
                    await self.send_event(
                        RealtimeEvent(
                            type=EventType.SYSTEM,
                            content={
                                "message": "Session history cleared from last event to last user message"
                            },
                        )
                    )
                except Exception as e:
                    logger.error(f"Error deleting session events: {str(e)}")
                    await self.send_event(
                        RealtimeEvent(
                            type=EventType.ERROR,
                            content={"message": f"Error clearing history: {str(e)}"},
                        )
                    )

            # Send acknowledgment that query editing was received
            await self.send_event(
                RealtimeEvent(
                    type=EventType.SYSTEM,
                    content={"message": "Query editing mode activated"},
                )
            )

            # Check if there's an active task for this session
            if self.has_active_task():
                await self.send_event(
                    RealtimeEvent(
                        type=EventType.ERROR,
                        content={"message": "A query is already being processed"},
                    )
                )
                return

            # Send processing acknowledgment
            await self.send_event(
                RealtimeEvent(
                    type=EventType.PROCESSING,
                    content={"message": "Processing your request..."},
                )
            )

            # Run the agent with the query in a separate task
            self.active_task = asyncio.create_task(
                self._run_agent_async(
                    edit_content.text, edit_content.resume, edit_content.files
                )
            )

        except ValidationError as e:
            await self.send_event(
                RealtimeEvent(
                    type=EventType.ERROR,
                    content={"message": f"Invalid edit_query content: {str(e)}"},
                )
            )

    async def _handle_enhance_prompt(self, content: dict):
        """Handle prompt enhancement request."""
        try:
            enhance_content = EnhancePromptContent(**content)

            # Create LLM client using factory
            client = self.client_factory.create_client(enhance_content.model_name)

            # Call the enhance_prompt function
            success, message, enhanced_prompt = await enhance_user_prompt(
                client=client,
                user_input=enhance_content.text,
                files=enhance_content.files,
            )

            if success and enhanced_prompt:
                # Send the enhanced prompt back to the client
                await self.send_event(
                    RealtimeEvent(
                        type=EventType.PROMPT_GENERATED,
                        content={
                            "result": enhanced_prompt,
                            "original_request": enhance_content.text,
                        },
                    )
                )
            else:
                # Send error message
                await self.send_event(
                    RealtimeEvent(
                        type=EventType.ERROR,
                        content={"message": message},
                    )
                )

        except ValidationError as e:
            await self.send_event(
                RealtimeEvent(
                    type=EventType.ERROR,
                    content={"message": f"Invalid enhance_prompt content: {str(e)}"},
                )
            )

    async def _run_agent_async(
        self, user_input: str, resume: bool = False, files: list = []
    ):
        """Run the agent asynchronously and send results back to the websocket."""
        if not self.agent:
            await self.send_event(
                RealtimeEvent(
                    type=EventType.ERROR,
                    content={"message": "Agent not initialized for this session"},
                )
            )
            return

        try:
            # Add user message to the event queue to save to database
            self.agent.message_queue.put_nowait(
                RealtimeEvent(type=EventType.USER_MESSAGE, content={"text": user_input})
            )
            # Run the agent with the query using the new async method
            await self.agent.run_agent_async(user_input, files, resume)

        except Exception as e:
            logger.error(f"Error running agent: {str(e)}")
            import traceback

            traceback.print_exc()
            await self.send_event(
                RealtimeEvent(
                    type=EventType.ERROR,
                    content={"message": f"Error running agent: {str(e)}"},
                )
            )
        finally:
            # Clean up the task reference
            self.active_task = None

    def has_active_task(self) -> bool:
        """Check if there's an active task for this session."""
        return self.active_task is not None and not self.active_task.done()

    def cleanup(self):
        """Clean up resources associated with this session."""
        # Set websocket to None in the agent but keep the message processor running
        if self.agent:
            self.agent.websocket = (
                None  # This will prevent sending to websocket but keep processing
            )
            if self.agent.history:
                self.agent.history.save_to_session(
                    str(self.session_uuid), self.file_store
                )

        # Cancel any running tasks
        if self.active_task and not self.active_task.done():
            self.active_task.cancel()
            self.active_task = None

        # Clean up references
        self.websocket = None
        self.agent = None
        self.message_processor = None
