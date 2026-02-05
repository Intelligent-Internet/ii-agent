"""Chat API router with SSE streaming support."""

import json
import logging
from typing import Optional, cast
from datetime import datetime
from uuid import UUID
import uuid

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.db.chat import ChatMessage
from ii_agent.metrics.models import TokenUsage
from ii_agent.server.api.deps import DBSession
from ii_agent.server.api.deps import CurrentUser
from ii_agent.server.chat.models import (
    ChatMessageRequest,
    ChatMessageResponse,
    MessageHistoryResponse,
    ClearHistoryResponse,
    StopConversationRequest,
    StopConversationResponse,
    MessageRoleType,
    UsageObject,
    FileAttachmentResponse,
)
from ii_agent.server.chat.service import ChatService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/chat", tags=["chat"])


def _normalize_content(content) -> list:
    """
    Normalize content to list format, handling old format for backward compatibility.

    Returns the content list directly (not wrapped in any structure).
    """
    if not content:
        return []

    # Handle old format {"parts": [...]}
    if isinstance(content, dict) and "parts" in content:
        return content["parts"]

    # New format [...]
    if isinstance(content, list):
        return content

    return []


async def _fetch_file_attachments_for_messages(
    db_session: AsyncSession,
    messages: list[ChatMessage],
) -> dict[uuid.UUID, list[FileAttachmentResponse]]:
    """
    Fetch file attachments for all messages using a single query.

    Args:
        db_session: Database session
        messages: List of ChatMessage objects

    Returns:
        Dictionary mapping file_id to FileAttachmentResponse
    """
    from sqlalchemy import select
    from ii_agent.db.models import FileUpload
    from uuid import UUID

    # Collect all unique file IDs from all messages
    all_file_ids = set()
    for msg in messages:
        file_ids = msg.file_ids
        if file_ids:
            all_file_ids.update(file_ids)

    # If no files, return empty dict
    if not all_file_ids:
        return {}

    # Single query to fetch all file uploads
    result = await db_session.execute(
        select(FileUpload).where(
            FileUpload.id.in_(
                [str(fid) if isinstance(fid, UUID) else fid for fid in all_file_ids]
            )
        )
    )
    file_uploads = result.scalars().all()

    # Create mapping: file_id -> FileAttachmentResponse
    file_map = {}
    for file_upload in file_uploads:
        file_id = uuid.UUID(file_upload.id)
        file_map[file_id] = FileAttachmentResponse(
            id=file_id,
            file_name=file_upload.file_name,
            file_size=file_upload.file_size,
            content_type=file_upload.content_type,
            created_at=file_upload.created_at,
        )

    return file_map


async def _build_message_history_response(
    *,
    db_session: AsyncSession,
    session_id: str,
    limit: int,
    before: Optional[str],
) -> MessageHistoryResponse:
    """
    Fetch and format message history for responses.
    """
    messages, has_more = await ChatService.get_message_history(
        db_session=db_session,
        session_id=session_id,
        limit=limit,
        before=before,
    )

    message_responses = []
    file_attach_map = await _fetch_file_attachments_for_messages(
        db_session=db_session, messages=messages
    )
    for msg in messages:
        # Normalize content to list format
        content_parts = _normalize_content(msg.content)
        files = []
        if msg.file_ids:
            for f in msg.file_ids:
                if f in file_attach_map:
                    files.append(file_attach_map[f])

        message_responses.append(
            ChatMessageResponse(
                id=str(msg.id),
                role=cast(MessageRoleType, msg.role),
                content=content_parts,
                usage=TokenUsage(**dict(msg.usage)) if msg.usage is not None else None,
                tokens=msg.tokens,
                model=msg.model,
                created_at=msg.created_at,
                files=files,
                finish_reason=msg.finish_reason,
            )
        )

    return MessageHistoryResponse(
        messages=message_responses,
        has_more=has_more,
        total_count=len(message_responses),
    )


