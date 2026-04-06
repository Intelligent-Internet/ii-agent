"""Layer 3: Webhook receiver — handles inbound messages forwarded by II-Claw."""

import asyncio
import hashlib
import hmac
import logging

from ii_agent.ii_claw.api.client import proxy_get, proxy_post, proxy_put, proxy_delete, send_to_user_channel

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from typing import Any

from pydantic import BaseModel

from ii_agent.auth.dependencies import CurrentUser
from ii_agent.core.config.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ii-claw", tags=["ii-claw"])

# ===========================================================================
# Webhook
# ===========================================================================
_settings = get_settings()
WEBHOOK_SECRET = _settings.ii_claw_webhook_secret

# ---------------------------------------------------------------------------
# HMAC verification
# ---------------------------------------------------------------------------

def verify_signature(body: bytes, signature: str | None) -> bool:
    """Verify HMAC-SHA256 signature from II-Claw."""
    if not WEBHOOK_SECRET:
        return True  # No secret configured, skip verification
    if not signature:
        return False
    expected = hmac.new(
        WEBHOOK_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)


# ---------------------------------------------------------------------------
# Webhook endpoint
# ---------------------------------------------------------------------------

@router.post("/webhook/inbound")
async def receive_inbound(
    request: Request,
    background_tasks: BackgroundTasks,
    x_webhook_signature: str | None = Header(None),
):
    """Receive an inbound message forwarded from II-Claw.

    Flow:
      1. Return {"immediate_reply": "Processing...", "async_processing": true} immediately
      2. Background task: call_agent → send text content via send_to_user_channel → send media
    """
    body = await request.body()

    # Verify HMAC signature
    if not verify_signature(body, x_webhook_signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    import json
    from ii_agent.ii_claw.models import InboundMessage
    payload = InboundMessage(**json.loads(body))

    # logger.info(
    #     "Inbound [%s] from %s (%s): content_type=%s",
    #     payload.channel,
    #     payload.sender.display_name,
    #     payload.sender.platform_id,
    #     payload.content_type,
    # )

    # Fire background processing — response will be sent via send_to_user_channel
    background_tasks.add_task(_process_and_reply, payload)

    return {"immediate_reply": "Processing...", "async_processing": True}


async def _process_and_reply(payload):
    """Background: run AI agent, then send results back via II-Claw channel."""
    from ii_agent.ii_claw.ai_processor import process_inbound_message

    user_id = payload.user_id if payload.user_id else "unknown_user"
    channel = payload.instance_name if payload.instance_name else payload.channel
    recipient = payload.reply_to.recipient if payload.reply_to else payload.sender.platform_id
    thread_id = payload.reply_to.thread_id if payload.reply_to else payload.thread_id

    try:
        output = await process_inbound_message(payload)

        # Step 1: Send text content
        if output.content:
            await send_to_user_channel(
                user_id, channel, recipient,
                text=output.content,
                thread_id=thread_id,
            )

        # Step 2: Send media (images, videos, audio, files)
        for img in output.media.images:
            await send_to_user_channel(
                user_id, channel, recipient,
                image_url=img.get("url"),
                caption=img.get("caption"),
                thread_id=thread_id,
            )

        for vid in output.media.videos:
            await send_to_user_channel(
                user_id, channel, recipient,
                video_url=vid.get("url"),
                caption=vid.get("caption"),
                thread_id=thread_id,
            )

        for aud in output.media.audio:
            await send_to_user_channel(
                user_id, channel, recipient,
                voice_url=aud.get("url"),
                caption=aud.get("caption"),
                thread_id=thread_id,
            )

        for f in output.media.files:
            await send_to_user_channel(
                user_id, channel, recipient,
                file_url=f.url,
                filename=f.name,
                caption=f.name,
                thread_id=thread_id,
            )

    except Exception as e:
        logger.error("Background processing failed for %s/%s: %s", channel, recipient, e, exc_info=True)
        # Try to notify user of the error
        try:
            await send_to_user_channel(
                user_id, channel, recipient,
                text=f"Sorry, an error occurred while processing your message: {e}",
                thread_id=thread_id,
            )
        except Exception:
            logger.error("Failed to send error message to channel")

# ===========================================================================
# Channels
# ===========================================================================

# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class UserChannelConfigureRequest(BaseModel):
    """Configure a user-scoped channel instance.

    fields can have mixed types (str, int, bool, list)
    matching the actual channel config schema.

    Example payload:
        {
            "channel_type": "discord",
            "fields": {
                "bot_token_env": "actual-discord-bot-token-here",
                "allowed_guilds": ["123456"],
                "allowed_users": [],
                "intents": 37376,
                "ignore_bots": true
            }
        }
    """
    channel_type: str
    instance_name: str | None = None  # Display name, defaults to instance_name_id
    fields: dict[str, Any]
    agent_id: str | None = None  # Optional agent scoping for this channel instance
    register_webhook: bool = True


class UserChannelUpdateRequest(BaseModel):
    """Update an existing user-scoped channel instance.

    PUT /api/users/{user_id}/channels/{instance_name_id}

    All fields are optional — only provided fields are updated.
    Fields are merged into existing config (not replaced).

    Example payload:
        {
            "instance_name": "New Display Name",
            "enabled": false,
            "fields": {"allowed_guilds": ["456"]}
        }
    """
    instance_name: str | None = None  # Rename display name
    enabled: bool | None = None
    fields: dict[str, Any] | None = None
    agent_id: str | None = None  # Optional agent scoping for this channel instance


class UserChannelSendRequest(BaseModel):
    """Send a message via a user-scoped channel instance."""
    recipient: str
    message: str | None = None
    image_url: str | None = None
    file_url: str | None = None
    filename: str | None = None
    voice_url: str | None = None
    video_url: str | None = None
    caption: str | None = None
    thread_id: str | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

async def _try_ii_claw_get(path: str):
    """Try GET from II-Claw, return (data, status_code, is_live)."""
    try:
        resp = await proxy_get(path)
        return resp.json(), resp.status_code, True
    except Exception as e:
        logger.debug("II-Claw unreachable for %s: %s", path, e)
        return None, None, False

@router.get("/users/{user_id}/channels")
async def list_user_channels(
    user_id: str,
    current_user: CurrentUser,
    channel_type: str | None = None,
):
    """List all channel instances for a user.

    Optional query param ?channel_type=discord to filter by type.
    Proxies to GET /api/users/{user_id}/channels
    """
    if str(current_user.id) != user_id:
        raise HTTPException(status_code=403, detail="Cannot list channels for another user")

    params = {"channel_type": channel_type} if channel_type else None
    try:
        data, status, live = await _try_ii_claw_get(f"/api/users/{user_id}/channels")
        if live:
            channels = data.get("channels", []) if isinstance(data, dict) else []
            if channel_type:
                channels = [ch for ch in channels if ch.get("channel_type") == channel_type]
            return {"source": "II-Claw", "channels": channels}
        return {"source": "II-Claw", "channels": []}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"II-Claw unreachable: {e}")


