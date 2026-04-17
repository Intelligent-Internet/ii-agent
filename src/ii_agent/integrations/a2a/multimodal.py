"""Multimodal Part translation between ii-agent media types and A2A Parts.

Converts :class:`~ii_agent.files.media.media.Image`,
:class:`~ii_agent.files.media.media.File`, and related dicts into A2A
:class:`~a2a.types.Part` objects (``TextPart``, ``FilePart``, ``DataPart``).

This module covers both directions:

* **Inbound** (user → backend): extract A2A Parts from ii-agent message dicts
  so the adapter server can forward multimodal content to CLI backends.
* **Outbound** (backend → client): convert event content that references
  images/files into ``FilePart`` objects for A2A artifact events.
"""

from __future__ import annotations

import base64
from typing import Any, Optional, Sequence

from a2a.types import (
    DataPart,
    FilePart,
    FileWithBytes,
    FileWithUri,
    Part,
    TextPart,
)

from ii_agent.integrations.a2a._logger import logger


# ---------------------------------------------------------------------------
# Inbound: ii-agent message dicts → A2A Parts
# ---------------------------------------------------------------------------


def extract_user_content(
    messages: list[dict[str, Any]],
) -> tuple[str, list[Part]]:
    """Extract text prompt **and** multimodal A2A Parts from the latest user message.

    Returns ``(text_prompt, parts)`` where *parts* contains at least a
    ``TextPart`` for the text body plus any ``FilePart`` objects for images
    and files attached to the message.

    The text prompt is returned separately for backward-compatible callers
    that only support text.
    """
    text_prompt = ""
    parts: list[Part] = []

    for msg in reversed(messages):
        role = str(msg.get("role") or "").lower()
        if role != "user":
            continue

        text_prompt = _extract_text(msg)

        # Collect image parts
        for img_dict in msg.get("images") or []:
            part = _image_dict_to_part(img_dict)
            if part is not None:
                parts.append(part)

        # Collect file parts
        for file_dict in msg.get("files") or []:
            part = _file_dict_to_part(file_dict)
            if part is not None:
                parts.append(part)

        # Collect audio parts
        for aud_dict in msg.get("audio") or []:
            part = _audio_dict_to_part(aud_dict)
            if part is not None:
                parts.append(part)

        # Collect video parts
        for vid_dict in msg.get("videos") or []:
            part = _video_dict_to_part(vid_dict)
            if part is not None:
                parts.append(part)

        # Prepend the text as the first Part
        if text_prompt:
            parts.insert(0, Part(root=TextPart(text=text_prompt)))

        break  # Only process the latest user message

    _non_text = sum(1 for p in parts if not isinstance(p.root, TextPart))
    logger.debug(
        f"[a2a:multimodal] extract_user_content: "
        f"messages={len(messages)}, prompt_chars={len(text_prompt)}, "
        f"parts={len(parts)} (text={len(parts) - _non_text}, media={_non_text})"
    )
    return text_prompt, parts


def extract_historical_image_parts(messages: list[dict[str, Any]]) -> list[Part]:
    """Collect image Parts from all user messages *except* the last one.

    ``extract_user_content`` handles images from the latest user message.
    This function picks up images from *prior* user turns so the LLM can
    still see them on follow-up questions without re-upload.

    Returns a (possibly empty) list of ``FilePart`` objects.
    """
    # Identify the index of the last non-system user message.
    last_user_idx = -1
    for i in range(len(messages) - 1, -1, -1):
        role = str(messages[i].get("role") or "").lower()
        if role == "user":
            last_user_idx = i
            break

    parts: list[Part] = []
    seen_ids: set[str] = set()

    for idx, msg in enumerate(messages):
        if idx == last_user_idx:
            continue  # handled by extract_user_content
        role = str(msg.get("role") or "").lower()
        if role != "user":
            continue

        for img_dict in msg.get("images") or []:
            img_id = img_dict.get("id") or ""
            if img_id and img_id in seen_ids:
                continue
            part = _image_dict_to_part(img_dict)
            if part is not None:
                parts.append(part)
                if img_id:
                    seen_ids.add(img_id)

    if parts:
        logger.info(
            f"[a2a:multimodal] extract_historical_image_parts: "
            f"found {len(parts)} image(s) from prior user messages"
        )
    return parts


