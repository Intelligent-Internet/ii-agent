"""Enhanced WebSocket connection manager with authentication and advanced features."""

import logging
import uuid
import json
import asyncio
from typing import Dict, Set, Optional, List
from datetime import datetime, timezone
from fastapi import WebSocket, WebSocketDisconnect

from ii_agent.core.config.ii_agent_config import IIAgentConfig
from ii_agent.db.manager import get_db
from ii_agent.db.models import User
from ii_agent.server.auth.jwt_handler import jwt_handler
from ii_agent.server.services.session_service import SessionService
from ii_agent.server.websocket.chat_session import ChatSession

logger = logging.getLogger(__name__)


class EnhancedConnectionManager:
    """Enhanced WebSocket connection manager with authentication and advanced features."""

    def __init__(
        self,
        session_service: SessionService,
        config: IIAgentConfig,
    ):
        # Active chat sessions mapped by WebSocket
        self.sessions: Dict[WebSocket, ChatSession] = {}

        # User to WebSocket mappings for multi-device support
        self.user_connections: Dict[str, Set[WebSocket]] = {}

        # Session UUID to WebSocket mappings for session sharing
        self.session_connections: Dict[str, Set[WebSocket]] = {}

        # Connection metadata
        self.connection_metadata: Dict[WebSocket, dict] = {}

        self.session_service = session_service
        self.config = config

        # Start background tasks
        asyncio.create_task(self._periodic_cleanup())

    async def authenticate_connection(self, websocket: WebSocket) -> Optional[User]:
        """Authenticate WebSocket connection using JWT token."""
        try:
            # Get token from query params or headers
            token = websocket.query_params.get("token")
            if not token:
                # Check headers (if available in WebSocket implementation)
                token = websocket.headers.get("Authorization", "").replace(
                    "Bearer ", ""
                )

            if not token:
                return None

            # Verify token
            payload = jwt_handler.verify_access_token(token)
            if not payload:
                return None

            # Get user from database
            db = next(get_db())
            try:
                user = db.query(User).filter(User.id == payload.get("user_id")).first()
                return user if user and user.is_active else None
            finally:
                db.close()

        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return None

    async def connect(
        self, websocket: WebSocket, require_auth: bool = True
    ) -> Optional[ChatSession]:
        """Accept a new WebSocket connection and create a chat session."""

        # Authenticate connection if required
        user = None
        if require_auth:
            user = await self.authenticate_connection(websocket)
            if not user:
                await websocket.close(code=1008, reason="Authentication required")
                return None

        await websocket.accept()

        # Get connection parameters
        session_uuid_str = websocket.query_params.get("session_uuid")
        device_id = websocket.query_params.get("device_id")
        client_info = websocket.query_params.get("client_info", "unknown")

        # Parse session UUID
        session_uuid = None
        if session_uuid_str:
            try:
                session_uuid = uuid.UUID(session_uuid_str)
            except ValueError:
                logger.warning(f"Invalid session UUID: {session_uuid_str}")

        # Store connection metadata
        self.connection_metadata[websocket] = {
            "user_id": user.id if user else None,
            "device_id": device_id,
            "client_info": client_info,
            "connected_at": datetime.now(timezone.utc),
            "last_activity": datetime.now(timezone.utc),
        }

        # Create or resume chat session
        session = self.session_service.create_session(
            websocket=websocket,
            session_uuid=session_uuid,
            device_id=device_id,
        )

        self.sessions[websocket] = session

        # Track user connections
        if user:
            if user.id not in self.user_connections:
                self.user_connections[user.id] = set()
            self.user_connections[user.id].add(websocket)

        # Track session connections
        session_id = str(session.session_uuid)
        if session_id not in self.session_connections:
            self.session_connections[session_id] = set()
        self.session_connections[session_id].add(websocket)

        logger.info(
            f"New WebSocket connection established: user={user.id if user else 'anonymous'}, "
            f"session={session_id}, device={device_id}"
        )

        # Send connection confirmation
        await self.send_message(
            websocket,
            {
                "type": "connection_established",
                "session_id": session_id,
                "user_id": user.id if user else None,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        return session

    async def disconnect(self, websocket: WebSocket):
        """Handle WebSocket disconnection and cleanup."""
        metadata = self.connection_metadata.get(websocket, {})
        user_id = metadata.get("user_id")

        logger.info(f"WebSocket disconnecting: user={user_id}")

        # Clean up session
        if websocket in self.sessions:
            session = self.sessions[websocket]
            session_id = str(session.session_uuid)

            # Notify other connections in the same session about disconnection
            await self.broadcast_to_session(
                session_id,
                {
                    "type": "user_disconnected",
                    "user_id": user_id,
                    "device_id": metadata.get("device_id"),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                exclude=[websocket],
            )

            session.cleanup()
            del self.sessions[websocket]

            # Remove from session connections
            if session_id in self.session_connections:
                self.session_connections[session_id].discard(websocket)
                if not self.session_connections[session_id]:
                    del self.session_connections[session_id]

        # Remove from user connections
        if user_id and user_id in self.user_connections:
            self.user_connections[user_id].discard(websocket)
            if not self.user_connections[user_id]:
                del self.user_connections[user_id]

        # Clean up metadata
        if websocket in self.connection_metadata:
            del self.connection_metadata[websocket]

    async def send_message(self, websocket: WebSocket, message: dict):
        """Send a message to a specific WebSocket connection."""
        try:
            await websocket.send_text(json.dumps(message))

            # Update last activity
            if websocket in self.connection_metadata:
                self.connection_metadata[websocket]["last_activity"] = datetime.now(
                    timezone.utc
                )

        except WebSocketDisconnect:
            logger.warning("Attempted to send message to disconnected WebSocket")
            await self.disconnect(websocket)
        except Exception as e:
            logger.error(f"Error sending WebSocket message: {e}")

    async def broadcast_to_user(
        self, user_id: str, message: dict, exclude: List[WebSocket] = None
    ):
        """Broadcast a message to all connections for a specific user."""
        if user_id not in self.user_connections:
            return

        exclude = exclude or []
        connections = self.user_connections[user_id] - set(exclude)

        if connections:
            await asyncio.gather(
                *[self.send_message(ws, message) for ws in connections],
                return_exceptions=True,
            )

    async def broadcast_to_session(
        self, session_id: str, message: dict, exclude: List[WebSocket] = None
    ):
        """Broadcast a message to all connections in a specific session."""
        if session_id not in self.session_connections:
            return

        exclude = exclude or []
        connections = self.session_connections[session_id] - set(exclude)

        if connections:
            await asyncio.gather(
                *[self.send_message(ws, message) for ws in connections],
                return_exceptions=True,
            )

    async def broadcast_to_all(self, message: dict):
        """Broadcast a message to all active connections."""
        if self.sessions:
            await asyncio.gather(
                *[self.send_message(ws, message) for ws in self.sessions.keys()],
                return_exceptions=True,
            )

    def get_session(self, websocket: WebSocket) -> Optional[ChatSession]:
        """Get the chat session for a WebSocket connection."""
        return self.sessions.get(websocket)

    def get_user_connections(self, user_id: str) -> Set[WebSocket]:
        """Get all WebSocket connections for a specific user."""
        return self.user_connections.get(user_id, set())

    def get_session_connections(self, session_id: str) -> Set[WebSocket]:
        """Get all WebSocket connections for a specific session."""
        return self.session_connections.get(session_id, set())

    def get_connection_count(self) -> int:
        """Get the number of active connections."""
        return len(self.sessions)

    def get_user_count(self) -> int:
        """Get the number of unique users connected."""
        return len(self.user_connections)

    def get_session_count(self) -> int:
        """Get the number of active sessions."""
        return len(self.session_connections)

    def get_connection_stats(self) -> dict:
        """Get comprehensive connection statistics."""
        now = datetime.now(timezone.utc)

        # Calculate activity stats
        active_5min = 0
        active_1hr = 0

        for metadata in self.connection_metadata.values():
            last_activity = metadata.get("last_activity")
            if last_activity:
                time_diff = (now - last_activity).total_seconds()
                if time_diff <= 300:  # 5 minutes
                    active_5min += 1
                if time_diff <= 3600:  # 1 hour
                    active_1hr += 1

        return {
            "total_connections": self.get_connection_count(),
            "unique_users": self.get_user_count(),
            "active_sessions": self.get_session_count(),
            "active_last_5min": active_5min,
            "active_last_1hr": active_1hr,
            "client_types": self._get_client_type_stats(),
        }

    def _get_client_type_stats(self) -> dict:
        """Get statistics about client types."""
        client_stats = {}
        for metadata in self.connection_metadata.values():
            client_info = metadata.get("client_info", "unknown")
            client_stats[client_info] = client_stats.get(client_info, 0) + 1
        return client_stats

    async def _periodic_cleanup(self):
        """Periodic cleanup of stale connections."""
        while True:
            try:
                await asyncio.sleep(300)  # Run every 5 minutes
                await self._cleanup_stale_connections()
            except Exception as e:
                logger.error(f"Error in periodic cleanup: {e}")

    async def _cleanup_stale_connections(self):
        """Clean up connections that haven't been active."""
        now = datetime.now(timezone.utc)
        stale_connections = []

        for websocket, metadata in self.connection_metadata.items():
            last_activity = metadata.get("last_activity")
            if last_activity:
                time_diff = (now - last_activity).total_seconds()
                if time_diff > 3600:  # 1 hour without activity
                    stale_connections.append(websocket)

        # Clean up stale connections
        for websocket in stale_connections:
            logger.info("Cleaning up stale WebSocket connection")
            await self.disconnect(websocket)

    async def send_typing_indicator(
        self, session_id: str, user_id: str, is_typing: bool
    ):
        """Send typing indicator to all connections in a session."""
        message = {
            "type": "typing_indicator",
            "session_id": session_id,
            "user_id": user_id,
            "is_typing": is_typing,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await self.broadcast_to_session(session_id, message)

    async def send_presence_update(self, user_id: str, status: str):
        """Send presence update to user's connections."""
        message = {
            "type": "presence_update",
            "user_id": user_id,
            "status": status,  # online, away, busy, offline
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await self.broadcast_to_user(user_id, message)