@router.post("/users/{user_id}/channels/{instance_name_id}/configure")
async def configure_user_channel(
    user_id: str,
    instance_name_id: str,
    req: UserChannelConfigureRequest,
    current_user: CurrentUser,
):
    """Configure a user-scoped channel instance.

    POST /ii_claw/users/{user_id}/channels/{instance_name_id}/configure

    - instance_name_id (path): the slug ID (e.g. "my_agent_1")
    - instance_name (body): optional display name, defaults to instance_name_id

    1. Validates user_id matches the authenticated user.
    2. Converts mixed-type fields to string format for Rust compatibility.
    3. Proxies to POST /api/users/{user_id}/channels/{instance_name_id}/configure.
    """
    # Validate user ownership
    if str(current_user.id) != user_id:
        raise HTTPException(status_code=403, detail="Cannot configure channels for another user")

    # Convert mixed-type fields to strings for Rust compatibility
    string_fields: dict[str, str] = {}
    for key, value in req.fields.items():
        if isinstance(value, list):
            string_fields[key] = ", ".join(str(v) for v in value)
        elif isinstance(value, bool):
            string_fields[key] = str(value).lower()
        else:
            string_fields[key] = str(value)

    channel_type = req.channel_type.lower()

    # Configure the channel instance
    payload: dict[str, Any] = {
        "channel_type": channel_type,
        "fields": string_fields,
    }
    if req.instance_name:
        payload["instance_name"] = req.instance_name
    if req.agent_id:
        payload["agent_id"] = req.agent_id

    try:
        resp = await proxy_post(
            f"/api/users/{user_id}/channels/{instance_name_id}/configure",
            json=payload,
        )
        result = resp.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"II-Claw unreachable: {e}")

    return {
        "source": "II-Claw",
        "result": result,
        "status": resp.status_code,
        "webhook": "registered",
        "channel_type": req.channel_type,
        "instance_name_id": instance_name_id,
        "user_id": user_id,
    }


