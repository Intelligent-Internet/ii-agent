"""
Backend function to call agent programmatically, matching the exact
production flow of UserQueryHandler._handle_v1_query().

Reference files:
  - server/socket/command/query_handler.py  (_handle_v1_query, lines 193-309)
  - server/services/agent_service.py        (create_agent_v1, lines 696-727)
  - server/socket/command/command_handler.py (validate_and_update_session, lines 141-222)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Literal, Optional

from ii_agent.agents.types import AgentType
from ii_agent.core.config.settings import get_settings
from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.core.container import get_app_container
from ii_agent.core.db import get_db_session_local, get_session_factory
from ii_agent.core.logger import logger
from ii_agent.files.media.media import Image, File as UrlFile
from ii_agent.realtime.events.app_events import AppEvent
from ii_agent.realtime.events.converter import convert_agent_event_to_realtime
from ii_agent.sessions.schemas import SessionInfo
from ii_agent.tasks.models import RunTask
from ii_agent.tasks.types import RunStatus
from ii_agent.ii_claw.custom_agent import resolve_skill_creator, resolve_connector_tool, resolve_system_prompt
from ii_agent.agents.factory import agent_factory
from ii_agent.agents.runs.agent import RunOutput, RunCompletedEvent
from ii_agent.agents.sessions.store import AgentSessionStore

# Same constants as query_handler.py
IMAGE_CONTENT_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
SEVEN_DAY_SECONDS = 7 * 24 * 3600


# ---------------------------------------------------------------------------
# Input / Output
# ---------------------------------------------------------------------------

@dataclass
class CallAgentInput:
    """
    Input matching what frontend sends via Socket.IO "chat_message" event.

    Maps to QueryCommandContent (server/models/messages.py lines 104-137).
    Frontend sends: {type: "query", content: {text, files, model_id, agent_type, tool_args, ...}}
    """

    # --- Required ---
    user_id: str                                       # JWT user id
    text: str                                          # User's message

    # --- Model config (frontend model selector) ---
    model_id: Optional[str] = None                     # e.g. "gpt-5.2", "claude-sonnet-4", "custom_model_xyz"
    provider: Optional[str] = None                      # e.g. Provider.OPENAI
    source: Literal["user", "system"] = "user"         # "user" = user key, "system" = platform key

    # --- Agent mode (frontend mode selector) ---
    agent_type: AgentType = AgentType.GENERAL

    # --- Tool toggles (frontend tool switches) ---
    tool_args: Dict[str, Any] = field(default_factory=dict)

    # --- File attachments (frontend file upload) ---
    file_ids: List[str] = field(default_factory=list)  # Uploaded file UUIDs from /files/* API

    # --- Custom agent config (primarily for agent_type == CUSTOM) ---
    custom_system_prompt: Optional[str] = None         # User's custom system prompt
    skill_mode: Optional[str] = "default"              # None | "default" | "custom_skill" | "default_and_custom_skill"
    connector_mode: Optional[str] = "default"          # None | "default" | "custom_connector" | "default_and_custom_connector"

    # --- Optional ---
    session_id: Optional[str] = None                   # None = new session
    metadata: Optional[Dict[str, Any]] = None
    github_repository: Optional[Dict[str, str]] = None


@dataclass
class FileAttachment:
    """A file delivered to the user (from send_user_files tool or RunOutput)."""
    name: str
    url: str
    file_type: str = "documents"  # code, xlsx, archive, documents


@dataclass
class MediaOutput:
    """All media produced by the agent run."""
    images: List[Dict[str, Any]] = field(default_factory=list)   # [{url, mime_type, ...}]
    videos: List[Dict[str, Any]] = field(default_factory=list)   # [{url, format, ...}]
    audio: List[Dict[str, Any]] = field(default_factory=list)    # [{url, format, ...}]
    files: List[FileAttachment] = field(default_factory=list)    # Delivered files (send_user_files)


@dataclass
class CallAgentOutput:
    """Output containing everything the frontend would receive."""

    session_id: str
    run_id: str
    status: RunStatus
    content: Optional[str]                  # Final text response
    events: List[AppEvent]                   # All events (same as Socket.IO)
    media: MediaOutput = field(default_factory=MediaOutput)  # All media/file outputs
    run_output: Optional[RunOutput] = None  # Full RunOutput for programmatic use
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Internal helpers (avoid code duplication between call_agent / call_agent_stream)
# ---------------------------------------------------------------------------

async def _ensure_user_exists(user_id: str) -> None:
    """Ensure the user and API key exist in DB (for CLI/programmatic usage).

    The API key is required because the E2B sandbox MCP server uses it
    as a credential during configure_sandbox_mcp(). Without it, the
    set_credential endpoint returns 400 and sandbox tools (apply_patch,
    ShellRunCommand, etc.) are never registered → "Unknown tool" errors.
    """
    from ii_agent.users.models import User, APIKey
    from sqlalchemy import select
    import secrets

    async with get_db_session_local() as db:
        # Ensure user
        result = await db.execute(select(User).where(User.id == user_id))
        if result.scalars().first() is None:
            user = User(id=user_id, email=f"{user_id}@cli.local", credits=999999.0, bonus_credits=0.0)
            db.add(user)
            await db.flush()
            logger.info(f"Created CLI user: {user_id}")

        # Ensure API key (needed for sandbox MCP tool registration)
        result = await db.execute(
            select(APIKey).where(APIKey.user_id == user_id, APIKey.is_active == True)
        )
        if result.scalars().first() is None:
            api_key = APIKey(
                user_id=user_id,
                api_key=f"ii-claw-{secrets.token_hex(16)}",
                is_active=True,
            )
            db.add(api_key)
            logger.info(f"Created API key for user: {user_id}")

        await db.commit()


async def _resolve_llm_config(session_id: uuid.UUID, user_id: str, source: str, model_id: Optional[str], provider: Optional[str]) -> LLMConfig:
    """Resolve LLM config for the given session/user."""
    container = get_app_container()
    async with get_db_session_local() as db:
        if source == "user" and model_id:
            try:
                setting = await container.model_setting_service.get_model_settings_by_name(
                    db,
                    model_name=model_id,
                    user_id=uuid.UUID(user_id),
                    include_key=True,
                )
                if setting:
                    return LLMConfig(
                        model=setting.model_id,
                        provider=setting.provider,
                    )
            except Exception:
                pass

        # Fallback to system default
        return LLMConfig(model=model_id or "default", provider=provider or "default")


async def _update_session_meta(session_info: SessionInfo, inp: CallAgentInput) -> None:
    """Update session name + agent_type (mirrors command_handler.py:167-170)."""
    container = get_app_container()
    async with get_db_session_local() as db:
        fields: Dict[str, Any] = {}
        if not session_info.name and inp.text:
            fields["name"] = inp.text.strip()[:100]
        if fields:
            await container.session_service.update_session_fields(
                db, session_info.id, **fields
            )


async def _check_credits(llm_config: LLMConfig, user_id: str) -> bool:
    """Check credits (mirrors command_handler.py:185-192)."""
    container = get_app_container()
    async with get_db_session_local() as db:
        return await container.credit_service.has_sufficient_credits(
            db, uuid.UUID(user_id)
        )


async def _create_run_task(session_info: SessionInfo, inp: CallAgentInput) -> RunTask | None:
    """Create RunTask in DB for ii_claw programmatic calls.

    Bypasses claim_task's partial-unique constraint by force-completing
    any stale active tasks first, then inserting directly.
    """
    from ii_agent.tasks.types import TaskType
    from sqlalchemy import select, update

    # Step 1: Force-complete all stale active tasks for this session
    async with get_db_session_local() as db:
        active_values = [s.value for s in RunStatus.active_states()]
        await db.execute(
            update(RunTask)
            .where(
                RunTask.session_id == session_info.id,
                RunTask.status.in_(active_values),
            )
            .values(status=RunStatus.FAILED, error_message="Superseded by new ii_claw call")
        )
        # auto-commit on context exit

    # Step 2: Insert new task directly
    async with get_db_session_local() as db:
        task = RunTask(
            session_id=session_info.id,
            task_type=TaskType.AGENT_RUN,
            status=RunStatus.RUNNING,
        )
        db.add(task)
        await db.flush()
        await db.refresh(task)
        return task


async def _create_agent(inp: CallAgentInput, session_id_str: str, llm_config: LLMConfig):
    """Create IIAgent via AgentFactory.

    Uses resolve_* helpers from ii_claw.custom_agent to build skill_creator,
    connector_tool, and system_prompt based on CallAgentInput config.
    """
    skill_creator = resolve_skill_creator(inp, mode=inp.skill_mode)
    connector_tool = resolve_connector_tool(inp, mode=inp.connector_mode)
    system_prompt = resolve_system_prompt(inp)

    return await agent_factory.create_agent(
        user_id=inp.user_id,
        session_id=session_id_str,
        llm_config=llm_config,
        tool_args=inp.tool_args,
        metadata=inp.metadata,
        agent_type=inp.agent_type,
        session_store=AgentSessionStore(session_maker=get_session_factory()),
        skill_creator=skill_creator,
        connector_tool=connector_tool,
        system_prompt=system_prompt,
    )


async def _process_files(inp: CallAgentInput, session_id_str: str) -> tuple[list[Image], list[UrlFile]]:
    """Process file uploads (mirrors query_handler.py:579-623)."""
    images: list[Image] = []
    files: list[UrlFile] = []

    if not inp.file_ids:
        return images, files

    container = get_app_container()
    async with get_db_session_local() as db:
        files_data = await container.file_service.get_files_by_ids_and_update_session(
            db,
            file_ids=[uuid.UUID(fid) for fid in inp.file_ids],
            user_id=uuid.UUID(inp.user_id),
            session_id=uuid.UUID(session_id_str),
            expiration_seconds=SEVEN_DAY_SECONDS,
        )

    for fd in files_data:
        if not fd.url:
            continue
        files.append(UrlFile(id=fd.id, url=fd.url, filename=fd.name))
        if fd.content_type in IMAGE_CONTENT_TYPES:
            images.append(Image(url=fd.url, mime_type=fd.content_type))

    return images, files


def _extract_media(
    events: List[AppEvent],
    run_output: Optional[RunOutput],
) -> MediaOutput:
    """Extract all media/files from events and RunOutput.

    Sources:
      1. RunOutput.images/videos/audio/files  (direct agent media)
      2. TOOL_RESULT events from send_user_files  (delivered file attachments)
      3. TOOL_RESULT events with images/videos from other tools
    """
    from ii_agent.realtime.events.app_events import AgentToolResultEvent

    media = MediaOutput()

    # --- From RunOutput (images, videos, audio, files from agent) ---
    if run_output:
        if run_output.images:
            for img in run_output.images:
                d = img.model_dump(exclude_none=True) if hasattr(img, "model_dump") else {"url": getattr(img, "url", None)}
                if d.get("url"):
                    media.images.append(d)
        if run_output.videos:
            for vid in run_output.videos:
                d = vid.model_dump(exclude_none=True) if hasattr(vid, "model_dump") else {"url": getattr(vid, "url", None)}
                if d.get("url"):
                    media.videos.append(d)
        if run_output.audio:
            for aud in run_output.audio:
                d = aud.model_dump(exclude_none=True) if hasattr(aud, "model_dump") else {"url": getattr(aud, "url", None)}
                if d.get("url"):
                    media.audio.append(d)
        if run_output.files:
            for f in run_output.files:
                url = getattr(f, "url", None)
                if url:
                    media.files.append(FileAttachment(
                        name=getattr(f, "filename", None) or getattr(f, "name", None) or "file",
                        url=url,
                        file_type=getattr(f, "file_type", "documents") or "documents",
                    ))

    # --- From ToolExecution results (e.g. generate_image, generate_video) ---
    # Collect already-seen URLs to avoid duplicates
    seen_urls: set[str] = set()
    for img in media.images:
        if img.get("url"):
            seen_urls.add(img["url"])
    for vid in media.videos:
        if vid.get("url"):
            seen_urls.add(vid["url"])
    for aud in media.audio:
        if aud.get("url"):
            seen_urls.add(aud["url"])
    for f in media.files:
        seen_urls.add(f.url)

    if run_output and run_output.tools:
        for tool_exec in run_output.tools:
            result = tool_exec.result
            if result is None:
                continue
            display = getattr(result, "user_display_content", None)
            if not isinstance(display, dict) or display.get("type") != "file_url":
                continue
            url = display.get("url")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            mime = display.get("mime_type", "")
            if mime.startswith("image/"):
                media.images.append({"url": url, "mime_type": mime})
            elif mime.startswith("video/"):
                media.videos.append({"url": url, "mime_type": mime})
            elif mime.startswith("audio/"):
                media.audio.append({"url": url, "mime_type": mime})
            else:
                media.files.append(FileAttachment(
                    name=display.get("name") or "file",
                    url=url,
                    file_type="documents",
                ))

    # --- From AgentToolResultEvent events (send_user_files attachments) ---
    for evt in events:
        if not isinstance(evt, AgentToolResultEvent):
            continue

        tool_name = getattr(evt, "tool_name", "")
        content = evt.content if hasattr(evt, "content") else {}
        result = content.get("result") if isinstance(content, dict) else None

        # send_user_files: result = {tool_name: "message", action: {text, attachments: [{name, file_type, url}]}}
        if tool_name == "send_user_files" and isinstance(result, dict):
            action = result.get("action", {})
            attachments = action.get("attachments", [])
            if isinstance(attachments, list):
                for att in attachments:
                    if isinstance(att, dict) and att.get("url") and att["url"] not in seen_urls:
                        media.files.append(FileAttachment(
                            name=att.get("name", "file"),
                            url=att["url"],
                            file_type=att.get("file_type", "documents"),
                        ))
                        seen_urls.add(att["url"])

    return media


async def _extract_content(
    events: List[AppEvent],
    run_output: Optional[RunOutput],
) -> Optional[str]:
    """Extract final text content from RunOutput or events."""
    from ii_agent.realtime.events.app_events import AgentResponseEvent

    if run_output and run_output.content:
        return str(run_output.content)

    # Fallback: collect from AgentResponseEvent events
    parts = []
    for e in events:
        if isinstance(e, AgentResponseEvent):
            content = e.content if hasattr(e, "content") else {}
            if isinstance(content, dict):
                parts.append(content.get("text", ""))
    return "\n".join(parts) if parts else None


async def _update_task_status(task_id: uuid.UUID, status: RunStatus) -> None:
    """Update RunTask status in DB."""
    container = get_app_container()
    async with get_db_session_local() as db:
        await container.run_task_service.transition_status(db, task_id=task_id, to_status=status)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def call_agent(inp: CallAgentInput) -> CallAgentOutput:
    """
    Call agent exactly like frontend does, with full session/DB/event handling.

    Mirrors UserQueryHandler._handle_v1_query() (query_handler.py:193-309):
      [1] Get or create session in DB
      [2] Resolve LLM config (model, provider, API key)
      [3] Validate credits
      [4] Create AgentRunTask in DB
      [5] Create IIAgent via AgentFactory (with skills, connectors)
      [6] Process file uploads -> images + files
      [7] Run agent with streaming, collect events
      [8] Update task status in DB

    Returns:
        CallAgentOutput with session_id, events, final content, and status.
    """
    collected_events: list[AppEvent] = []
    final_status = RunStatus.FAILED
    run_output: Optional[RunOutput] = None
    run_id_str: Optional[str] = None

    try:
        # [0] Ensure user exists
        await _ensure_user_exists(inp.user_id)

        # [1] Session
        container = get_app_container()
        session_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, str(inp.session_id)) if inp.session_id else uuid.uuid4()

        user_uuid = uuid.UUID(inp.user_id)
        async with get_db_session_local() as db:
            session_info = await container.session_service.find_session_by_id(db, session_uuid)
            if not session_info:
                session_info = await container.session_service.create_new_session(
                    db, session_uuid, user_uuid, "v1"
                )

        session_id_str = str(session_info.id)
        await _update_session_meta(session_info, inp)

        # [2] LLM Config
        llm_config = await _resolve_llm_config(
            session_id=session_info.id,
            user_id=inp.user_id,
            source=inp.source,
            model_id=inp.model_id,
            provider=inp.provider

        )

        # [3] Credits
        if not await _check_credits(llm_config, inp.user_id):
            return CallAgentOutput(
                session_id=session_id_str, run_id="", status=RunStatus.FAILED,
                content=None, events=[], error="Insufficient credits",
            )

        # [4] Run task
        task = await _create_run_task(session_info, inp)
        if task is None:
            return CallAgentOutput(
                session_id=session_id_str, run_id="", status=RunStatus.FAILED,
                content=None, events=[], error="Another task is already running",
            )
        run_id_str = str(task.id)

        # [5] Create agent
        agent = await _create_agent(inp, session_id_str, llm_config)

        # [6] Files
        images, files = await _process_files(inp, session_id_str)

        # [7] Run + collect events
        event_stream = await agent.arun(
            inp.text,
            stream=True,
            stream_events=True,
            run_id=run_id_str,
            images=images or None,
            files=files or None,
            yield_run_output=True,
        )

        async for event in event_stream:
            realtime_event = convert_agent_event_to_realtime(
                event=event,
                run_id=uuid.UUID(run_id_str),
                session_id=session_info.id,
            )
            if realtime_event:
                collected_events.append(realtime_event)

            if isinstance(event, RunCompletedEvent):
                final_status = event.status or RunStatus.COMPLETED
            if isinstance(event, RunOutput):
                run_output = event
                if final_status == RunStatus.FAILED:
                    final_status = RunStatus.COMPLETED

        # [8] Update task status
        await _update_task_status(task.id, final_status)

    except Exception as e:
        logger.error(f"call_agent error: {e}", exc_info=True)
        if run_id_str:
            try:
                await _update_task_status(uuid.UUID(run_id_str), RunStatus.FAILED)
            except Exception:
                pass

        return CallAgentOutput(
            session_id=inp.session_id or "",
            run_id=run_id_str or "",
            status=RunStatus.FAILED,
            content=None,
            events=collected_events,
            error=str(e),
        )

    content = await _extract_content(collected_events, run_output)
    media = _extract_media(collected_events, run_output)

    return CallAgentOutput(
        session_id=session_id_str,
        run_id=run_id_str or "",
        status=final_status,
        content=content,
        events=collected_events,
        media=media,
        run_output=run_output,
    )


async def call_agent_stream(inp: CallAgentInput) -> AsyncIterator[AppEvent]:
    """
    Same as call_agent() but yields AppEvent one-by-one for real-time streaming.

    Each yielded event has the same format that frontend receives via Socket.IO,
    so you can forward them directly to any consumer.
    """
    from ii_agent.realtime.events.app_events import SystemErrorEvent, ErrorCode, EventGroup

    # [0] Ensure user exists
    await _ensure_user_exists(inp.user_id)

    # [1] Session
    container = get_app_container()
    session_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, str(inp.session_id)) if inp.session_id else uuid.uuid4()
    user_uuid = uuid.UUID(inp.user_id)

    async with get_db_session_local() as db:
        session_info = await container.session_service.find_session_by_id(db, session_uuid)
        if not session_info:
            session_info = await container.session_service.create_new_session(
                db, session_uuid, user_uuid, "v1"
            )

    session_id_str = str(session_info.id)
    await _update_session_meta(session_info, inp)

    # [2] LLM Config
    llm_config = await _resolve_llm_config(
        session_id=session_info.id,
        user_id=inp.user_id,
        source=inp.source,
        model_id=inp.model_id,
        provider=inp.provider,
    )

    # [3] Credits
    if not await _check_credits(llm_config, inp.user_id):
        yield SystemErrorEvent(
            group=EventGroup.SYSTEM,
            name="system.error",
            session_id=session_info.id,
            code=ErrorCode.INSUFFICIENT_CREDITS,
            message="Insufficient credits",
        )
        return

    # [4] Run task
    task = await _create_run_task(session_info, inp)
    if task is None:
        yield SystemErrorEvent(
            group=EventGroup.SYSTEM,
            name="system.error",
            session_id=session_info.id,
            code=ErrorCode.CONCURRENT_OPERATION,
            message="Another task is already running",
        )
        return

    run_id_str = str(task.id)

    # [5] Create agent
    agent = await _create_agent(inp, session_id_str, llm_config)

    # [6] Files
    images, files = await _process_files(inp, session_id_str)

    # [7] Run + stream events
    final_status = RunStatus.FAILED
    try:
        event_stream = await agent.arun(
            inp.text,
            stream=True,
            stream_events=True,
            run_id=run_id_str,
            images=images or None,
            files=files or None,
            yield_run_output=False,
        )

        async for event in event_stream:
            realtime_event = convert_agent_event_to_realtime(
                event=event,
                run_id=uuid.UUID(run_id_str),
                session_id=session_info.id,
            )
            if realtime_event:
                yield realtime_event

            if isinstance(event, RunCompletedEvent):
                final_status = event.status or RunStatus.COMPLETED
            if isinstance(event, RunOutput):
                if final_status == RunStatus.FAILED:
                    final_status = RunStatus.COMPLETED

    except Exception as e:
        logger.error(f"call_agent_stream error: {e}", exc_info=True)
        yield SystemErrorEvent(
            group=EventGroup.SYSTEM,
            name="system.error",
            session_id=session_info.id,
            run_id=uuid.UUID(run_id_str),
            code=ErrorCode.UNEXPECTED_ERROR,
            message=str(e),
        )

    # [8] Update task status
    await _update_task_status(task.id, final_status)