def build_conversation_context(messages: list[dict[str, Any]]) -> str:
    """Build a structured text representation of prior conversation turns.

    Formats all messages *before* the last user message into a
    ``<conversation_history>`` block that preserves:

    * **Role fidelity** – user, assistant, and tool messages keep distinct labels.
    * **Thinking/reasoning blocks** – wrapped in ``<thinking>`` tags.
    * **Encrypted reasoning** – noted when ``redacted_reasoning_content`` present.
    * **Tool call structure** – tool name, arguments, and linked results.
    * **Tool errors** – failed tool calls labeled ``[Tool Error]`` vs ``[Tool Result]``.
    * **Session summaries** – compressed history labeled ``[Session Summary]``.
    * **Multimodal references** – images, files, audio, video attachments noted inline.
    * **Assistant media outputs** – generated images/files/audio/video noted inline.
    * **Citations** – source references from assistant messages.

    System/developer messages are excluded (forwarded separately as the
    system prompt).

    Returns an empty string when there is no meaningful prior history.
    """
    if not messages:
        return ""

    # Identify prior turns: everything except system/developer messages and
    # the final user message (which becomes the current prompt).
    non_system = [
        m for m in messages if str(m.get("role") or "").lower() not in ("system", "developer")
    ]
    # The last non-system message should be the current user prompt — exclude it.
    if not non_system:
        return ""
    prior = non_system[:-1]
    if not prior:
        return ""

    # Compute per-role breakdown of prior messages for observability.
    _role_counts: dict[str, int] = {}
    _summary_count = 0
    _tool_call_count = 0
    for msg in prior:
        _r = str(msg.get("role") or "unknown").lower()
        _role_counts[_r] = _role_counts.get(_r, 0) + 1
        if msg.get("is_summary"):
            _summary_count += 1
        if msg.get("tool_calls"):
            _tool_call_count += len(msg["tool_calls"])

    lines: list[str] = []
    for msg in prior:
        formatted = _format_history_message(msg)
        if formatted:
            lines.append(formatted)

    if not lines:
        logger.debug(
            f"[a2a:multimodal] build_conversation_context: "
            f"no formattable history (total_messages={len(messages)}, "
            f"prior={len(prior)}, roles={_role_counts})"
        )
        return ""

    result = "<conversation_history>\n" + "\n\n".join(lines) + "\n</conversation_history>\n\n"
    logger.info(
        f"[a2a:multimodal] build_conversation_context: "
        f"total_messages={len(messages)}, prior_turns={len(prior)}, "
        f"formatted_blocks={len(lines)}, history_chars={len(result)}, "
        f"roles={_role_counts}, summaries={_summary_count}, "
        f"tool_calls={_tool_call_count}"
    )
    return result


