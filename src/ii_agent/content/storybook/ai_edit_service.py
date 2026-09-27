"""Storybook AI edit orchestration service."""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from typing import Any, Dict, Optional, TYPE_CHECKING

from bs4 import BeautifulSoup
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.users.service import UserService
from ii_agent.credits.service import CreditService
from ii_agent.billing.exceptions import InsufficientCreditsError
from ii_agent.chat.llm.factory import get_client
from ii_agent.chat.types import ImageURLContent, MessageRole, TextContent
from ii_agent.content.media.service import _generate_image
from ii_agent.content.storybook.billing import (
    DEFAULT_STORYBOOK_IMAGE_RESERVE_USD,
    build_storybook_scope,
    check_and_deduct_storybook_credits,
)
from ii_agent.content.storybook.schemas import StorybookDetail
from ii_agent.core.config.settings import Settings
from ii_agent.core.exceptions import ValidationError
from ii_agent.chat.llm.utils import make_message, extract_text_content
from ii_agent.core.request_context import get_or_generate_request_id
from ii_agent.sessions.service import SessionService
from ii_agent.settings.llm.service import ModelSettingService

if TYPE_CHECKING:
    from ii_agent.core.config.llm_config import LLMConfig

logger = logging.getLogger(__name__)

DEFAULT_TEXT_PERCENTAGE = 30
DEFAULT_IMAGE_COST_USD = 0.02
ALLOWED_TEXT_POSITIONS = {"left", "right", "top", "bottom", "none", "separate_page"}

FALLBACK_SUPPORTED_ASPECT_RATIOS_BY_PROVIDER = {
    "openai": {
        "1:1": 1.0,
        "2:3": 0.666,
        "3:2": 1.5,
    },
    "gemini": {
        "1:1": 1.0,
        "2:3": 0.666,
        "3:2": 1.5,
        "16:9": 1.777,
        "9:16": 0.562,
        "4:3": 1.333,
        "3:4": 0.75,
        "21:9": 2.333,
    },
    "vertex": {
        "1:1": 1.0,
        "2:3": 0.666,
        "3:2": 1.5,
        "16:9": 1.777,
        "9:16": 0.562,
        "4:3": 1.333,
        "3:4": 0.75,
        "21:9": 2.333,
    },
}
DEFAULT_SUPPORTED_RATIOS = FALLBACK_SUPPORTED_ASPECT_RATIOS_BY_PROVIDER["gemini"]

AI_REWRITE_SYSTEM_PROMPT = """You are a creative writing assistant helping to improve text content for a storybook page.

Your task is to rewrite the given text to make it more engaging, clear, and appropriate for the storybook context.

Guidelines:
- Maintain the original meaning and intent
- Improve clarity and flow
- Make the language more vivid and engaging
- Keep a similar length (don't make it much longer or shorter)
- Match the tone appropriate for the storybook context
- If an image is provided, consider the visual context when rewriting

Return ONLY the rewritten text, without any explanations or additional commentary."""


def _build_extension_prompt(user_prompt: str, text_position: Optional[str]) -> str:
    """Build an outpainting prompt for extending a storybook background image."""
    direction_info = {
        "separate_page": {
            "direction": "to the right",
            "edge": "left edge",
            "continue_from": "right side",
        },
        "right": {
            "direction": "to the left",
            "edge": "right edge",
            "continue_from": "left side",
        },
        "left": {
            "direction": "to the right",
            "edge": "left edge",
            "continue_from": "right side",
        },
        "top": {
            "direction": "downward",
            "edge": "top edge",
            "continue_from": "bottom",
        },
        "bottom": {
            "direction": "upward",
            "edge": "bottom edge",
            "continue_from": "top",
        },
    }

    info = direction_info.get(text_position or "")
    if info:
        return (
            f"OUTPAINTING TASK: Generate an image that continues and extends the reference image {info['direction']}. "
            f"This new image will be placed next to the original to create a wider/larger panoramic view. "
            f"CRITICAL REQUIREMENTS: "
            f"1) The {info['edge']} of your generated image must seamlessly connect with the {info['continue_from']} of the reference image. "
            f"2) Match EXACTLY the same art style, color palette, lighting direction, atmosphere, and visual quality. "
            f"3) Continue the same scene naturally - maintain consistent horizon line, perspective, and scale. "
            f"4) Extend the environment, background elements, and any ongoing visual elements from the reference. "
            f"5) Do NOT recreate or duplicate the reference image - generate NEW content that continues the scene. "
            f"Scene context to extend: {user_prompt}"
        )

    return (
        "Generate an image that matches the exact art style, color palette, lighting, and visual quality "
        "of the reference image. Create a scene that could exist in the same world/story. "
        f"Scene description: {user_prompt}"
    )


