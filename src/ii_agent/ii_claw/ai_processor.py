"""AI processing logic — calls the II-Agent backend via call_agent().

Converts inbound II-Claw webhook messages into CallAgentInput,
runs the agent, and returns CallAgentOutput (with content + media).
"""

import re
import logging
from typing import Optional

from ii_agent.agents.types import AgentType
from ii_agent.settings.llm import Provider
from ii_agent.ii_claw.models import InboundMessage
from ii_agent.ii_claw.call_agent import CallAgentInput, CallAgentOutput, call_agent
from ii_agent.ii_claw.custom_agent import process_custom_agent

logger = logging.getLogger(__name__)

# Default agent type when no match is found
DEFAULT_AGENT_TYPE = AgentType.GENERAL

# Map string values to AgentType for fast membership checks from inbound agent_id
_AGENT_TYPE_BY_VALUE = {agent_type.value: agent_type for agent_type in AgentType}

DEFAULT_MODEL_ID = "gpt-5.2"
DEFAULT_PROVIDER = Provider.OPENAI

def detect_agent_type_from_metadata(metadata: Optional[dict]) -> AgentType:
    """Detect the AgentType from an InboundMessage's metadata.

    Priority: thread_name > channel_name.
    Matches by normalizing the name to lowercase with underscores removed/spaces
    collapsed, then comparing against AgentType enum values.

    Examples:
        "Fast Research" / "FastResearch" / "fastresearch" -> AgentType.FAST_RESEARCH
        "Deep Research" -> AgentType.DEEP_RESEARCH
        "general" -> AgentType.GENERAL

    Returns DEFAULT_AGENT_TYPE if no match is found.
    """
    if not metadata:
        return DEFAULT_AGENT_TYPE

    # Priority: thread_name first, then channel_name
    name = metadata.get("thread_name") or metadata.get("channel_name") or metadata.get("chat_title")
    if not name:
        return DEFAULT_AGENT_TYPE

    # Normalize: "Fast Research" -> "fast_research", "FastResearch" -> "fast_research"
    # 1. Insert underscore before uppercase letters (for camelCase/PascalCase)
    normalized = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
    # 2. Replace spaces/hyphens with underscores
    normalized = re.sub(r"[\s\-]+", "_", normalized)
    # 3. Lowercase and strip
    normalized = normalized.lower().strip("_")

    # Try to match against AgentType values
    for agent_type in AgentType:
        if normalized == agent_type.value:
            return agent_type

    return DEFAULT_AGENT_TYPE


def detect_session_id_from_metadata(metadata: Optional[dict]) -> Optional[str]:
    """Derive a stable session ID from an InboundMessage's metadata.

    Priority: thread_id > channel_id
    Messages in the same thread/channel will share one agent session.

    Returns None if no usable identifier is found (creates a new session).
    """
    if not metadata:
        return None
    return metadata.get("thread_id") or metadata.get("message_thread_id") or metadata.get("channel_id") or metadata.get("chat_id") or None


def _build_agent_text(msg: InboundMessage) -> str:
    """Build the text prompt to send to the agent from an inbound message."""
    parts: list[str] = []

    if msg.text:
        parts.append(msg.text)

    if msg.content_type == "image" and msg.media_url:
        parts.append(f"[Image: {msg.media_url}]")
    elif msg.content_type == "video" and msg.media_url:
        parts.append(f"[Video: {msg.media_url}]")
    elif msg.content_type == "audio" and msg.media_url:
        parts.append(f"[Audio: {msg.media_url}]")
    elif msg.content_type == "voice" and msg.media_url:
        parts.append(f"[Voice message ({msg.media_duration_seconds or 0}s): {msg.media_url}]")
    elif msg.content_type == "file" and msg.media_url:
        parts.append(f"[File '{msg.media_filename or 'unknown'}': {msg.media_url}]")
    elif msg.content_type == "location":
        parts.append("[Location shared]")

    return "\n".join(parts) if parts else "(empty message)"


async def process_inbound_message(msg: InboundMessage) -> CallAgentOutput:
    """Process an inbound channel message and return CallAgentOutput.

    Args:
        msg: The parsed inbound message from II-Claw webhook.

    Returns:
        CallAgentOutput with content (text) and media (images, videos, audio, files).
        The caller (_process_and_reply) sends these via send_to_channel.
    """
    input_text = _build_agent_text(msg)
    user_id = msg.user_id if msg.user_id else "cli-user"

    # --- Resolve agent_id: built-in AgentType first, custom agent second ---
    raw_agent_id = msg.agent_id
    agent_id = raw_agent_id.strip().lower() if raw_agent_id else None
    agent_type_from_agent_id = _AGENT_TYPE_BY_VALUE.get(agent_id) if agent_id else None
    custom_overrides = None

    if agent_id and agent_type_from_agent_id is None:
        custom_overrides = await process_custom_agent(
            agent_id=agent_id,
            user_id=user_id,
        )
        if custom_overrides is None:
            logger.warning(
                "agent_id=%s not found for user=%s, falling back to default",
                agent_id,
                user_id,
            )

    # --- Build CallAgentInput ---
    if custom_overrides is not None:
        inp = CallAgentInput(
            user_id=user_id,
            text=input_text,
            model_id=custom_overrides.model_id,
            provider=custom_overrides.provider or DEFAULT_PROVIDER,
            source="system",
            agent_type=AgentType.CUSTOM,
            session_id=detect_session_id_from_metadata(msg.metadata),
            custom_system_prompt=custom_overrides.custom_system_prompt,
            tool_args=custom_overrides.tool_args or {},
            skill_mode=custom_overrides.skill_mode,
            connector_mode=custom_overrides.connector_mode,
        )
    else:
        inp = CallAgentInput(
            user_id=user_id,
            text=input_text,
            model_id=DEFAULT_MODEL_ID,
            provider=DEFAULT_PROVIDER,
            source="system",
            agent_type=agent_type_from_agent_id or detect_agent_type_from_metadata(msg.metadata),
            session_id=detect_session_id_from_metadata(msg.metadata),
        )

    output = await call_agent(inp)

    if output.error:
        logger.error("Agent error: %s", output.error)
        output.content = f"Sorry, something went wrong: {output.error}"
    elif not output.content:
        output.content = "I processed your request but have no response to share."

    logger.info("AI response: %s", (output.content or "")[:100])

    return output
