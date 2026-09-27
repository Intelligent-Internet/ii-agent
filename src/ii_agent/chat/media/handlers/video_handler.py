"""Handler for video generation media type."""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, List, Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.chat.types import (
    BinaryContent,
    TextContent,
    MediaPreferences,
    VideoFrameReference,
    VideoSettings,
)
from ii_agent.chat.tools.base import BaseTool
from ii_agent.chat.tools.video_generate import (
    VideoGenerationTool,
    DURATION_TO_SECONDS,
)
from ii_agent.chat.tools.video_concatenate import ConcatenateVideosTool
from ii_agent.chat.tools.video_extract_frames import ExtractFramesTool
from ii_agent.chat.prompts.video_prompts import (
    VIDEO_GENERATION_SYSTEM_PROMPT,
    build_audio_guidance_hint,
    build_frame_transition_hint,
)
from ii_agent.chat.application.file_processor import (
    compress_image_for_provider,
    DEFAULT_IMAGE_LIMIT,
)
from ii_agent.core.storage.client import get_storage
from ..modes.base import BaseModeStrategy
from ..modes.normal_mode import NormalModeStrategy
from ..registry import register_handler
from .base import BaseMediaHandler

if TYPE_CHECKING:
    from ii_agent.core.container import ApplicationContainer

logger = logging.getLogger(__name__)


# Duration threshold for long video workflow (LLM uses multi-segment workflow above this)
LONG_VIDEO_THRESHOLD_SECONDS = 8


