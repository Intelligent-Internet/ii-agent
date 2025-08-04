"""Enhanced WebSocket endpoint with authentication and advanced features."""

import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends

from ii_agent.core.config.ii_agent_config import IIAgentConfig
from ii_agent.server.services.session_service import SessionService
from ii_agent.server.websocket.enhanced_manager import EnhancedConnectionManager
from ii_agent.server.websocket.message_types import (
    MessageType,
    parse_message,
    ChatMessage,
    PingMessage,
    PongMessage,
    TypingIndicator,
    PresenceUpdate,
    ErrorMessage,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Global connection manager instance
connection_manager: EnhancedConnectionManager = None


def get_connection_manager(
    session_service: SessionService = Depends(SessionService),
    config: IIAgentConfig = Depends(IIAgentConfig),
) -> EnhancedConnectionManager:
    """Get or create the global connection manager."""
    global connection_manager
    if connection_manager is None:
        connection_manager = EnhancedConnectionManager(session_service, config)
    return connection_manager


@router.websocket("/ws/v2")
async def websocket_endpoint_v2(
    websocket: WebSocket,
    manager: EnhancedConnectionManager = Depends(get_connection_manager),
):
    """Enhanced WebSocket endpoint with authentication and advanced features."""

    session = None
    try:
        # Connect and authenticate
        session = await manager.connect(websocket, require_auth=True)
        if not session:
            return  # Connection was rejected

        logger.info(
            f"WebSocket v2 connection established for session: {session.session_uuid}"
        )

        # Start message handling loop
        while True:
            try:
                # Receive message
                data = await websocket.receive_text()
                message_data = json.loads(data)

                # Parse message
                message = parse_message(message_data)

                # Handle different message types
                await handle_message(websocket, session, message, manager)

            except WebSocketDisconnect:
                logger.info("WebSocket disconnected normally")
                break

            except json.JSONDecodeError:
                # Send error for invalid JSON
                error_msg = ErrorMessage(
                    error_code="INVALID_JSON",
                    error_message="Invalid JSON format",
                    session_id=str(session.session_uuid),
                )
                await manager.send_message(websocket, error_msg.model_dump())

            except Exception as e:
                logger.error(f"Error handling WebSocket message: {e}")
                error_msg = ErrorMessage(
                    error_code="MESSAGE_ERROR",
                    error_message=str(e),
                    session_id=str(session.session_uuid),
                )
                await manager.send_message(websocket, error_msg.model_dump())

    except Exception as e:
        logger.error(f"WebSocket connection error: {e}")

    finally:
        # Clean up connection
        if session:
            await manager.disconnect(websocket)


async def handle_message(
    websocket: WebSocket, session, message, manager: EnhancedConnectionManager
):
    """Handle different types of WebSocket messages."""

    session_id = str(session.session_uuid)
    metadata = manager.connection_metadata.get(websocket, {})
    user_id = metadata.get("user_id")

    if isinstance(message, ChatMessage):
        # Handle chat message
        await handle_chat_message(websocket, session, message, manager)

    elif isinstance(message, PingMessage):
        # Handle ping/pong for heartbeat
        pong_msg = PongMessage(session_id=session_id, user_id=user_id)
        await manager.send_message(websocket, pong_msg.model_dump())

    elif isinstance(message, TypingIndicator):
        # Handle typing indicator
        if user_id:
            await manager.send_typing_indicator(session_id, user_id, message.is_typing)

    elif isinstance(message, PresenceUpdate):
        # Handle presence update
        if user_id:
            await manager.send_presence_update(user_id, message.status)

    else:
        # Unknown message type
        error_msg = ErrorMessage(
            error_code="UNKNOWN_MESSAGE_TYPE",
            error_message=f"Unknown message type: {message.type}",
            session_id=session_id,
        )
        await manager.send_message(websocket, error_msg.model_dump())


async def handle_chat_message(
    websocket: WebSocket,
    session,
    message: ChatMessage,
    manager: EnhancedConnectionManager,
):
    """Handle chat message processing."""

    try:
        # Update session with new message
        session_id = str(session.session_uuid)
        metadata = manager.connection_metadata.get(websocket, {})
        user_id = metadata.get("user_id")

        # Broadcast message received confirmation
        confirmation = {
            "type": MessageType.MESSAGE_RECEIVED,
            "session_id": session_id,
            "user_id": user_id,
            "timestamp": message.timestamp,
            "message_id": f"msg_{hash(message.content)}",
        }
        await manager.send_message(websocket, confirmation)

        # Process the message through the existing chat session
        # This would integrate with your existing agent processing logic
        # For now, we'll send a mock response

        # Simulate agent thinking
        thinking_msg = {
            "type": MessageType.AGENT_THINKING,
            "thinking_content": "Processing your request...",
            "session_id": session_id,
            "timestamp": message.timestamp,
            "is_complete": False,
        }
        await manager.broadcast_to_session(session_id, thinking_msg)

        # Simulate agent response (replace with actual agent processing)
        import asyncio

        await asyncio.sleep(1)  # Simulate processing time

        response_msg = {
            "type": MessageType.AGENT_RESPONSE,
            "content": f"I received your message: {message.content}",
            "session_id": session_id,
            "timestamp": message.timestamp,
            "metadata": {
                "model": "claude-3-sonnet",
                "token_usage": {"input": 100, "output": 50},
            },
        }
        await manager.broadcast_to_session(session_id, response_msg)

    except Exception as e:
        logger.error(f"Error processing chat message: {e}")
        error_msg = ErrorMessage(
            error_code="CHAT_PROCESSING_ERROR",
            error_message=str(e),
            session_id=str(session.session_uuid),
        )
        await manager.send_message(websocket, error_msg.model_dump())


@router.get("/ws/stats")
async def get_websocket_stats(
    manager: EnhancedConnectionManager = Depends(get_connection_manager),
):
    """Get WebSocket connection statistics."""
    return manager.get_connection_stats()


@router.post("/ws/broadcast")
async def broadcast_message(
    message: dict,
    session_id: str = None,
    user_id: str = None,
    manager: EnhancedConnectionManager = Depends(get_connection_manager),
):
    """Broadcast a message to WebSocket connections."""

    if session_id:
        await manager.broadcast_to_session(session_id, message)
    elif user_id:
        await manager.broadcast_to_user(user_id, message)
    else:
        await manager.broadcast_to_all(message)

    return {"message": "Broadcast sent successfully"}