@router.post("/conversations")
async def send_chat_message(
    request: ChatMessageRequest,
    current_user: CurrentUser,
    db_session: DBSession,
):
    """
    Send a chat message with automatic session creation or reuse existing session.

    If request.session_id is provided, reuses that session.
    Otherwise, creates a new session automatically.

    Tool Support:
    - Provide tools parameter with granular control: {"web_search": true, "image_search": false}
    - Available tools: web_search, image_search, web_visit
    - Future tools: code_interpreter, file_search (coming soon)
    - LLM can call enabled tools as needed during conversation
    - Tool results are streamed back via tool_result events
    - Credits are deducted for both LLM usage and tool execution

    Returns SSE stream with event types:

    **Event: delta** (streaming content chunks)
    - delta_type: "content" | "reasoning"
    - data: string chunk

    **Event: message** (metadata and control events)
    - event: "session_created" - New session created (only if new session)
      - data: {session_id, name, status, agent_type, model_id, created_at}
    - event: "stream_start" - Message started
      - data: {session_id, model_id}
    - event: "tool_calls" - Tool/function calls
      - data: array of tool call objects
    - event: "function_call" - Legacy function call
      - data: {name, arguments}
    - event: "usage" - Token usage statistics
      - data: {completion_tokens, prompt_tokens, total_tokens, ...}
    - event: "stream_complete" - Stream finished
      - data: {message_id, message, usage, tokens, elapsed_ms}
    - event: "done" - All events sent
    - event: "error" - Error occurred
      - data: {error, code}

    **Event: tool_call** (tool invocation by LLM)
    - status: "start" - Tool call initiated
      - data: {id, name, type}
    - status: "delta" - Tool input streaming
      - data: {id, delta} (partial JSON)
    - status: "stop" - Tool call complete
      - data: {id, name, input} (complete JSON)

    **Event: tool_result** (tool execution result)
    - status: "info"
    - data: {tool_call_id, name, output, is_error}
    """

    # Validate model exists and is available
    try:
        await ChatService.validate_model_for_chat(
            db_session=db_session,
            model_id=request.model_id,
            user_id=str(current_user.id),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Check credits
    has_credits = await ChatService.check_sufficient_credits(
        db_session=db_session, user_id=str(current_user.id)
    )
    if not has_credits:
        raise HTTPException(status_code=402, detail="Insufficient credits")

    # Use existing session or create new one
    session_metadata = None
    session_id = None

    if request.session_id:
        # Use existing session
        session_id = str(request.session_id)

        # Validate user has access to this session
        try:
            await ChatService.validate_session_access(
                db_session=db_session,
                session_id=session_id,
                user_id=str(current_user.id),
            )
            logger.info(
                f"Reusing existing session {session_id} for user {current_user.id}"
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
    else:
        # Create new session
        try:
            session_metadata = await ChatService.create_chat_session(
                db_session=db_session,
                user_id=str(current_user.id),
                user_message=request.content,
                model_id=request.model_id,
            )
            session_id = session_metadata.session_id
            request.session_id = uuid.UUID(session_id)
            logger.info(f"Created new session {session_id} for user {current_user.id}")

        except Exception as e:
            logger.error(f"Failed to create session: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to create session")

    async def event_generator():
        """Generate SSE events from provider stream following new SSE contract."""
        import time

        start_time = time.time()
        event_count = 0
        logger.info(f"event_generator started for session {session_id}")

        try:
            # Send session created event only if this is a new session
            if session_metadata:
                session_event = {
                    "status": "created",
                    "session_id": session_metadata.session_id,
                    "name": session_metadata.name,
                    "agent_type": session_metadata.agent_type,
                    "model_id": session_metadata.model_id,
                    "created_at": session_metadata.created_at,
                }
                yield f"event: session\ndata: {json.dumps(session_event)}\n\n"
                event_count += 1

            # Stream response from provider
            async for event in ChatService.stream_chat_response(
                db_session=db_session,
                chat_request=request,
                user_id=str(current_user.id),
            ):
                event_count += 1
                event_type = event.get("type")

                # Content events (start/delta/stop)
                if event_type == "content_start":
                    yield f"event: content\ndata: {json.dumps({'status': 'start'})}\n\n"

                elif event_type == "content_delta":
                    content_event = {"status": "delta", "delta": event.get("content")}
                    yield f"event: content\ndata: {json.dumps(content_event)}\n\n"

                elif event_type == "content_stop":
                    yield f"event: content\ndata: {json.dumps({'status': 'stop'})}\n\n"

                # Thinking events (delta-only, no start/stop)
                elif event_type == "thinking_delta":
                    thinking_event = {"status": "delta", "delta": event.get("thinking")}
                    # Include signature if present (for o1 models)
                    if event.get("signature"):
                        thinking_event["signature"] = event.get("signature")
                    yield f"event: thinking\ndata: {json.dumps(thinking_event)}\n\n"

                # Tool call events (start/delta/stop)
                elif event_type == "tool_use_start":
                    tool_call = event.get("tool_call", {})
                    tool_event = {
                        "status": "start",
                        "id": tool_call.id
                        if hasattr(tool_call, "id")
                        else tool_call.get("id"),
                        "name": tool_call.name
                        if hasattr(tool_call, "name")
                        else tool_call.get("name"),
                        "type": tool_call.type
                        if hasattr(tool_call, "type")
                        else tool_call.get("type", "function"),
                    }
                    yield f"event: tool_call\ndata: {json.dumps(tool_event)}\n\n"

                elif event_type == "tool_use_delta":
                    tool_call = event.get("tool_call", {})
                    tool_event = {
                        "status": "delta",
                        "id": tool_call.id
                        if hasattr(tool_call, "id")
                        else tool_call.get("id"),
                        "delta": tool_call.input
                        if hasattr(tool_call, "input")
                        else tool_call.get("input", ""),  # Partial JSON
                    }
                    yield f"event: tool_call\ndata: {json.dumps(tool_event)}\n\n"

                elif event_type == "tool_use_stop":
                    tool_call = event.get("tool_call", {})
                    tool_event = {
                        "status": "stop",
                        "id": tool_call.id
                        if hasattr(tool_call, "id")
                        else tool_call.get("id"),
                        "name": tool_call.name
                        if hasattr(tool_call, "name")
                        else tool_call.get("name"),
                        "input": tool_call.input
                        if hasattr(tool_call, "input")
                        else tool_call.get("input"),  # Complete JSON
                    }
                    yield f"event: tool_call\ndata: {json.dumps(tool_event)}\n\n"

                # Code interpreter events (start/delta/stop)
                elif event_type == "code_interpreter_start":
                    yield f"event: code_block\ndata: {json.dumps({'status': 'start'})}\n\n"

                elif event_type == "code_interpreter_delta":
                    ci_event = {"status": "delta", "delta": event.get("content")}
                    yield f"event: code_block\ndata: {json.dumps(ci_event)}\n\n"

                elif event_type == "code_interpreter_stop":
                    yield f"event: code_block\ndata: {json.dumps({'status': 'stop'})}\n\n"

                # Tool result events (from backend execution)
                elif event_type == "tool_result":
                    result_event = {
                        "status": "info",
                        "tool_call_id": event.get("tool_call_id"),
                        "name": event.get("name"),
                        "output": event.get("output"),
                        "is_error": event.get("is_error", False),
                    }
                    yield f"event: tool_result\ndata: {json.dumps(result_event)}\n\n"

                # Usage events (per LLM turn)
                elif event_type == "usage":
                    usage = event.get("usage", {})
                    usage_event = {
                        "status": "info",
                        "input_tokens": usage.get("input_tokens", 0),
                        "output_tokens": usage.get("output_tokens", 0),
                        "cache_creation_tokens": usage.get("cache_creation_tokens", 0),
                        "cache_read_tokens": usage.get("cache_read_tokens", 0),
                        "total_tokens": usage.get("input_tokens", 0)
                        + usage.get("output_tokens", 0),
                    }
                    yield f"event: usage\ndata: {json.dumps(usage_event)}\n\n"

                # Complete event (final - only sent when loop exits)
                elif event_type == "complete":
                    elapsed_ms = int((time.time() - start_time) * 1000)
                    complete_event = {
                        "status": "done",
                        "message_id": str(event.get("message_id")),
                        "finish_reason": event.get("finish_reason", "end_turn"),
                        "elapsed_ms": elapsed_ms,
                        "files": event.get("files"),
                    }
                    yield f"event: complete\ndata: {json.dumps(complete_event)}\n\n"

            # Stream completed successfully
            logger.info(f"event_generator completed successfully for session {session_id} after {event_count} events")

        except Exception as e:
            logger.error(f"Chat streaming error: {e}", exc_info=True)
            error_event = {
                "status": "error",
                "error": str(e),
                "code": "streaming_error",
            }
            yield f"event: error\ndata: {json.dumps(error_event)}\n\n"
        finally:
            elapsed = time.time() - start_time
            logger.info(f"event_generator finished for session {session_id}: {event_count} events in {elapsed:.2f}s")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.post(
    "/conversations/{session_id}/stop", response_model=StopConversationResponse
)
async def stop_conversation(
    session_id: uuid.UUID,
    current_user: CurrentUser,
    db_session: DBSession,
) -> StopConversationResponse:
    """
    Stop an ongoing conversation by updating session status to 'pause'.

    Args:
        request: Stop conversation request with session_id
        current_user: Current authenticated user
        db_session: Database session

    Returns:
        StopConversationResponse with success status and last message ID
    """
    session_id = str(session_id)

    # Validate session access
    try:
        await ChatService.validate_session_access(
            db_session=db_session,
            session_id=session_id,
            user_id=str(current_user.id),
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Stop the conversation
    try:
        last_message_id = await ChatService.stop_conversation(
            db_session=db_session,
            session_id=session_id,
        )

        return StopConversationResponse(
            success=True,
            last_message_id=UUID(last_message_id) if last_message_id else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to stop conversation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to stop conversation")


@router.get("/conversations/{session_id}", response_model=MessageHistoryResponse)
async def get_message_history(
    session_id: str,
    current_user: CurrentUser,
    db_session: DBSession,
    limit: int = Query(50, ge=1, le=200),
    before: Optional[str] = None,
) -> MessageHistoryResponse:
    """Get conversation history for a session."""

    try:
        # Validate session access
        await ChatService.validate_session_access(
            db_session=db_session,
            session_id=session_id,
            user_id=str(current_user.id),
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return await _build_message_history_response(
        db_session=db_session,
        session_id=session_id,
        limit=limit,
        before=before,
    )


@router.get("/conversations/{session_id}/public", response_model=MessageHistoryResponse)
async def get_public_message_history(
    session_id: str,
    db_session: DBSession,
    limit: int = Query(50, ge=1, le=200),
    before: Optional[str] = None,
) -> MessageHistoryResponse:
    """Get conversation history for a public session without authentication."""

    try:
        await ChatService.validate_public_session_access(
            db_session=db_session,
            session_id=session_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return await _build_message_history_response(
        db_session=db_session,
        session_id=session_id,
        limit=limit,
        before=before,
    )


@router.delete("/conversation/{session_id}", response_model=ClearHistoryResponse)
async def clear_conversation(
    session_id: str,
    current_user: CurrentUser,
    db_session: DBSession,
) -> ClearHistoryResponse:
    """Clear all messages in a conversation."""

    try:
        # Validate session access
        await ChatService.validate_session_access(
            db_session=db_session,
            session_id=session_id,
            user_id=str(current_user.id),
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Clear messages
    deleted_count = await ChatService.clear_messages(
        db_session=db_session, session_id=session_id
    )

    return ClearHistoryResponse(
        success=True,
        deleted_count=deleted_count,
        message="Conversation cleared successfully",
    )
