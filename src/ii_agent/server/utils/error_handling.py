"""Error handling utilities for the WebSocket server."""

import logging
from typing import Optional

from fastapi import WebSocket

from ii_agent.core.event import EventType, RealtimeEvent

logger = logging.getLogger(__name__)


async def send_error_event(
    websocket: Optional[WebSocket], 
    message: str, 
    error_type: str = "error"
) -> None:
    """Send an error event to the client via WebSocket.
    
    Args:
        websocket: WebSocket connection (may be None)
        message: Error message to send
        error_type: Type of error (for categorization)
    """
    if websocket:
        try:
            await websocket.send_json(
                RealtimeEvent(
                    type=EventType.ERROR,
                    content={"message": message, "error_type": error_type},
                ).model_dump()
            )
        except Exception as e:
            logger.error(f"Error sending error event to client: {e}")


async def handle_service_error(
    websocket: Optional[WebSocket],
    error: Exception,
    operation: str,
    logger_instance: Optional[logging.Logger] = None
) -> None:
    """Handle service errors with consistent logging and client notification.
    
    Args:
        websocket: WebSocket connection (may be None)
        error: The exception that occurred
        operation: Description of the operation that failed
        logger_instance: Logger instance to use (defaults to module logger)
    """
    if logger_instance is None:
        logger_instance = logger
    
    error_message = f"Error during {operation}: {str(error)}"
    logger_instance.error(error_message, exc_info=True)
    
    await send_error_event(websocket, error_message, operation)


def format_validation_error(error: Exception) -> str:
    """Format validation error for client consumption.
    
    Args:
        error: Validation error
        
    Returns:
        Formatted error message
    """
    return f"Invalid request format: {str(error)}"


def format_service_error(error: Exception, service_name: str) -> str:
    """Format service error for client consumption.
    
    Args:
        error: Service error
        service_name: Name of the service that failed
        
    Returns:
        Formatted error message
    """
    return f"{service_name} error: {str(error)}"