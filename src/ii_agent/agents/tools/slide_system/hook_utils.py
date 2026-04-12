from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, TYPE_CHECKING

from ii_agent.core.config.settings import get_settings
from ii_agent.core.db import get_db_session_local
from ii_agent.content.slides.content_processor import SlideContentProcessor
from ii_agent.core.storage.client import get_storage
from ii_agent.core.logger import logger

if TYPE_CHECKING:
    from ii_agent.agents.agent import IIAgent
    from ii_agent.content.slides.service import SlideService


_SLIDE_FILEPATH_RE = re.compile(r"(?:^|/)presentations/([^/]+)/slide_(\d+)\.html$")
_HTML_TITLE_RE = re.compile(r"<title[^>]*>\s*(.*?)\s*</title>", re.IGNORECASE | re.DOTALL)


@dataclass(slots=True)
class PersistableSlidePayload:
    presentation_name: str
    slide_number: int
    slide_content: str
    slide_title: str | None = None


def _build_storage():
    try:
        return get_storage()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Slide content processing skipped: %s", exc)
        return None


def _coerce_slide_number(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            parsed = int(stripped)
            return parsed if parsed > 0 else None
    return None


def _extract_html_title(html_content: Any) -> str | None:
    if not isinstance(html_content, str) or not html_content.strip():
        return None
    match = _HTML_TITLE_RE.search(html_content)
    if not match:
        return None
    title = re.sub(r"\s+", " ", match.group(1)).strip()
    return title or None


def _parse_slide_filepath(filepath: Any) -> tuple[str | None, int | None]:
    if not isinstance(filepath, str) or not filepath:
        return None, None
    match = _SLIDE_FILEPATH_RE.search(filepath)
    if not match:
        return None, None
    return match.group(1), int(match.group(2))


def _extract_slide_payload_from_mapping(
    *,
    default_presentation_name: str | None,
    default_slide_number: int | None,
    default_title: str | None,
    mapping: dict[str, Any],
) -> PersistableSlidePayload | None:
    slide_content = mapping.get("content")
    if not isinstance(slide_content, str) or not slide_content.strip():
        slide_content = mapping.get("new_content")
    if not isinstance(slide_content, str) or not slide_content.strip():
        return None

    filepath_presentation_name, filepath_slide_number = _parse_slide_filepath(
        mapping.get("filepath")
    )

    presentation_name = mapping.get("presentation_name")
    if not isinstance(presentation_name, str) or not presentation_name.strip():
        presentation_name = default_presentation_name or filepath_presentation_name
    if not isinstance(presentation_name, str) or not presentation_name.strip():
        return None

    slide_number = _coerce_slide_number(mapping.get("slide_number"))
    if slide_number is None:
        slide_number = default_slide_number or filepath_slide_number
    if slide_number is None:
        return None

    title = mapping.get("title")
    if not isinstance(title, str) or not title.strip():
        title = mapping.get("slide_title")
    if not isinstance(title, str) or not title.strip():
        title = default_title or _extract_html_title(slide_content)

    return PersistableSlidePayload(
        presentation_name=presentation_name.strip(),
        slide_number=slide_number,
        slide_content=slide_content,
        slide_title=title.strip() if isinstance(title, str) and title.strip() else None,
    )


def _extract_persistable_slide_payloads(
    *,
    tool_input: Dict[str, Any],
    user_display_content: Any,
) -> list[PersistableSlidePayload]:
    default_presentation_name = tool_input.get("presentation_name")
    if not isinstance(default_presentation_name, str):
        default_presentation_name = None

    default_slide_number = _coerce_slide_number(tool_input.get("slide_number"))

    default_title = tool_input.get("title")
    if not isinstance(default_title, str):
        default_title = None

    if isinstance(user_display_content, dict):
        payload = _extract_slide_payload_from_mapping(
            default_presentation_name=default_presentation_name,
            default_slide_number=default_slide_number,
            default_title=default_title,
            mapping=user_display_content,
        )
        return [payload] if payload else []

    if isinstance(user_display_content, list):
        payloads: list[PersistableSlidePayload] = []
        for item in user_display_content:
            if not isinstance(item, dict):
                continue
            payload = _extract_slide_payload_from_mapping(
                default_presentation_name=default_presentation_name,
                default_slide_number=default_slide_number,
                default_title=default_title,
                mapping=item,
            )
            if payload:
                payloads.append(payload)
        return payloads

    return []


async def process_slide_content(
    *,
    agent: "IIAgent",
    tool_name: str,
    user_display_content: Any,
    url_cache: Optional[Dict[str, str]] = None,
) -> Any:
    settings = get_settings()
    # Skip only when using local filesystem storage with no serving capability.
    # MinIO and GCS can serve content even without a custom domain.
    if not settings.storage.custom_domain and not settings.storage.serve_base_url:
        if settings.storage.provider != "gcs":
            return user_display_content

    sandbox = getattr(agent, "sandbox", None)
    if not sandbox:
        return user_display_content

    storage = _build_storage()
    if storage is None:
        return user_display_content

    # When there's no custom domain (e.g., local MinIO), use the backend's
    # slide assets endpoint so images are served through our API.
    slide_assets_base_url: str | None = None
    if not settings.storage.custom_domain and settings.storage.serve_base_url:
        base = settings.storage.serve_base_url.rstrip("/")
        slide_assets_base_url = f"{base}/files/slides/assets"

    content_processor = SlideContentProcessor(
        storage,
        sandbox,
        url_cache=url_cache or {},
        slide_assets_base_url=slide_assets_base_url,
    )

    try:
        if tool_name == "slide_apply_patch" and isinstance(user_display_content, list):
            for slide_data in user_display_content:
                if not isinstance(slide_data, dict):
                    continue
                html_content = slide_data.get("new_content")
                slide_file_path = slide_data.get("filepath")
                if html_content and slide_file_path:
                    processed_html = await content_processor.process_html_content(
                        html_content, slide_file_path
                    )
                    slide_data["new_content"] = processed_html
            return user_display_content

        if isinstance(user_display_content, dict) and "content" in user_display_content:
            html_content = user_display_content.get("content")
            slide_file_path = user_display_content.get("filepath")
            if html_content and slide_file_path:
                processed_html = await content_processor.process_html_content(
                    html_content, slide_file_path
                )
                user_display_content["content"] = processed_html
            return user_display_content

        if isinstance(user_display_content, list):
            for slide_data in user_display_content:
                if not isinstance(slide_data, dict):
                    continue
                if "new_content" not in slide_data:
                    continue
                html_content = slide_data.get("new_content")
                slide_file_path = slide_data.get("filepath")
                if html_content and slide_file_path:
                    processed_html = await content_processor.process_html_content(
                        html_content, slide_file_path
                    )
                    slide_data["new_content"] = processed_html
            return user_display_content

        return user_display_content
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Error processing slide content for %s: %s", tool_name, exc)
        return user_display_content


async def persist_slide_tool_result(
    *,
    agent: "IIAgent",
    slide_service: "SlideService | None",
    tool_name: str,
    tool_input: Dict[str, Any],
    user_display_content: Any,
) -> None:
    session_id = getattr(agent, "session_id", None)
    if not session_id or slide_service is None:
        return

    payloads = _extract_persistable_slide_payloads(
        tool_input=tool_input,
        user_display_content=user_display_content,
    )
    if not payloads:
        return

    normalized_session_id = str(session_id)

    try:
        async with get_db_session_local() as db:
            for payload in payloads:
                await slide_service.persist_tool_slide_result(
                    db,
                    session_id=normalized_session_id,
                    presentation_name=payload.presentation_name,
                    slide_number=payload.slide_number,
                    slide_title=payload.slide_title,
                    slide_content=payload.slide_content,
                    tool_name=tool_name,
                )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "Failed to persist slide tool result for session %s (%s): %s",
            normalized_session_id,
            tool_name,
            exc,
        )