def _format_history_message(msg: dict[str, Any]) -> str:
    """Format a single message dict for inclusion in conversation history.

    Handles user, assistant, and tool roles with appropriate structure,
    including summary messages, encrypted reasoning, media outputs,
    tool errors, audio/video attachments, and citations.
    """
    role = str(msg.get("role") or "unknown").lower()
    is_summary = bool(msg.get("is_summary"))
    parts: list[str] = []

    if is_summary:
        # Compressed session summaries get a distinct label regardless of role
        text = _extract_text(msg)
        if text:
            parts.append(f"[Session Summary]: {text}")
        return "\n".join(parts)

    if role == "user":
        text = _extract_text(msg)
        if text:
            parts.append(f"[User]: {text}")
        # Note any attached media (images, files, audio, videos)
        _append_media_references(msg, parts, indent="  ")

    elif role == "assistant":
        # Reasoning / thinking content
        reasoning = msg.get("reasoning_content") or ""
        if reasoning:
            parts.append(f"[Assistant Thinking]:\n<thinking>\n{reasoning}\n</thinking>")

        # Redacted (encrypted) reasoning — note its presence
        redacted = msg.get("redacted_reasoning_content") or ""
        if redacted:
            parts.append("[Assistant had encrypted reasoning (redacted)]")

        # Tool calls made by the assistant
        tool_calls = msg.get("tool_calls") or []
        if tool_calls:
            for tc in tool_calls:
                tc_name = tc.get("function", {}).get("name") or tc.get("name") or "unknown_tool"
                tc_args = tc.get("function", {}).get("arguments") or tc.get("arguments") or ""
                if isinstance(tc_args, dict):
                    import json as _json

                    tc_args = _json.dumps(tc_args, ensure_ascii=False)
                # Truncate very long arguments to keep history manageable
                if len(tc_args) > 2000:
                    tc_args = tc_args[:2000] + "... (truncated)"
                parts.append(f"[Assistant Tool Call]: {tc_name}({tc_args})")

        # Text content
        text = _extract_text(msg)
        if text:
            parts.append(f"[Assistant]: {text}")

        # Media outputs generated by the assistant
        _append_output_references(msg, parts, indent="  ")
        # Attached media on assistant messages (images, files, audio, videos)
        _append_media_references(msg, parts, indent="  ")

        # Citations
        citations = msg.get("citations")
        if citations:
            _append_citations(citations, parts, indent="  ")

    elif role == "tool":
        tool_name = msg.get("tool_name") or ""
        is_error = bool(msg.get("tool_call_error"))
        text = _extract_text(msg)

        if is_error:
            label_parts = ["[Tool Error"]
        else:
            label_parts = ["[Tool Result"]
        if tool_name:
            label_parts.append(f" ({tool_name})")
        label_parts.append("]:")
        label = "".join(label_parts)
        if text:
            # Truncate very long tool results
            if len(text) > 3000:
                text = text[:3000] + "\n... (truncated)"
            parts.append(f"{label} {text}")

    else:
        # Fallback for any other role
        text = _extract_text(msg)
        if text:
            parts.append(f"[{role.title()}]: {text}")

    return "\n".join(parts)


def _append_media_references(msg: dict[str, Any], parts: list[str], indent: str = "") -> None:
    """Append inline references for images, files, audio, and videos attached to a message."""
    for img in msg.get("images") or []:
        url = img.get("url") or img.get("filepath") or ""
        alt = img.get("alt_text") or img.get("id") or "image"
        if url:
            parts.append(f"{indent}[Attached image: {alt} — {url}]")
        else:
            parts.append(f"{indent}[Attached image: {alt}]")

    for fd in msg.get("files") or []:
        url = fd.get("url") or fd.get("filepath") or ""
        name = fd.get("filename") or fd.get("name") or "file"
        if url:
            parts.append(f"{indent}[Attached file: {name} — {url}]")
        else:
            parts.append(f"{indent}[Attached file: {name}]")

    for aud in msg.get("audio") or []:
        transcript = aud.get("transcript") or ""
        aud_id = aud.get("id") or "audio"
        label = f"[Attached audio: {aud_id}]"
        if transcript:
            label = f"[Attached audio: {aud_id} — transcript: {transcript}]"
        parts.append(f"{indent}{label}")

    for vid in msg.get("videos") or []:
        url = vid.get("url") or vid.get("filepath") or ""
        vid_id = vid.get("id") or "video"
        if url:
            parts.append(f"{indent}[Attached video: {vid_id} — {url}]")
        else:
            parts.append(f"{indent}[Attached video: {vid_id}]")


