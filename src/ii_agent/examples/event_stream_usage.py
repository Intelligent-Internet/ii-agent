"""
Example demonstrating how to use the refactored AgentController with EventStream abstraction.

This example shows how to:
1. Create an AsyncEventStream
2. Set up WebSocket and Database subscribers
3. Instantiate AgentController with the event stream
4. Handle events through the abstraction layer
"""

import asyncio
import logging
import uuid
from typing import Optional

from fastapi import WebSocket

from ii_agent.controller.agent_controller import AgentController
from ii_agent.core.event_stream import AsyncEventStream
from ii_agent.subscribers.websocket_subscriber import WebSocketSubscriber
from ii_agent.subscribers.database_subscriber import DatabaseSubscriber


async def create_agent_with_event_stream(
    system_prompt: str,
    agent,
    tools,
    init_history,
    workspace_manager,
    logger_for_agent_logs: logging.Logger,
    websocket: Optional[WebSocket] = None,
    session_id: Optional[uuid.UUID] = None,
    interactive_mode: bool = True,
) -> AgentController:
    """
    Create an AgentController with proper event stream setup.
    
    This function demonstrates how to wire up the event stream with subscribers.
    """
    # Create the event stream
    event_stream = AsyncEventStream(logger=logger_for_agent_logs)
    
    # Create and subscribe the WebSocket subscriber if websocket is provided
    if websocket:
        websocket_subscriber = WebSocketSubscriber(websocket, logger_for_agent_logs)
        event_stream.subscribe(websocket_subscriber.handle_event)
    
    # Create and subscribe the database subscriber if session_id is provided
    if session_id:
        database_subscriber = DatabaseSubscriber(session_id, logger_for_agent_logs)
        event_stream.subscribe(database_subscriber.handle_event)
    
    # Create the AgentController with the event stream
    agent_controller = AgentController(
        system_prompt=system_prompt,
        agent=agent,
        tools=tools,
        init_history=init_history,
        workspace_manager=workspace_manager,
        event_stream=event_stream,
        logger_for_agent_logs=logger_for_agent_logs,
        interactive_mode=interactive_mode,
    )
    
    return agent_controller


# Example of adding additional custom event subscribers
class LoggingSubscriber:
    """Example custom subscriber that logs all events."""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
    
    def handle_event(self, event):
        """Log all events for debugging/monitoring."""
        self.logger.info(f"Event: {event.type} - {event.content}")


def add_logging_subscriber(event_stream: AsyncEventStream, logger: logging.Logger):
    """Add a logging subscriber to monitor all events."""
    logging_subscriber = LoggingSubscriber(logger)
    event_stream.subscribe(logging_subscriber.handle_event)


# Usage example:
# event_stream = AsyncEventStream()
# add_logging_subscriber(event_stream, logger)
# agent_controller = AgentController(..., event_stream=event_stream, ...)
# 
# Now the AgentController will publish events to the stream, and all subscribers
# (WebSocket, Database, Logging) will receive and handle them independently.