@router.put("/users/{user_id}/channels/{instance_name_id}")
async def update_user_channel(
    user_id: str,
    instance_name_id: str,
    req: UserChannelUpdateRequest,
    current_user: CurrentUser,
):
    """Update an existing user-scoped channel instance.

    PUT /ii_claw/users/{user_id}/channels/{instance_name_id}

    Proxies to PUT /api/users/{user_id}/channels/{instance_name_id}.
    - instance_name_id (path): the immutable slug ID (e.g. "my_agent_1")
    - instance_name (body): optional new display name
    Only provided fields are updated; fields dict is merged into existing config.
    """
    if str(current_user.id) != user_id:
        raise HTTPException(status_code=403, detail="Cannot update channels for another user")

    # Build payload with only provided fields
    payload: dict[str, Any] = {}
    if req.instance_name is not None:
        payload["instance_name"] = req.instance_name
    if req.enabled is not None:
        payload["enabled"] = req.enabled
    if req.agent_id is not None:
        payload["agent_id"] = req.agent_id
    if req.fields is not None:
        # Convert mixed-type fields to strings for Rust compatibility
        string_fields: dict[str, str] = {}
        for key, value in req.fields.items():
            if isinstance(value, list):
                string_fields[key] = ", ".join(str(v) for v in value)
            elif isinstance(value, bool):
                string_fields[key] = str(value).lower()
            else:
                string_fields[key] = str(value)
        payload["fields"] = string_fields

    try:
        resp = await proxy_put(
            f"/api/users/{user_id}/channels/{instance_name_id}",
            json=payload,
        )
        result = resp.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"II-Claw unreachable: {e}")

    return {
        "source": "II-Claw",
        "result": result,
        "status": resp.status_code,
        "instance_name_id": instance_name_id,
        "user_id": user_id,
    }


@router.delete("/users/{user_id}/channels/{instance_name_id}")
async def remove_user_channel(
    user_id: str,
    instance_name_id: str,
    current_user: CurrentUser,
):
    """Remove a user-scoped channel instance.

    Proxies to DELETE /api/users/{user_id}/channels/{instance_name_id}
    """
    if str(current_user.id) != user_id:
        raise HTTPException(status_code=403, detail="Cannot remove channels for another user")

    try:
        resp = await proxy_delete(f"/api/users/{user_id}/channels/{instance_name_id}")
        result = resp.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"II-Claw unreachable: {e}")

    return {
        "source": "II-Claw",
        "result": result,
        "status": resp.status_code,
    }


@router.post("/users/{user_id}/channels/{instance_name_id}/send")
async def send_to_user_channel_endpoint(
    user_id: str,
    instance_name_id: str,
    req: UserChannelSendRequest,
    current_user: CurrentUser,
):
    """Send a message via a user-scoped channel instance.

    Proxies to POST /api/users/{user_id}/channels/{instance_name_id}/send
    """
    if str(current_user.id) != user_id:
        raise HTTPException(status_code=403, detail="Cannot send via channels for another user")

    try:
        result = await send_to_user_channel(
            user_id,
            instance_name_id,
            req.recipient,
            text=req.message,
            image_url=req.image_url,
            file_url=req.file_url,
            filename=req.filename,
            voice_url=req.voice_url,
            video_url=req.video_url,
            caption=req.caption,
            thread_id=req.thread_id,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"II-Claw unreachable: {e}")

    return {"source": "II-Claw", "result": result}