def _append_output_references(msg: dict[str, Any], parts: list[str], indent: str = "") -> None:
    """Append inline references for media outputs generated by the assistant."""
    if msg.get("image_output"):
        out = msg["image_output"]
        url = out.get("url") or out.get("filepath") or ""
        alt = out.get("alt_text") or out.get("id") or "generated image"
        if url:
            parts.append(f"{indent}[Generated image: {alt} — {url}]")
        else:
            parts.append(f"{indent}[Generated image: {alt}]")

    if msg.get("file_output"):
        out = msg["file_output"]
        url = out.get("url") or out.get("filepath") or ""
        name = out.get("filename") or out.get("name") or "generated file"
        if url:
            parts.append(f"{indent}[Generated file: {name} — {url}]")
        else:
            parts.append(f"{indent}[Generated file: {name}]")

    if msg.get("audio_output"):
        out = msg["audio_output"]
        transcript = out.get("transcript") or ""
        aud_id = out.get("id") or "generated audio"
        if transcript:
            parts.append(f"{indent}[Generated audio: {aud_id} — transcript: {transcript}]")
        else:
            parts.append(f"{indent}[Generated audio: {aud_id}]")

    if msg.get("video_output"):
        out = msg["video_output"]
        url = out.get("url") or out.get("filepath") or ""
        vid_id = out.get("id") or "generated video"
        if url:
            parts.append(f"{indent}[Generated video: {vid_id} — {url}]")
        else:
            parts.append(f"{indent}[Generated video: {vid_id}]")


def _append_citations(citations: Any, parts: list[str], indent: str = "") -> None:
    """Append citation references from an assistant message."""
    if isinstance(citations, dict):
        items = citations.get("citations") or citations.get("items") or []
        if isinstance(items, list):
            for cite in items:
                if isinstance(cite, dict):
                    title = cite.get("title") or cite.get("url") or "source"
                    url = cite.get("url") or ""
                    if url:
                        parts.append(f"{indent}[Citation: {title} — {url}]")
                    else:
                        parts.append(f"{indent}[Citation: {title}]")


# ---------------------------------------------------------------------------
# Outbound: event content dicts → A2A Parts
# ---------------------------------------------------------------------------


def content_to_parts(content: Any) -> list[Part]:
    """Convert an event ``content`` dict into a list of A2A Parts.

    Handles:
    * Plain text (``str`` or ``content["text"]``)
    * Image references (``content["image"]`` or ``content["image_url"]``)
    * File references (``content["file"]`` or ``content["file_url"]``)
    * Structured data (``content["data"]``)

    Returns an empty list when the content cannot be converted.
    """
    if content is None:
        return []

    if isinstance(content, str):
        return [Part(root=TextPart(text=content))] if content else []

    if not isinstance(content, dict):
        return [Part(root=TextPart(text=str(content)))]

    parts: list[Part] = []

    # Text content
    text = content.get("text") or content.get("message") or content.get("detail")
    if isinstance(text, str) and text:
        parts.append(Part(root=TextPart(text=text)))

    # Image content
    image = content.get("image") or content.get("image_output")
    if isinstance(image, dict):
        part = _image_dict_to_part(image)
        if part is not None:
            parts.append(part)

    image_url = content.get("image_url")
    if isinstance(image_url, str) and image_url:
        parts.append(
            Part(
                root=FilePart(
                    file=FileWithUri(name="image", uri=image_url, mime_type="image/png"),
                )
            )
        )

    # File content
    file_data = content.get("file") or content.get("file_output")
    if isinstance(file_data, dict):
        part = _file_dict_to_part(file_data)
        if part is not None:
            parts.append(part)

    file_url = content.get("file_url")
    if isinstance(file_url, str) and file_url:
        parts.append(
            Part(
                root=FilePart(
                    file=FileWithUri(name="file", uri=file_url),
                )
            )
        )

    # Structured data (tool results, JSON payloads)
    data = content.get("data")
    if isinstance(data, dict) and data:
        parts.append(Part(root=DataPart(data=data)))

    return parts


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _extract_text(msg: dict[str, Any]) -> str:
    """Extract plain text from a message dict (same logic as ``_extract_last_user_text``)."""
    content = msg.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()

    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str) and text.strip():
                    text_parts.append(text.strip())
            elif isinstance(item, str) and item.strip():
                text_parts.append(item.strip())
        if text_parts:
            return "\n".join(text_parts)

    return ""