@register_handler("video")
class VideoMediaHandler(BaseMediaHandler):
    """
    Handler for video generation media type.

    Supports text-to-video and image-to-video generation with:
    - Start frame (first frame reference)
    - End frame (last frame reference)
    - Duration, resolution, aspect ratio settings
    - Audio generation toggle
    - Multishot mode for scene splitting
    """

    def detect_mode(self, media_preferences: MediaPreferences) -> BaseModeStrategy:
        """Detect mode for video generation. Currently uses NormalMode only."""
        return NormalModeStrategy()

    async def create_tools(
        self,
        *,
        session_id: uuid.UUID,
        mode_strategy: BaseModeStrategy,
        media_preferences: MediaPreferences,
        container: ApplicationContainer,
    ) -> List[BaseTool]:
        """
        Create all video-related tools.

        Returns:
            - VideoGenerationTool: Generate single video segment (max 8s)
            - ConcatenateVideosTool: Combine multiple videos into one
            - ExtractFramesTool: Extract frames for video continuity
        """
        video_settings = media_preferences.video_settings or VideoSettings()
        video_frames = media_preferences.video_frames or []

        logger.info(
            f"[VIDEO_HANDLER] Creating tools with settings: "
            f"duration={video_settings.duration}, resolution={video_settings.resolution}, "
            f"aspect_ratio={video_settings.aspect_ratio}, audio={video_settings.audio_included}"
        )

        tools = [
            VideoGenerationTool(
                session_id=session_id,
                container=container,
                media_preferences=media_preferences,
                video_settings=video_settings,
                video_frames=video_frames,
            ),
            ConcatenateVideosTool(session_id=session_id, container=container),
            ExtractFramesTool(session_id=session_id, container=container),
        ]

        return tools

    async def build_llm_context(
        self,
        *,
        db_session: AsyncSession,
        session_id: uuid.UUID,
        mode_strategy: BaseModeStrategy,
        media_preferences: MediaPreferences,
    ) -> List[BinaryContent | TextContent]:
        """
        Build LLM message parts with reference frames as image URLs.

        For video generation, this provides:
        1. Start/end frame images via URLs so the LLM can see them AND use exact URLs
        2. Storybook reference images and scripts when switching from storybook to video mode
        """
        video_context_parts: List[BinaryContent | TextContent] = []

        # Add video frame references (start/end frames)
        video_frames = media_preferences.video_frames or []
        if video_frames:
            frame_configs = [
                ("start", "START FRAME (Video should begin with this scene)"),
                ("end", "END FRAME (Video should end with this scene)"),
            ]

            for frame_type, label in frame_configs:
                for frame in video_frames:
                    if frame.type != frame_type:
                        continue

                    frame_url = await self._get_frame_public_url(frame, db_session)
                    if not frame_url:
                        continue

                    video_context_parts.append(
                        TextContent(text=f"\n--- {label} ---\nURL: {frame_url}")
                    )
                    image_content = await self._download_image_as_binary(frame_url)
                    if image_content:
                        video_context_parts.append(image_content)
                    logger.debug(f"[VIDEO_HANDLER] Added {frame_type} frame")

        # Add storybook context when switching from storybook to video mode
        storybook_ctx = media_preferences.storybook_context
        if storybook_ctx and storybook_ctx.reference_images:
            lines = [
                "\n\n--- STORYBOOK CONTEXT FOR VIDEO GENERATION ---",
                f"Storybook ID: {storybook_ctx.storybook_id}",
                "Use these scenes as visual style references for the video.",
                "The video should match the visual style, characters, and scenes shown.\n",
                "Generated story:",
            ]

            for i, image_url in enumerate(storybook_ctx.reference_images):
                lines.append(f"- Scene {i + 1}:")
                lines.append(f"  + url: {image_url}")
                if i < len(storybook_ctx.scripts) and storybook_ctx.scripts[i]:
                    lines.append(f"  + script: {storybook_ctx.scripts[i]}")

            video_context_parts.append(TextContent(text="\n".join(lines)))

            logger.info(
                f"[VIDEO_HANDLER] Added storybook context: "
                f"{len(storybook_ctx.reference_images)} images, {len(storybook_ctx.scripts)} scripts"
            )

        return video_context_parts

    def build_system_prompt_addition(
        self,
        media_preferences: MediaPreferences,
    ) -> str:
        """Build system prompt addition for video generation mode."""
        return VIDEO_GENERATION_SYSTEM_PROMPT

    async def build_tool_hint(
        self,
        *,
        db_session: AsyncSession,
        session_id: uuid.UUID,
        media_preferences: MediaPreferences,
        mode_strategy: BaseModeStrategy,
    ) -> str:
        """Generate tool hint text for video generation."""
        video_settings = media_preferences.video_settings or VideoSettings()

        # Build explicit user configuration block
        user_config = (
            f"\n⚙️ USER VIDEO SETTINGS (MUST RESPECT):"
            f"\n  • Duration: {video_settings.duration}"
            f"\n  • Resolution: {video_settings.resolution}"
            f"\n  • Aspect Ratio: {video_settings.aspect_ratio}"
            f"\n  • Audio: {'enabled' if video_settings.audio_included else 'disabled'}"
            f"\n  • Multishot: {'enabled' if video_settings.multishot_mode else 'disabled'}"
        )

        # Determine duration
        duration_str = video_settings.duration
        duration_seconds = DURATION_TO_SECONDS.get(duration_str, 6)

        video_frames = media_preferences.video_frames or []
        has_start = video_frames and any(f.type == "start" for f in video_frames)
        has_end = video_frames and any(f.type == "end" for f in video_frames)

        frame_context = ""
        if video_frames:
            if has_start and has_end:
                frame_context = " The user provided start and end frames (shown above with URLs) - generate a video that transitions between them."
            elif has_start:
                frame_context = " The user provided a start frame (shown above with URL) - generate a video starting from this image."
            elif has_end:
                frame_context = " The user provided an end frame (shown above with URL) - generate a video ending at this image."

        # Check if this needs multi-segment workflow
        needs_multi_segment = duration_seconds > LONG_VIDEO_THRESHOLD_SECONDS

        logger.debug(
            f"[VIDEO_HANDLER] Tool hint: duration={duration_seconds}s, multi_segment={needs_multi_segment}"
        )

        # Build audio guidance
        audio_hint = build_audio_guidance_hint(
            video_settings.audio_included, is_multi_segment=needs_multi_segment
        )

        # Build frame transition guidance
        frame_hint = build_frame_transition_hint(has_start, has_end)

        # Build storybook context hint
        storybook_hint = ""
        storybook_ctx = media_preferences.storybook_context
        if storybook_ctx and storybook_ctx.reference_images:
            image_list = "\n".join(
                f"  • Image {i + 1}: {url}"
                for i, url in enumerate(storybook_ctx.reference_images[:5])
            )
            storybook_hint = (
                f"\n\n📚 STORYBOOK CONTEXT AVAILABLE:"
                f"\nReference images and scripts from a storybook are provided above."
                f"\nWhen calling generate_video, you MUST pass the image URLs in the "
                f"'reference_images' parameter to maintain visual consistency."
                f"\nUse the scripts to guide the narrative/story of the video."
                f"\n\nReference image URLs to use:\n{image_list}"
            )

        # Build the hint based on whether multi-segment is needed
        if needs_multi_segment:
            initial_duration = 8
            remaining_duration = duration_seconds - initial_duration
            extensions_needed = (remaining_duration + 6) // 7

            extension_steps = []
            current_total = initial_duration
            for i in range(extensions_needed):
                ext_duration = min(7, duration_seconds - current_total)
                current_total += ext_duration
                step_num = i + 2
                if i == extensions_needed - 1 and has_end:
                    extension_steps.append(
                        f'\n   Step {step_num}: generate_video(prompt="[continue description]", '
                        f"source_video=<previous_url>, use_extension_api=True, is_final_segment=True)"
                        f"\n           → Returns {current_total}s merged video (with end frame applied)"
                    )
                else:
                    extension_steps.append(
                        f'\n   Step {step_num}: generate_video(prompt="[continue description]", '
                        f"source_video=<previous_url>, use_extension_api=True)"
                        f"\n           → Returns {current_total}s merged video"
                    )

            extension_steps_str = "".join(extension_steps)

            media_hint = (
                f"\n\n[User selected video generation: "
                f"type={media_preferences.type}, "
                f"model_name={media_preferences.model_name}"
                f"{user_config}"
                f"{frame_context}"
                f"\n\n📹 LONG VIDEO ({duration_seconds}s) - USE EXTENSION API"
                f"\n"
                f"\n🎯 YOUR TASK: Generate a {duration_seconds}s video using the Extension API."
                f"\nThis requires {extensions_needed + 1} total API calls: 1 initial (8s) + {extensions_needed} extension(s)."
                f"\n"
                f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                f"\n📋 EXACT STEPS TO FOLLOW:"
                f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                f"\n"
                f'\n   Step 1: generate_video(prompt="[your detailed prompt]")'
                f"\n           → Returns 8s video URL (initial segment)"
                f"{extension_steps_str}"
                f"\n"
                f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                f"\n✅ KEY POINTS:"
                f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                f"\n• Extension API returns MERGED video (original + extension combined)"
                f"\n• NO concatenate_videos needed - each extension builds on the previous"
                f"\n• Audio coherence is maintained across extensions"
                f"\n• Always pass the LATEST video URL as source_video"
                f"\n• The prompt for extensions should describe how the scene CONTINUES"
                f"\n• Resolution: Extensions use 720p (API limitation)"
                + (
                    "\n• END FRAME: User provided end frame - set is_final_segment=True on last extension"
                    if has_end
                    else ""
                )
                + (
                    "\n• START FRAME: User's start frame is applied automatically to Step 1"
                    if has_start
                    else ""
                )
                + "\n\nSTART NOW: Call generate_video with your prompt for Step 1!]"
                + f"{storybook_hint}"
                + f"{audio_hint}"
                + f"{frame_hint}"
            )
        else:
            # Single segment hint
            media_hint = (
                f"\n\n[User selected video generation: "
                f"type={media_preferences.type}, "
                f"model_name={media_preferences.model_name}"
                f"{user_config}"
                f"{frame_context}"
                f"\n\n⚠️ IMPORTANT: Do NOT pass 'duration' parameter to generate_video - the user's duration setting ({video_settings.duration}) will be used automatically."
                f"\n\nYou MUST call the generate_video tool immediately with just the 'prompt' parameter.]"
                + f"{storybook_hint}"
                + f"{audio_hint}"
                + f"{frame_hint}"
            )

        return media_hint

    # ── Helper methods ────────────────────────────────────────────────

    async def _get_frame_public_url(
        self,
        frame: VideoFrameReference,
        db_session: AsyncSession,
    ) -> str | None:
        """Get the public URL for a video frame reference.

        HEIC/HEIF frames are converted to JPEG because the video generation
        API does not support HEIC and the LLM should never see a HEIC URL.
        Prefer the ``file_id`` path so HEIC detection via DB metadata works.
        """
        # Prefer file_id — it goes through _resolve_file_to_public_url which
        # handles HEIC conversion via DB metadata.
        file_id = frame.file_id or (
            frame.url if frame.url and not frame.url.startswith(("http://", "https://")) else None
        )
        if file_id:
            url = await self._resolve_file_to_public_url(file_id)
            if url:
                return url

        if frame.url and frame.url.startswith(("http://", "https://")):
            # Convert HEIC URLs on the fly
            url_path = frame.url.split("?")[0].lower()
            if url_path.endswith((".heic", ".heif")):
                converted = await self._convert_heic_url_to_jpeg(frame.url)
                if converted:
                    return converted
            return frame.url

        return None

    async def _resolve_file_to_public_url(self, file_id: str) -> str | None:
        """Resolve a file ID to its public URL, converting HEIC to JPEG."""
        from ii_agent.core.db import get_db_session_local

        try:
            async with get_db_session_local() as db:
                from ii_agent.files.dependencies import get_file_repository
                from ii_agent.sessions.dependencies import get_session_repository

                file_repo = get_file_repository()
                session_repo = get_session_repository()
                from ii_agent.files.service import FileService

                file_svc = FileService(file_repo=file_repo, session_repo=session_repo)

                file_data = await file_svc.get_file_by_id(db, file_id)
                if not file_data or not file_data.storage_path:
                    return None

                storage_path = file_data.storage_path
                public_url = get_storage().public_url(storage_path)

                logger.info(f"[VIDEO_HANDLER] Resolved file {file_id} -> {public_url}")
                return public_url
        except Exception as e:
            logger.warning(f"[VIDEO_HANDLER] Failed to get URL for file {file_id}: {e}")
            return None

    async def _convert_heic_storage_to_jpeg(self, file_id: str, source_path: str) -> str:
        """Read HEIC from storage, convert to JPEG, upload to public storage."""
        import io
        import anyio
        from ii_agent.agents.utils.heic import convert_heic_to_jpeg

        logger.info(f"[VIDEO_HANDLER] Converting HEIC frame {file_id} to JPEG")
        public_path = f"video_generation_frames/{file_id[:8]}.jpg"

        file_obj = await get_storage().read(source_path)
        heic_bytes = file_obj.read()
        file_obj.close()

        def _convert(data: bytes) -> bytes:
            jpeg_bytes, _ = convert_heic_to_jpeg(data)
            return jpeg_bytes

        jpeg_bytes = await anyio.to_thread.run_sync(lambda: _convert(heic_bytes))
        await get_storage().write(public_path, io.BytesIO(jpeg_bytes), "image/jpeg")
        return get_storage().public_url(public_path)

    async def _convert_heic_url_to_jpeg(self, heic_url: str) -> str | None:
        """Download HEIC from URL, convert to JPEG, upload to public storage."""
        import io
        import anyio
        import httpx
        import uuid as _uuid
        from ii_agent.agents.utils.heic import convert_heic_to_jpeg

        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
                resp = await client.get(heic_url)
                resp.raise_for_status()

            heic_bytes = resp.content

            def _convert(data: bytes) -> bytes:
                jpeg_bytes, _ = convert_heic_to_jpeg(data)
                return jpeg_bytes

            jpeg_bytes = await anyio.to_thread.run_sync(lambda: _convert(heic_bytes))
            fid = str(_uuid.uuid4())[:8]
            public_path = f"video_generation_frames/{fid}.jpg"
            await get_storage().write(public_path, io.BytesIO(jpeg_bytes), "image/jpeg")
            url = get_storage().public_url(public_path)
            logger.info(f"[VIDEO_HANDLER] Converted HEIC URL to JPEG: {url}")
            return url
        except Exception as e:
            logger.warning(f"[VIDEO_HANDLER] HEIC URL conversion failed: {e}")
            return None

    async def _copy_to_public_storage(
        self, file_id: str, source_path: str, content_type: str | None
    ) -> str:
        """Copy a file from private storage to public storage."""
        ext = source_path.rsplit(".", 1)[-1] if "." in source_path else "png"
        public_path = f"shared/{file_id[:8]}.{ext}"
        await get_storage().copy(source_path, public_path)
        return get_storage().public_url(public_path)

    async def _download_image_as_binary(self, url: str) -> Optional[BinaryContent]:
        """Download image from URL and return as BinaryContent."""
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
                response = await client.get(url)
                response.raise_for_status()

                content_type = response.headers.get("content-type", "")
                if ";" in content_type:
                    content_type = content_type.split(";")[0].strip()

                url_path = url.split("?")[0]
                filename = url_path.split("/")[-1]

                if not content_type or content_type == "application/octet-stream":
                    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
                    content_type = {
                        "png": "image/png",
                        "jpg": "image/jpeg",
                        "jpeg": "image/jpeg",
                        "gif": "image/gif",
                        "webp": "image/webp",
                        "heic": "image/heic",
                        "heif": "image/heif",
                    }.get(ext, "image/png")

                image_data = response.content
                if content_type and content_type.startswith("image/"):
                    try:
                        image_data, content_type = compress_image_for_provider(
                            image_data, content_type, DEFAULT_IMAGE_LIMIT
                        )
                    except Exception as e:
                        logger.warning(
                            f"[VIDEO_HANDLER] Failed to compress frame image: {e}, using original"
                        )

                return BinaryContent(
                    path=filename,
                    mime_type=content_type,
                    data=image_data,
                )
        except httpx.HTTPStatusError as e:
            logger.warning(
                f"[VIDEO_HANDLER] HTTP {e.response.status_code} downloading image: {url}"
            )
            return None
        except Exception as e:
            logger.warning(f"[VIDEO_HANDLER] Failed to download image: {e}")
            return None
