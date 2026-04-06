"""Shared Pydantic models for the AI Backend."""

from pydantic import BaseModel


class Sender(BaseModel):
    platform_id: str
    display_name: str
    internal_user: str | None = None


class ReplyTo(BaseModel):
    channel: str
    recipient: str
    thread_id: str | None = None


class InboundMessage(BaseModel):
    """Payload schema matching II-Claw's forward_to_external_webhook output."""
    user_id: str
    agent_id: str | None = None
    channel: str
    instance_name: str
    platform_message_id: str | None = None
    sender: Sender | None = None
    content_type: str
    text: str | None = None
    media_url: str | None = None
    media_filename: str | None = None
    media_duration_seconds: int | None = None
    is_group: bool = False
    thread_id: str | None = None
    timestamp: str | None = None
    metadata: dict | None = None
    reply_to: ReplyTo | None = None