def _image_dict_to_part(img: dict[str, Any]) -> Optional[Part]:
    """Convert an ii-agent Image dict to an A2A ``FilePart``.

    Supports three content sources (in priority order):
    1. ``url`` → ``FileWithUri``
    2. ``content`` (base64 or raw bytes) → ``FileWithBytes``
    3. ``filepath`` → ``FileWithUri`` (file:// scheme)
    """
    mime = img.get("mime_type") or "image/png"
    name = img.get("id") or img.get("alt_text") or "image"

    url = img.get("url")
    if url:
        return Part(root=FilePart(file=FileWithUri(name=str(name), uri=url, mime_type=mime)))

    raw_content = img.get("content")
    if raw_content:
        b64 = _to_base64(raw_content)
        if b64:
            return Part(
                root=FilePart(file=FileWithBytes(name=str(name), bytes=b64, mime_type=mime))
            )

    filepath = img.get("filepath")
    if filepath:
        return Part(
            root=FilePart(
                file=FileWithUri(name=str(name), uri=f"file://{filepath}", mime_type=mime)
            )
        )

    return None


def _file_dict_to_part(fd: dict[str, Any]) -> Optional[Part]:
    """Convert an ii-agent File dict to an A2A ``FilePart``."""
    mime = fd.get("mime_type") or "application/octet-stream"
    name = fd.get("filename") or fd.get("name") or fd.get("id") or "file"

    url = fd.get("url")
    if url:
        return Part(root=FilePart(file=FileWithUri(name=str(name), uri=url, mime_type=mime)))

    raw_content = fd.get("content")
    if raw_content:
        b64 = _to_base64(raw_content)
        if b64:
            return Part(
                root=FilePart(file=FileWithBytes(name=str(name), bytes=b64, mime_type=mime))
            )

    filepath = fd.get("filepath")
    if filepath:
        return Part(
            root=FilePart(
                file=FileWithUri(name=str(name), uri=f"file://{filepath}", mime_type=mime)
            )
        )

    return None


def _audio_dict_to_part(aud: dict[str, Any]) -> Optional[Part]:
    """Convert an ii-agent Audio dict to an A2A ``FilePart``."""
    mime = aud.get("mime_type") or "audio/mpeg"
    name = aud.get("id") or "audio"

    url = aud.get("url")
    if url:
        return Part(root=FilePart(file=FileWithUri(name=str(name), uri=url, mime_type=mime)))

    raw_content = aud.get("content")
    if raw_content:
        b64 = _to_base64(raw_content)
        if b64:
            return Part(
                root=FilePart(file=FileWithBytes(name=str(name), bytes=b64, mime_type=mime))
            )

    filepath = aud.get("filepath")
    if filepath:
        return Part(
            root=FilePart(
                file=FileWithUri(name=str(name), uri=f"file://{filepath}", mime_type=mime)
            )
        )

    return None


def _video_dict_to_part(vid: dict[str, Any]) -> Optional[Part]:
    """Convert an ii-agent Video dict to an A2A ``FilePart``."""
    mime = vid.get("mime_type") or "video/mp4"
    name = vid.get("id") or "video"

    url = vid.get("url")
    if url:
        return Part(root=FilePart(file=FileWithUri(name=str(name), uri=url, mime_type=mime)))

    raw_content = vid.get("content")
    if raw_content:
        b64 = _to_base64(raw_content)
        if b64:
            return Part(
                root=FilePart(file=FileWithBytes(name=str(name), bytes=b64, mime_type=mime))
            )

    filepath = vid.get("filepath")
    if filepath:
        return Part(
            root=FilePart(
                file=FileWithUri(name=str(name), uri=f"file://{filepath}", mime_type=mime)
            )
        )

    return None


def _to_base64(value: Any) -> Optional[str]:
    """Normalise a content value to a base64 string.

    *value* can be ``bytes``, a base64-encoded ``str``, or ``None``.
    """
    if value is None:
        return None
    if isinstance(value, bytes):
        return base64.b64encode(value).decode("ascii")
    if isinstance(value, str):
        # Already base64-encoded
        return value
    return None


def has_multimodal_parts(parts: Sequence[Part]) -> bool:
    """Return ``True`` if *parts* contains any non-text Part."""
    return any(not isinstance(p.root, TextPart) for p in parts)