@router.post("/users/{user_id}/channels/reload")
async def reload_user_channels(
    user_id: str,
    current_user: CurrentUser,
):
    """Trigger hot-reload of all channel instances for a user.

    Proxies to POST /api/users/{user_id}/channels/reload
    """
    if str(current_user.id) != user_id:
        raise HTTPException(status_code=403, detail="Cannot reload channels for another user")

    try:
        resp = await proxy_post(f"/api/users/{user_id}/channels/reload")
        return {"source": "II-Claw", "result": resp.json(), "status": resp.status_code}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"II-Claw unreachable: {e}")


# ===========================================================================
# Cron Jobs
# ===========================================================================

# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class CronJobCreateRequest(BaseModel):
    """Create a new cron job.

    Example payload:
        {
            "name": "standup-reminder",
            "label": "notifications",
            "schedule": {"type": "cron", "expr": "0 9 * * 1-5", "tz": "America/New_York"},
            "action": {"type": "channel_message", "channel": "slack", "recipient": "#general", "message": "Hey!"},
            "one_shot": false,
            "channel_type": {"platform": "slack"},
            "metadata": {"team": "eng"}
        }
    """
    name: str
    label: str | None = None
    one_shot: bool = False
    schedule: dict[str, Any]
    action: dict[str, Any]
    channel_type: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class CronJobToggleRequest(BaseModel):
    """Toggle a cron job enabled/disabled."""
    enabled: bool


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/users/{user_id}/cron/jobs")
async def create_cron_job(
    user_id: str,
    req: CronJobCreateRequest,
    current_user: CurrentUser,
):
    """Create a new cron job for a user.

    Proxies to POST /api/users/{user_id}/cron/jobs
    """
    if str(current_user.id) != user_id:
        raise HTTPException(status_code=403, detail="Cannot create cron jobs for another user")

    payload: dict[str, Any] = {
        "name": req.name,
        "schedule": req.schedule,
        "action": req.action,
        "one_shot": req.one_shot,
    }
    if req.label is not None:
        payload["label"] = req.label
    if req.channel_type is not None:
        payload["channel_type"] = req.channel_type
    if req.metadata is not None:
        payload["metadata"] = req.metadata

    try:
        resp = await proxy_post(f"/api/users/{user_id}/cron/jobs", json=payload)
        result = resp.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"II-Claw unreachable: {e}")

    return {"source": "II-Claw", "result": result, "status": resp.status_code}


@router.get("/users/{user_id}/cron/jobs")
async def list_cron_jobs(
    user_id: str,
    current_user: CurrentUser,
    label: str | None = None,
):
    """List all cron jobs for a user.

    Optional query param ?label=notifications to filter.
    Proxies to GET /api/users/{user_id}/cron/jobs
    """
    if str(current_user.id) != user_id:
        raise HTTPException(status_code=403, detail="Cannot list cron jobs for another user")

    params = {"label": label} if label else None
    try:
        data, status, live = await _try_ii_claw_get(f"/api/users/{user_id}/cron/jobs")
        if live:
            jobs = data.get("jobs", []) if isinstance(data, dict) else []
            if label:
                jobs = [j for j in jobs if j.get("label") == label]
            return {"source": "II-Claw", "jobs": jobs, "total": len(jobs)}
        return {"source": "II-Claw", "jobs": [], "total": 0}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"II-Claw unreachable: {e}")


@router.delete("/users/{user_id}/cron/jobs/{job_id}")
async def delete_cron_job(
    user_id: str,
    job_id: str,
    current_user: CurrentUser,
):
    """Delete a cron job.

    Proxies to DELETE /api/users/{user_id}/cron/jobs/{job_id}
    """
    if str(current_user.id) != user_id:
        raise HTTPException(status_code=403, detail="Cannot delete cron jobs for another user")

    try:
        resp = await proxy_delete(f"/api/users/{user_id}/cron/jobs/{job_id}")
        result = resp.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"II-Claw unreachable: {e}")

    return {"source": "II-Claw", "result": result, "status": resp.status_code}