def _build_style_context(style_json: Dict[str, Any]) -> str:
    """Build a compact style context string from storybook style settings."""
    style_parts = []
    character_description = style_json.get("character_description")
    art_style = style_json.get("art_style")
    color_palette = style_json.get("color_palette")

    if character_description:
        style_parts.append(f"Character: {character_description}")
    if art_style:
        style_parts.append(f"Art style: {art_style}")
    if color_palette:
        style_parts.append(f"Color palette: {color_palette}")

    return ". ".join(style_parts) if style_parts else ""


def _enhance_prompt_with_style(
    image_prompt: str,
    style_context: str,
    aspect_ratio: str,
    *,
    is_cover_page: bool = False,
    reference_type: Optional[str] = None,
    composition_rule: Optional[str] = None,
) -> str:
    """Enhance prompt with style and strict layout constraints."""
    borderless_note = (
        "CRITICAL TECHNICAL REQUIREMENTS - READ CAREFULLY: "
        f"This image MUST be generated at EXACTLY {aspect_ratio} aspect ratio and fill 100% of the canvas (FULL BLEED). "
        "STRICTLY PROHIBITED: Empty borders, letterboxing, pillarboxing, white bars, gray bars, black bars, "
        "centered content with surrounding empty space, frames, vignettes, padding, margins, or ANY unfilled areas. "
        "ALSO PROHIBITED: Do NOT include any decorative borders, ornamental frames, book-style page borders, "
        "or edge designs within the artwork itself. "
        "REQUIRED: The artwork must extend completely to all four edges (top, bottom, left, right) with zero empty space."
    )

    negative_prompt = (
        " NEGATIVE PROMPT / STRICTLY PROHIBITED: No violence, gore, blood, injury, weapons, war, crime, "
        "threats, hate symbols, harassment, or bullying. No sexual or suggestive content, nudity, fetish, "
        "pornography, or sexualized minors. No self-harm or suicide. No drugs, alcohol abuse, smoking, or vaping. "
        "No gambling, political propaganda, extremist imagery, or controversial symbols. No real person likeness, "
        "no copyrighted characters/brands, no watermarks, and no text overlays."
    )
    if not is_cover_page:
        negative_prompt += (
            " Also, do NOT include any titles, text, letters, captions, typography, branding, logos, "
            "book cover elements, thumbnails, or headings."
        )

    if composition_rule:
        borderless_note += f" {composition_rule}"

    reference_note = ""
    if reference_type == "style_only":
        reference_note = (
            " Match the art style, color palette, and visual aesthetic of the "
            "reference image, but DO NOT copy characters, specific subjects, "
            "or any text/title from the reference image."
        )

    if not style_context:
        return f"{image_prompt}. {borderless_note}{negative_prompt}{reference_note}"
    return f"{image_prompt}. {style_context}. {borderless_note}{negative_prompt}{reference_note}"


