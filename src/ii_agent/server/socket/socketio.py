import logging
import uuid
from typing import Any, Dict, Set

import socketio
from ii_agent.core.client_host import client_host_var
from ii_agent.core.event import AgentStatus, EventType
from ii_agent.db.agent import AgentRunTask, RunStatus
from ii_agent.db.manager import get_db_session_local
from ii_agent.server.auth.jwt_handler import jwt_handler
from ii_agent.server.models.sessions import SessionInfo
from datetime import datetime, timedelta, timezone

from ii_agent.server.shared import (
    sandbox_service,
    session_service,
    config,
)
from ii_agent.server.socket.command.handler_factory import CommandHandlerFactory
from ii_agent.server.socket.session_store import session_store

logger = logging.getLogger(__name__)


class SocketIOManager:
    """Manages Socket.IO connections and their associated chat sessions."""

    def __init__(self, sio: socketio.AsyncServer):
        self.sio = sio
        self.sid_sesion_map: Dict[str, str] = {}
        self.command_factory = CommandHandlerFactory(sio=sio)

    def init(self):
        self.sio.event(self.connect)
        self.sio.event(self.disconnect)
        self.sio.on("join_session")(self.join_session)
        self.sio.on("chat_message")(self.chat_message)
        self.sio.on("leave_session")(self.leave_session)  # backward compatibility

    async def _emit_chat_event(
        self, room: str, event_type: str, content: Dict[str, Any]
    ) -> None:
        """Helper method to emit chat events and reduce duplication."""
        await self.sio.emit(
            "chat_event",
            {
                "type": event_type,
                "content": content,
            },
            room=room,
        )

    async def _emit_error(self, room: str, message: str) -> None:
        """Helper method to emit error events."""
        await self._emit_chat_event(room, "error", {"message": message})

    async def _emit_status_update(self, room: str, status: AgentStatus) -> None:
        """Helper method to emit status update events."""
        await self._emit_chat_event(room, EventType.STATUS_UPDATE, {"status": status})

    async def _emit_system_event(self, room: str, message: str, **kwargs) -> None:
        """Helper method to emit system events."""
        content = {"message": message}
        content.update(kwargs)
        await self._emit_chat_event(room, EventType.SYSTEM, content)

    async def check_and_cleanup_session(self, session_uuid: str) -> None:
        """Check if session is empty and clean up sandbox if needed."""
        if not session_uuid:
            logger.debug("Session UUID is None, skipping cleanup check")
            return
        session_id = uuid.UUID(session_uuid)
        try:
            is_empty = await session_store.is_session_empty(session_uuid)
            if is_empty:
                logger.info(f"Session {session_uuid} is empty, checking running task")

                async with get_db_session_local() as db:
                    run_task: AgentRunTask = (
                        await AgentRunTask.find_last_by_session_id_and_status(
                            db=db, session_id=session_id, status=RunStatus.RUNNING
                        )
                    )
                ttl = None
                if run_task:
                    logger.info(
                        f"Session {session_uuid} has running tasks, run_id: {run_task.id}"
                    )
                    running_delta = datetime.now(timezone.utc) - run_task.created_at

                    logger.info(
                        f"Session {session_uuid} has been running for {running_delta.total_seconds()} seconds"
                    )

                    ttl = max(
                        2 * 60 * 60,
                        int(3 * 60 * 60 - running_delta.total_seconds()),
                    )

                    await sandbox_service.cleanup_sandbox_for_session(
                        session_uuid=session_id, time_til_clean_up=ttl
                    )
            return
        except Exception as e:
            logger.error(f"Failed to check and cleanup session {session_uuid}: {e}")

    def _extract_client_host(self, environ: Dict[str, Any]) -> str:
        """Extract the client-facing hostname from a Socket.IO ASGI environ dict.

        Checks X-Forwarded-Host (for reverse proxies) then Host, returning only
        the hostname part (strips any :port suffix).
        """
        raw = (
            environ.get("HTTP_X_FORWARDED_HOST")
            or environ.get("HTTP_HOST")
            or ""
        )
        # Keep only the hostname, drop port (e.g. "192.168.2.2:8000" → "192.168.2.2")
        host = raw.split(":")[0].strip()
        return host or "localhost"

    async def _require_session(self, data: Dict[str, Any]) -> SessionInfo | None:
        session_uuid_str = data.get("session_uuid")
        if not session_uuid_str:
            return None
        try:
            session_uuid = uuid.UUID(session_uuid_str)
            session_info = await session_service.find_session_by_id(session_uuid)
            return session_info
        except ValueError:
            return None

    async def chat_message(self, sid, data):
        """Handle incoming chat messages."""
        logger.info(f"Received chat message from {sid}: {data}")
        session = await self._require_session(data)

        if not session:
            logger.error(
                f"Chat Session for {sid} is required but empty!, user_id: {data.get('session_id')}"
            )
            await self._emit_error(sid, "Chat Session is required!")
            return
        message_type = data.get("type")
        content = data.get("content", {})

        # Set the client host for this request so expose_port() returns URLs
        # that are routable from the caller's machine, not just localhost.
        session_data = await self.sio.get_session(sid)
        client_host_var.set(session_data.get("client_host", "localhost"))

        try:
            logger.debug("Start processing message of type: %s", message_type)
            handler = self.command_factory.get_handler_by_string(message_type)
            if handler:
                await handler.handle(content, session)
            else:
                await self._emit_chat_event(
                    sid,
                    EventType.ERROR,
                    {"message": f"Unknown message type: {message_type}"},
                )
        except Exception as e:
            logger.error(f"Error handling chat message from {sid}: {e}", exc_info=True)
            await self._emit_error(sid, f"Error processing message: {str(e)}")

    async def join_session(self, sid, data):
        """Join the session after connection is fully established."""
        try:
            # Get the stored session data
            session_data = await self.sio.get_session(sid)
            if not session_data or not session_data.get("authenticated"):
                logger.error(f"No valid session data found for {sid}")
                await self.sio.disconnect(sid)
                self.sid_sesion_map.pop(sid, None)
                return

            user_id = session_data.get("user_id")
            session_uuid_str = data.get("session_uuid")
            logger.info(f"Joining session for {session_uuid_str}, user: {user_id}")

            session_info: SessionInfo = await session_service.get_or_create_sessison(
                session_uuid=session_uuid_str, user_id=user_id
            )

            await self._emit_system_event(
                sid, "Session created", session_id=str(session_info.id)
            )

            logger.info(
                f"New chat session {session_info.id} created for user {user_id}: {sid}"
            )

            await self.sio.enter_room(sid, str(session_info.id))
            self.sid_sesion_map[sid] = str(session_info.id)

            # Add SID to session mapping
            await session_store.add_sid_to_session(str(session_info.id), sid)

            logger.info(f"Socket {sid} joined room {session_info.id}")
            session_count = await self.get_connection_count(session_info.id)
            logger.debug(
                f"Number of socket connections: {session_count} for current session: {session_uuid_str}"
            )
            # Send handshake event
            await self._handshake(sid, session_info)
        except Exception as e:
            logger.error(f"Error initializing session for {sid}: {e}", exc_info=True)
            await self._emit_error(sid, f"Session initialization failed: {str(e)}")
            await self.sio.disconnect(sid)

    async def _handshake(self, sid, session_info: SessionInfo):
        """Handle handshake message."""
        await self._emit_chat_event(
            room=str(sid),
            event_type=EventType.CONNECTION_ESTABLISHED,
            content={
                "message": "Connected to Agent WebSocket Server",
                "workspace_path": config.workspace_path,
            },
        )

        async with get_db_session_local() as db:
            running_task = await AgentRunTask.find_last_by_session_id_and_status(
                db=db, session_id=session_info.id, status=RunStatus.RUNNING
            )

        if running_task:
            await self._emit_status_update(str(session_info.id), AgentStatus.RUNNING)
        else:
            await self._emit_status_update(str(sid), AgentStatus.READY)

    async def connect(self, sid, environ, auth):
        """Handle Socket.IO client connection."""
        logger.info(f"Socket.IO client connecting: {sid}")

        # Extract authentication info
        if not auth or "token" not in auth:
            logger.warning(
                f"Socket.IO connection rejected: No authentication token provided for {sid}"
            )
            return False

        auth_token = auth["token"]
        session_uuid_str = auth.get("session_uuid")

        # Try to authenticate
        try:
            # Verify the access token
            payload = jwt_handler.verify_access_token(auth_token)
            if payload:
                user_id = payload.get("user_id")
                logger.info(f"Socket.IO authenticated for user: {user_id}")

                await self.sio.save_session(
                    sid,
                    {
                        "user_id": user_id,
                        "session_uuid": session_uuid_str,
                        "authenticated": True,
                        "client_host": self._extract_client_host(environ),
                    },
                )
                self.sid_sesion_map[sid] = session_uuid_str
                return True

            else:
                logger.warning(
                    f"Socket.IO connection rejected: Invalid or expired token for {sid}"
                )
                return False
        except Exception as e:
            logger.error(
                f"Socket.IO connection rejected: Error verifying token for {sid}: {e}"
            )
            return False

    async def leave_session(self, sid: str, data: Dict[str, Any]):
        """Handle leave_session event - backward compatibility."""
        logger.info(f"Socket.IO client leaving session: {sid}")
        session_uuid = self.sid_sesion_map.pop(sid, None)
        if session_uuid:
            await self.sio.leave_room(sid, session_uuid)
            await session_store.remove_sid_from_session(session_uuid, sid)
            await self.check_and_cleanup_session(session_uuid)

    async def disconnect(self, sid: str):
        """Handle Socket.IO disconnection and cleanup."""
        logger.info(f"Socket.IO client disconnecting: {sid}")
        session_uuid = self.sid_sesion_map.pop(sid, None)

        try:
            if session_uuid:
                await self.sio.leave_room(sid, str(session_uuid))
                # Remove SID from session mapping
                await session_store.remove_sid_from_session(str(session_uuid), sid)
                await self.check_and_cleanup_session(str(session_uuid))

            await self.sio.disconnect(sid)

        except ValueError as e:
            logger.warning(f"Failed to leave room {session_uuid} for socket {sid}: {e}")
            # Continue with cleanup even if leaving room fails

    async def get_connection_count(self, session_id: uuid.UUID) -> int:
        """Get the number of active connections for a specific session."""
        try:
            sids = await session_store.get_session_sids(str(session_id))
            return len(sids)
        except Exception as e:
            logger.error(
                f"Failed to get connection count for session {session_id}: {e}"
            )
            return 0