@router.put("/users/{user_id}/cron/jobs/{job_id}/enable")
async def toggle_cron_job(
    user_id: str,
    job_id: str,
    req: CronJobToggleRequest,
    current_user: CurrentUser,
):
    """Toggle a cron job enabled/disabled.

    Proxies to PUT /api/users/{user_id}/cron/jobs/{job_id}/enable
    """
    if str(current_user.id) != user_id:
        raise HTTPException(status_code=403, detail="Cannot toggle cron jobs for another user")

    try:
        resp = await proxy_put(
            f"/api/users/{user_id}/cron/jobs/{job_id}/enable",
            json={"enabled": req.enabled},
        )
        result = resp.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"II-Claw unreachable: {e}")

    return {"source": "II-Claw", "result": result, "status": resp.status_code}


class CronJobUpdateRequest(BaseModel):
    """Update an existing cron job (full overwrite).

    Same fields as create, plus `enabled`.
    """
    name: str
    label: str | None = None
    enabled: bool = True
    one_shot: bool = False
    schedule: dict[str, Any]
    action: dict[str, Any]
    channel_type: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


@router.put("/users/{user_id}/cron/jobs/{job_id}")
async def update_cron_job(
    user_id: str,
    job_id: str,
    req: CronJobUpdateRequest,
    current_user: CurrentUser,
):
    """Update an existing cron job (full overwrite).

    Proxies to PUT /api/users/{user_id}/cron/jobs/{job_id}
    """
    if str(current_user.id) != user_id:
        raise HTTPException(status_code=403, detail="Cannot update cron jobs for another user")

    payload: dict[str, Any] = {
        "name": req.name,
        "enabled": req.enabled,
        "one_shot": req.one_shot,
        "schedule": req.schedule,
        "action": req.action,
    }
    if req.label is not None:
        payload["label"] = req.label
    if req.channel_type is not None:
        payload["channel_type"] = req.channel_type
    if req.metadata is not None:
        payload["metadata"] = req.metadata

    try:
        resp = await proxy_put(f"/api/users/{user_id}/cron/jobs/{job_id}", json=payload)
        result = resp.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"II-Claw unreachable: {e}")

    return {"source": "II-Claw", "result": result, "status": resp.status_code}


@router.post("/users/{user_id}/cron/jobs/{job_id}/test")
async def test_cron_job(
    user_id: str,
    job_id: str,
    current_user: CurrentUser,
):
    """Test-trigger a cron job immediately.

    Proxies to POST /api/users/{user_id}/cron/jobs/{job_id}/test
    """
    if str(current_user.id) != user_id:
        raise HTTPException(status_code=403, detail="Cannot test cron jobs for another user")

    try:
        resp = await proxy_post(f"/api/users/{user_id}/cron/jobs/{job_id}/test")
        result = resp.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"II-Claw unreachable: {e}")

    return {"source": "II-Claw", "result": result, "status": resp.status_code}


@router.get("/users/{user_id}/cron/jobs/{job_id}/history")
async def get_cron_job_history(
    user_id: str,
    job_id: str,
    current_user: CurrentUser,
    limit: int = 50,
):
    """Get run history for a specific cron job.

    Proxies to GET /api/users/{user_id}/cron/jobs/{job_id}/history
    """
    if str(current_user.id) != user_id:
        raise HTTPException(status_code=403, detail="Cannot view cron job history for another user")

    try:
        data, status, live = await _try_ii_claw_get(
            f"/api/users/{user_id}/cron/jobs/{job_id}/history"
        )
        if live:
            runs = data.get("runs", []) if isinstance(data, dict) else []
            return {"source": "II-Claw", "runs": runs[:limit], "total": len(runs)}
        return {"source": "II-Claw", "runs": [], "total": 0}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"II-Claw unreachable: {e}")


@router.get("/users/{user_id}/cron/history")
async def get_all_cron_history(
    user_id: str,
    current_user: CurrentUser,
    limit: int = 50,
):
    """Get all cron job run history for a user.

    Proxies to GET /api/users/{user_id}/cron/history
    """
    if str(current_user.id) != user_id:
        raise HTTPException(status_code=403, detail="Cannot view cron history for another user")

    try:
        data, status, live = await _try_ii_claw_get(f"/api/users/{user_id}/cron/history")
        if live:
            runs = data.get("runs", []) if isinstance(data, dict) else []
            return {"source": "II-Claw", "runs": runs[:limit], "total": len(runs)}
        return {"source": "II-Claw", "runs": [], "total": 0}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"II-Claw unreachable: {e}")