def _get_optimal_aspect_ratio(
    base_aspect_ratio: str,
    text_position: str,
    text_percentage: int,
    provider: Optional[str],
) -> str:
    """Calculate optimal generation aspect ratio to reduce cropping."""
    if text_position == "none" or text_percentage <= 0:
        return base_aspect_ratio

    try:
        width, height = map(int, base_aspect_ratio.split(":"))
        base_ratio = width / height
    except ValueError:
        return base_aspect_ratio

    if text_position in {"left", "right"}:
        target_ratio = base_ratio * (1 - text_percentage / 100.0)
    elif text_position in {"top", "bottom"}:
        target_ratio = base_ratio / (1 - text_percentage / 100.0)
    else:
        return base_aspect_ratio

    provider_key = provider.lower() if provider else "gemini"
    supported = FALLBACK_SUPPORTED_ASPECT_RATIOS_BY_PROVIDER.get(
        provider_key,
        DEFAULT_SUPPORTED_RATIOS,
    )
    closest_ar = min(supported.keys(), key=lambda key: abs(supported[key] - target_ratio))
    return closest_ar


def _calculate_safe_zones(
    base_aspect_ratio: str,
    gen_aspect_ratio: str,
    text_position: str,
    text_percentage: int,
) -> tuple[int, int]:
    """Calculate visible image safe zone percentages (width, height)."""
    if text_position == "none" or text_percentage <= 0:
        return 100, 100

    try:
        bw, bh = map(int, base_aspect_ratio.split(":"))
        base_ratio = bw / bh
        gw, gh = map(int, gen_aspect_ratio.split(":"))
        gen_ratio = gw / gh
    except ValueError:
        return 100, 100

    if text_position in {"left", "right"}:
        container_ratio = base_ratio * (1 - text_percentage / 100.0)
    elif text_position in {"top", "bottom"}:
        container_ratio = base_ratio / (1 - text_percentage / 100.0)
    else:
        return 100, 100

    if gen_ratio > container_ratio:
        visible_width = int((container_ratio / gen_ratio) * 100)
        return visible_width, 100

    visible_height = int((gen_ratio / container_ratio) * 100)
    return 100, visible_height


def _extract_text_from_html(html_content: str) -> str:
    """Extract editable text blocks from storybook page HTML."""
    if not html_content:
        return ""
    soup = BeautifulSoup(html_content, "html.parser")
    nodes = soup.select('[data-editable="text"]')
    texts = [node.get_text(" ", strip=True) for node in nodes]
    return " ".join(text for text in texts if text).strip()


def _extract_text_position_from_html(html_content: str) -> Optional[str]:
    """Infer text position from storybook HTML layout rules."""
    if not html_content:
        return None
    match = re.search(
        r"\.storybook-page\s*\{[^}]*flex-direction:\s*([^;]+);",
        html_content,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None

    direction = re.sub(r"\s+", "", match.group(1).strip().lower())
    mapping = {
        "row": "right",
        "row-reverse": "left",
        "column": "bottom",
        "column-reverse": "top",
    }
    return mapping.get(direction)


def _extract_text_percentage_from_html(html_content: str) -> Optional[int]:
    """Infer text percentage allocation from storybook HTML layout rules."""
    if not html_content:
        return None

    match = re.search(
        r"\.text-section\s*\{[^}]*flex:\s*0\s+0\s+(\d+)%",
        html_content,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None

    match = re.search(
        r"\.image-section\s*\{[^}]*flex:\s*0\s+0\s+(\d+)%",
        html_content,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if match:
        try:
            image_pct = int(match.group(1))
        except ValueError:
            return None
        return max(0, 100 - image_pct)

    return None


def _extract_page(storybook: StorybookDetail, page_number: int):
    """Find one page in a StorybookDetail by page number."""
    for page in storybook.pages or []:
        if page.page_number == page_number:
            return page
    return None


class StorybookAIEditService:
    """AI orchestration for storybook editing flows."""

    def __init__(
        self,
        *,
        session_service: SessionService,
        user_service: UserService,
        model_setting_service: ModelSettingService,
        credit_service: CreditService,
        config: Settings,
    ) -> None:
        self._session_service = session_service
        self._user_service = user_service
        self._model_setting_service = model_setting_service
        self._credit_service = credit_service
        self._config = config

    async def rewrite_content(
        self,
        db: AsyncSession,
        *,
        storybook: StorybookDetail,
        user_id: str,
        content: str,
        page_image_url: Optional[str] = None,
    ) -> str:
        """Rewrite storybook text content using the session's LLM config."""
        if not content or not content.strip():
            raise ValidationError("No content provided to rewrite")

        llm_config, model_id = await self._resolve_storybook_llm_config(
            db,
            user_id=user_id,
            session_id=storybook.session_id,
        )
        llm_config.temperature = 0.7
        llm_config.thinking_tokens = 0

        client = get_client(llm_config)
        prompt = f"Please rewrite the following text. Do not add any extra content or context.\n\n{content.strip()}"
        if page_image_url:
            prompt = (
                "Use the attached storybook page image as visual context. "
                "Rewrite the following text so it better fits what is happening in the scene:\n\n This will be the final content, just rewrite it do not add any extra content or context.\n\n"
                f"{content.strip()}"
            )

        messages = [
            make_message(
                role=MessageRole.SYSTEM,
                session_id=storybook.session_id,
                parts=[TextContent(text=AI_REWRITE_SYSTEM_PROMPT)],
            ),
            make_message(
                role=MessageRole.USER,
                session_id=storybook.session_id,
                parts=[
                    TextContent(text=prompt),
                    *([ImageURLContent(url=page_image_url)] if page_image_url else []),
                ],
            ),
        ]

        result = await client.send(messages)
        rewritten_text = extract_text_content(result.content).strip()
        if not rewritten_text:
            raise ValidationError("AI did not return any rewritten content")
        return rewritten_text

    async def generate_background(
        self,
        db: AsyncSession,
        *,
        storybook: StorybookDetail,
        user_id: str,
        prompt: str,
        page_image_url: Optional[str] = None,
        text_position: Optional[str] = None,
    ) -> str:
        """Generate or outpaint a storybook background image."""
        if not prompt or not prompt.strip():
            raise ValidationError("No prompt provided for image generation")

        if not await self._credit_service.has_sufficient_credits(db, user_id):
            raise InsufficientCreditsError(available_credits=0.0, required_credits=0.0)

        user_api_key = await self._user_service.get_active_api_key(db, user_id)
        if not user_api_key:
            raise ValidationError("No active API key found")

        style_json = storybook.style_json or {}
        request_id = get_or_generate_request_id()
        return await self._run_billed_image_operation(
            db,
            storybook=storybook,
            user_id=user_id,
            operation_id=f"background:{storybook.id}:{request_id}",
            tool_name="storybook_background",
            context=f"storybook {storybook.id} background generation",
            execute_fn=lambda: _generate_image(
                prompt=_build_extension_prompt(prompt.strip(), text_position),
                aspect_ratio=storybook.aspect_ratio,
                image_size=storybook.resolution,
                session_id=storybook.session_id,
                user_api_key=user_api_key,
                image_urls=[page_image_url] if page_image_url else None,
                model_name=style_json.get("image_model_name"),
                provider=style_json.get("image_provider"),
            ),
        )

    async def regenerate_image(
        self,
        db: AsyncSession,
        *,
        storybook: StorybookDetail,
        user_id: str,
        page_number: int,
        prompt: str,
        reference_image_url: Optional[str] = None,
        scene_text: Optional[str] = None,
        text_position: Optional[str] = None,
        text_percentage: Optional[int] = None,
    ) -> str:
        """Generate a replacement storybook page image with layout awareness."""
        if not prompt or not prompt.strip():
            raise ValidationError("No prompt provided for image regeneration")

        if not await self._credit_service.has_sufficient_credits(db, user_id):
            raise InsufficientCreditsError(available_credits=0.0, required_credits=0.0)

        page = _extract_page(storybook, page_number)
        if not page:
            raise ValidationError("Page not found")

        user_api_key = await self._user_service.get_active_api_key(db, user_id)
        if not user_api_key:
            raise ValidationError("No active API key found")

        style_json = storybook.style_json or {}
        page_html = page.html_content or ""
        metadata = page.metadata or {}

        resolved_position = text_position
        if resolved_position and resolved_position not in ALLOWED_TEXT_POSITIONS:
            resolved_position = None
        if not resolved_position and metadata.get("is_separate_page_image"):
            resolved_position = "separate_page"
        if not resolved_position:
            resolved_position = _extract_text_position_from_html(page_html) or "none"

        resolved_percentage = text_percentage
        if resolved_position in {"none", "separate_page"}:
            resolved_percentage = 0
        elif resolved_percentage is None:
            resolved_percentage = _extract_text_percentage_from_html(page_html)
            if resolved_percentage is None:
                resolved_percentage = DEFAULT_TEXT_PERCENTAGE

        resolved_scene_text = (scene_text or "").strip()
        if not resolved_scene_text:
            if resolved_position == "separate_page":
                next_page = _extract_page(storybook, page_number + 1)
                next_meta = next_page.metadata if next_page and next_page.metadata else {}
                if next_page and next_meta.get("is_text_only_page"):
                    linked_image = next_meta.get("linked_image_page")
                    if linked_image in (None, page_number):
                        resolved_scene_text = _extract_text_from_html(next_page.html_content or "")
            if not resolved_scene_text:
                resolved_scene_text = _extract_text_from_html(page_html)

        base_prompt = prompt.strip()
        if resolved_scene_text:
            base_prompt = (
                f"{base_prompt}\nScene context (do not render as text): {resolved_scene_text}"
            )

        is_cover_page = page_number == 1
        storybook_name = storybook.name.strip()
        if is_cover_page and storybook_name:
            base_prompt = (
                f"{base_prompt}\nSTORYBOOK TITLE: This is the cover page. "
                f"Include the title '{storybook_name}' as prominent, stylized text "
                f"that fits the art style of the illustration."
            )
        else:
            base_prompt = (
                f"{base_prompt}\nIMPORTANT: Do NOT include any text, letters, captions, "
                "titles, or typography in the image. This is an interior page illustration only."
            )

        gen_aspect_ratio = storybook.aspect_ratio
        composition_rule = None
        if resolved_position in {"left", "right", "top", "bottom"} and resolved_percentage:
            gen_aspect_ratio = _get_optimal_aspect_ratio(
                storybook.aspect_ratio,
                resolved_position,
                resolved_percentage,
                style_json.get("image_provider"),
            )
            safe_width, safe_height = _calculate_safe_zones(
                storybook.aspect_ratio,
                gen_aspect_ratio,
                resolved_position,
                resolved_percentage,
            )
            composition_rule = (
                "CRITICAL LAYOUT INSTRUCTION: "
                f"Only the CENTER {safe_width}% WIDTH and CENTER {safe_height}% HEIGHT will remain visible in the final layout. "
                "Keep all important subjects and details inside that safe zone."
            )

        reference_image_urls: list[str] = []
        reference_type = None
        if reference_image_url:
            reference_image_urls.append(reference_image_url)
            reference_type = "style_only"
        if page.image_url and page.image_url not in reference_image_urls:
            reference_image_urls.append(page.image_url)
            reference_type = reference_type or "style_only"

        final_prompt = _enhance_prompt_with_style(
            base_prompt,
            _build_style_context(style_json),
            storybook.aspect_ratio,
            is_cover_page=is_cover_page,
            reference_type=reference_type,
            composition_rule=composition_rule,
        )

        last_exception: Exception | None = None
        for attempt in range(1, 6):
            try:
                request_id = get_or_generate_request_id()
                return await self._run_billed_image_operation(
                    db,
                    storybook=storybook,
                    user_id=user_id,
                    operation_id=f"regenerate:{storybook.id}:{page_number}:{request_id}",
                    tool_name="storybook_image_regeneration",
                    context=f"storybook {storybook.id} page {page_number} regenerate",
                    execute_fn=lambda: _generate_image(
                        prompt=final_prompt,
                        aspect_ratio=gen_aspect_ratio,
                        image_size=storybook.resolution,
                        session_id=storybook.session_id,
                        user_api_key=user_api_key,
                        image_urls=reference_image_urls or None,
                        model_name=style_json.get("image_model_name"),
                        provider=style_json.get("image_provider"),
                    ),
                )
            except InsufficientCreditsError:
                raise
            except Exception as exc:
                last_exception = exc
                if attempt < 5:
                    logger.warning(
                        "[Storybook AI Regenerate] Attempt %s/5 failed for storybook %s page %s: %s",
                        attempt,
                        storybook.id,
                        page_number,
                        exc,
                    )
                    await asyncio.sleep(5)

        raise RuntimeError(f"Failed to regenerate image after 5 attempts: {last_exception}")

    async def _resolve_storybook_llm_config(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        session_id: str,
    ):
        """Resolve the session LLM config with default fallback."""

        async def _get_default() -> LLMConfig:
            try:
                return await self._model_setting_service.resolve_system_config(
                    db, model_id="default"
                )
            except ValueError:
                return LLMConfig()

        try:
            session_uuid = uuid.UUID(session_id)
            session = await self._session_service.get_session_by_id(db, session_uuid)
        except Exception:
            return (await _get_default()).model_copy(deep=True), "default"

        setting_id = str(getattr(session, "model_setting_id", "") or "").strip()
        if not setting_id:
            return (await _get_default()).model_copy(deep=True), "default"

        try:
            llm_config = await self._model_setting_service.get_user_llm_config(
                db,
                setting_id=setting_id,
                user_id=user_id,
            )
            return llm_config.model_copy(deep=True), setting_id
        except Exception:
            try:
                llm_config = await self._model_setting_service.resolve_system_config(
                    db, model_id=setting_id
                )
                return llm_config.model_copy(deep=True), setting_id
            except Exception:
                return (await _get_default()).model_copy(deep=True), "default"

    async def _run_billed_image_operation(
        self,
        db: AsyncSession,
        *,
        storybook: StorybookDetail,
        user_id: str,
        operation_id: str,
        tool_name: str,
        context: str,
        execute_fn,
    ) -> str:
        """Check credits, execute image generation, then deduct actual cost."""
        scope = build_storybook_scope(
            user_id=user_id,
            session_id=storybook.session_id,
        )

        # 1. Check credits up-front
        estimated_cost = float(DEFAULT_STORYBOOK_IMAGE_RESERVE_USD)
        has_credits = await self._credit_service.has_sufficient_credits(db, user_id, estimated_cost)
        if not has_credits:
            logger.warning("[Storybook AI Edit] Insufficient credits for %s", context)
            raise InsufficientCreditsError(
                available_credits=0.0,
                required_credits=estimated_cost,
            )

        # 2. Execute the operation
        response = await execute_fn()
        image_url = response.get("url")
        if not image_url:
            raise RuntimeError("Image generation did not return an image URL")

        # 3. Deduct actual cost
        actual_cost = response.get("cost") or DEFAULT_IMAGE_COST_USD
        if actual_cost > 0:
            await check_and_deduct_storybook_credits(
                db,
                credit_service=self._credit_service,
                scope=scope,
                amount_usd=actual_cost,
                tool_name=tool_name,
                metadata={
                    "storybook_id": storybook.id,
                    "context": context,
                },
            )

        return image_url
