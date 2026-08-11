import base64
import binascii
import uuid
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Any, Literal

import yaml

from ii_agent_tools.integrations.video_generation import utils
from ii_agent_tools.integrations.video_generation.base import (
    BaseVideoGenerationClient,
    VideoGenerationResult,
    VideoReferenceImage,
)
from ii_agent_tools.integrations.video_generation.config import VideoGenerateConfig
from ii_agent_tools.integrations.video_generation.factory import (
    create_video_generation_client,
)
from ii_agent_tools.integrations.video_generation.minimax import (
    DEFAULT_MODEL as MINIMAX_DEFAULT_MODEL,
    MODEL_SUPPORTED_DURATIONS as MINIMAX_MODEL_SUPPORTED_DURATIONS,
    SUPPORTED_MODELS as MINIMAX_SUPPORTED_MODELS,
)
from ii_agent_tools.llm.client import LLMClient
from ii_agent_tools.logger import get_logger
from ii_agent_tools.storage.base import BaseStorage

logger = get_logger(__name__)

VIDEO_MODEL_CONFIG_PATH = (
    Path(__file__).resolve().parents[3] / "ii_agent" / "content" / "media" / "config" / "video.yaml"
)
VIDEO_MODEL_CONFIG_ALIASES = {
    "fal-ai/kling-video/o3/pro/reference-to-video": "fal-ai/kling-video/o3/pro/text-to-video",
    "fal-ai/kling-video/o3/pro/video-to-video/reference": "fal-ai/kling-video/o3/pro/text-to-video",
    "fal-ai/bytedance/seedance/v1.5/pro/image-to-video": "fal-ai/bytedance/seedance/v1.5/pro/text-to-video",
    "xai/grok-imagine-video/image-to-video": "xai/grok-imagine-video/text-to-video",
    "xai/grok-imagine-video/edit-video": "xai/grok-imagine-video/text-to-video",
    "fal-ai/sora-2/image-to-video/pro": "fal-ai/sora-2/text-to-video/pro",
}
DEFAULT_DIRECT_SEGMENT_DURATIONS = (4, 6, 8)
INLINE_FRAME_MIME_TYPES = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}
MINIMAX_MODEL_NAMES = {model_name.lower(): model_name for model_name in MINIMAX_SUPPORTED_MODELS}
MINIMAX_PROVIDER_ALIASES = {"minimax", "minimax-ai", "minimax_ai", "minimaxi"}


def _normalize_model_name(model_name: str | None) -> str:
    return (model_name or "").strip().lower()


@lru_cache(maxsize=1)
def _load_video_model_configs() -> dict[str, dict[str, Any]]:
    if not VIDEO_MODEL_CONFIG_PATH.exists():
        logger.warning(
            "[VideoGenerationService] Video model config not found: %s",
            VIDEO_MODEL_CONFIG_PATH,
        )
        return {}

    try:
        with VIDEO_MODEL_CONFIG_PATH.open("r", encoding="utf-8") as handle:
            config = yaml.safe_load(handle) or {}
    except Exception:
        logger.exception(
            "[VideoGenerationService] Failed to load video model config from %s",
            VIDEO_MODEL_CONFIG_PATH,
        )
        return {}

    models = config.get("models")
    if not isinstance(models, list):
        return {}

    model_configs: dict[str, dict[str, Any]] = {}
    for model in models:
        if not isinstance(model, dict):
            continue
        model_name = model.get("model_name")
        if isinstance(model_name, str) and model_name.strip():
            model_configs[model_name.strip().lower()] = model
    return model_configs


def _get_model_duration_seconds(
    model_name: str | None,
    *,
    field_name: str,
) -> list[int]:
    normalized_model_name = _normalize_model_name(model_name)
    if not normalized_model_name:
        return []

    minimax_model_name = MINIMAX_MODEL_NAMES.get(normalized_model_name)
    if minimax_model_name:
        return list(MINIMAX_MODEL_SUPPORTED_DURATIONS[minimax_model_name])

    lookup_model_name = VIDEO_MODEL_CONFIG_ALIASES.get(
        normalized_model_name,
        normalized_model_name,
    )
    model_config = _load_video_model_configs().get(lookup_model_name)
    if not model_config:
        return []

    durations: list[int] = []
    for duration_label in model_config.get(field_name, []):
        if not isinstance(duration_label, str):
            continue
        normalized_duration = duration_label.strip().lower()
        if normalized_duration.endswith("s"):
            normalized_duration = normalized_duration[:-1]
        try:
            durations.append(int(float(normalized_duration)))
        except ValueError:
            continue
    return durations


def is_supported_video_model(model_name: str | None) -> bool:
    normalized_model_name = _normalize_model_name(model_name)
    if not normalized_model_name:
        return False
    if "veo-3" in normalized_model_name:
        return True
    if normalized_model_name in MINIMAX_MODEL_NAMES:
        return True

    lookup_model_name = VIDEO_MODEL_CONFIG_ALIASES.get(
        normalized_model_name,
        normalized_model_name,
    )
    return lookup_model_name in _load_video_model_configs()


def get_model_direct_supported_duration_seconds(model_name: str | None) -> list[int]:
    direct_durations = _get_model_duration_seconds(
        model_name,
        field_name="direct_supported_durations",
    )
    if direct_durations:
        return direct_durations
    configured_durations = _get_model_duration_seconds(
        model_name,
        field_name="supported_durations",
    )
    if configured_durations:
        return configured_durations
    return list(DEFAULT_DIRECT_SEGMENT_DURATIONS)


def get_model_supported_duration_seconds(model_name: str | None) -> list[int]:
    configured_durations = _get_model_duration_seconds(
        model_name,
        field_name="supported_durations",
    )
    if configured_durations:
        return configured_durations
    return get_model_direct_supported_duration_seconds(model_name)


def get_max_direct_video_duration_seconds(model_name: str | None) -> int:
    direct_durations = get_model_direct_supported_duration_seconds(model_name)
    if direct_durations:
        return max(direct_durations)
    return max(DEFAULT_DIRECT_SEGMENT_DURATIONS)


class VideoGenerationService:
    """Video generation service with provider-per-request support."""

    def __init__(
        self,
        video_generate_config: VideoGenerateConfig,
        llm_client: LLMClient | None,
        storage: BaseStorage,
    ):
        self._config = video_generate_config
        self._default_client: BaseVideoGenerationClient | None = None
        self._client_cache: dict[str, BaseVideoGenerationClient] = {}
        self.llm_client = llm_client
        self.storage = storage
        self.base_temp_dir = Path("./tmp/video_generation")
        self.base_temp_dir.mkdir(parents=True, exist_ok=True)
        logger.info(
            "Initialized video generation temp directory",
            extra={"temp_dir": str(self.base_temp_dir.absolute())},
        )

    async def _normalize_frame_input(
        self,
        *,
        frame_name: str,
        frame_url: str | None,
        frame_base64: str | None,
        frame_mime_type: str | None,
        user_id: uuid.UUID | None,
    ) -> str | None:
        """Normalize inline frame content to a storage-backed public URL."""
        if frame_url and frame_base64:
            raise ValueError(f"{frame_name} accepts either a URL or base64 content, not both")
        if frame_url:
            return frame_url
        if not frame_base64:
            return None

        encoded_payload = frame_base64.strip()
        mime_type = frame_mime_type

        if encoded_payload.startswith("data:"):
            header, separator, encoded_payload = encoded_payload.partition(",")
            if not separator or ";base64" not in header:
                raise ValueError(f"{frame_name}_base64 must be raw base64 or a base64 data URL")
            data_url_mime_type = header[5:].split(";", 1)[0]
            if mime_type and mime_type != data_url_mime_type:
                raise ValueError(f"{frame_name}_mime_type does not match the data URL MIME type")
            mime_type = data_url_mime_type

        if not mime_type:
            raise ValueError(
                f"{frame_name}_mime_type is required when {frame_name}_base64 is provided"
            )

        extension = INLINE_FRAME_MIME_TYPES.get(mime_type)
        if not extension:
            raise ValueError(
                f"{frame_name}_mime_type must be one of: {', '.join(INLINE_FRAME_MIME_TYPES)}"
            )

        try:
            frame_bytes = base64.b64decode(encoded_payload, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError(f"{frame_name}_base64 must be valid base64") from exc

        if not frame_bytes:
            raise ValueError(f"{frame_name}_base64 must not be empty")

        blob_path = utils.construct_blob_path(
            user_id,
            f"{frame_name}_{uuid.uuid4().hex[:8]}.{extension}",
        )
        await self.storage.write(BytesIO(frame_bytes), blob_path, mime_type)
        public_url = self.storage.get_public_url(blob_path)
        logger.info(
            "[VideoGenerationService] Uploaded inline %s to %s",
            frame_name,
            public_url,
        )
        return public_url

    def _get_client(self, provider: str | None = None) -> BaseVideoGenerationClient:
        """Get or create a video generation client based on provider."""
        if not provider:
            if self._default_client is None:
                self._default_client = create_video_generation_client(self._config)
            return self._default_client

        if provider in self._client_cache:
            return self._client_cache[provider]

        client = create_video_generation_client(
            self._config,
            provider=provider,
        )
        self._client_cache[provider] = client
        return client

    async def _generate_with_extension_api(
        self,
        video_generation_client: BaseVideoGenerationClient,
        prompt: str,
        model_name: str,
        aspect_ratio: Literal["auto", "1:1", "3:4", "4:3", "9:16", "16:9", "21:9"],
        duration_seconds: int,
        resolution: str,
        audio_included: bool,
        start_frame: str | None,
        session_id: str | None,
        negative_prompt: str | None,
        person_generation: Literal["allow_all", "allow_adult"] | None,
        seed: int | None,
        reference_images: list[VideoReferenceImage] | None,
        provider_payload: dict[str, Any] | None,
        request_mode: str | None,
    ) -> VideoGenerationResult:
        """Generate long video using Veo's video extension API."""
        logger.info(f"[VideoGenerationService] Using extension API for {duration_seconds}s video")

        initial_duration = min(8, duration_seconds)
        remaining_duration = duration_seconds - initial_duration
        total_cost = 0.0

        logger.info(f"[VideoGenerationService] Generating initial {initial_duration}s segment")
        result = await video_generation_client.generate_video(
            prompt=prompt,
            model_name=model_name,
            aspect_ratio=aspect_ratio,
            duration_seconds=initial_duration,
            resolution=resolution,
            audio_included=audio_included,
            start_frame=start_frame,
            end_frame=None,
            session_id=session_id,
            negative_prompt=negative_prompt,
            person_generation=person_generation,
            seed=seed,
            reference_images=reference_images,
            provider_payload=provider_payload,
            request_mode=request_mode,
        )

        if not result.url or result.error:
            error_msg = result.error or "Initial segment generation failed"
            logger.error(f"[VideoGenerationService] Extension API failed: {error_msg}")
            return result

        total_cost += result.cost

        if not result.storage_path:
            logger.warning(
                "[VideoGenerationService] No storage_path returned, cannot use extension API"
            )
            return result

        output_bucket = getattr(video_generation_client, "output_bucket", None)
        if not output_bucket:
            logger.warning(
                "[VideoGenerationService] No output_bucket configured, cannot use extension API"
            )
            return result

        current_video_uri = f"gs://{output_bucket}/{result.storage_path}"
        current_duration = initial_duration

        extension_count = 0
        max_extensions = 20

        while remaining_duration > 0 and extension_count < max_extensions:
            extension_seconds = min(7, remaining_duration)
            extension_count += 1

            logger.info(
                f"[VideoGenerationService] Extension {extension_count}: "
                f"adding {extension_seconds}s (current: {current_duration}s, "
                f"remaining: {remaining_duration}s)"
            )

            continuation_prompt = (
                f"Continue the video seamlessly. Maintain the same visual style, "
                f"camera movement, and audio atmosphere. "
                f"Original scene: {prompt}"
            )

            extension_result = await video_generation_client.extend_video(
                video_uri=current_video_uri,
                prompt=continuation_prompt,
                extension_seconds=extension_seconds,
                generate_audio=audio_included,
            )

            if not extension_result.url or extension_result.error:
                error_msg = extension_result.error or "Extension failed"
                logger.warning(
                    f"[VideoGenerationService] Extension {extension_count} failed: {error_msg}"
                )
                break

            total_cost += extension_result.cost

            if extension_result.storage_path:
                current_video_uri = f"gs://{output_bucket}/{extension_result.storage_path}"
            current_duration += extension_seconds
            remaining_duration -= extension_seconds

            result = extension_result

        logger.info(
            f"[VideoGenerationService] Extension complete: {current_duration}s total, "
            f"{extension_count} extensions, cost: ${total_cost:.2f}"
        )

        result.cost = total_cost
        return result

    async def _generate_direct_video(
        self,
        *,
        video_generation_client: BaseVideoGenerationClient,
        prompt: str,
        model_name: str,
        aspect_ratio: Literal["auto", "1:1", "3:4", "4:3", "9:16", "16:9", "21:9"],
        duration_seconds: int,
        resolution: str,
        audio_included: bool,
        multishot_mode: bool,
        start_frame: str | None,
        end_frame: str | None,
        session_id: str | None,
        negative_prompt: str | None,
        person_generation: Literal["allow_all", "allow_adult"] | None,
        seed: int | None,
        reference_images: list[VideoReferenceImage] | None,
        provider_payload: dict[str, Any] | None,
        request_mode: str | None,
        provider: str | None,
    ) -> VideoGenerationResult:
        try:
            return await video_generation_client.generate_video(
                prompt=prompt,
                model_name=model_name,
                aspect_ratio=aspect_ratio,
                duration_seconds=duration_seconds,
                resolution=resolution,
                audio_included=audio_included,
                multishot_mode=multishot_mode,
                start_frame=start_frame,
                end_frame=end_frame,
                session_id=session_id,
                negative_prompt=negative_prompt,
                person_generation=person_generation,
                seed=seed,
                reference_images=reference_images,
                provider_payload=provider_payload,
                request_mode=request_mode,
            )
        except Exception:
            logger.exception(
                "Video generation failed",
                extra={
                    "prompt": prompt,
                    "duration_seconds": duration_seconds,
                    "aspect_ratio": aspect_ratio,
                    "model_name": model_name,
                    "provider": provider,
                },
            )
            raise

    async def generate_video(
        self,
        prompt: str,
        model_name: str | None = "veo-3.1-generate-preview",
        provider: str | None = None,
        aspect_ratio: Literal["auto", "1:1", "3:4", "4:3", "9:16", "16:9", "21:9"] = "16:9",
        duration_seconds: int = 5,
        resolution: str = "720p",
        audio_included: bool = False,
        multishot_mode: bool = True,
        # Frame URLs (passed directly to Veo API)
        start_frame: str | None = None,
        end_frame: str | None = None,
        start_frame_base64: str | None = None,
        start_frame_mime_type: str | None = None,
        end_frame_base64: str | None = None,
        end_frame_mime_type: str | None = None,
        session_id: str | None = None,
        negative_prompt: str | None = None,
        person_generation: Literal["allow_all", "allow_adult"] | None = None,
        seed: int | None = None,
        reference_images: list[VideoReferenceImage] | None = None,
        use_extension_api: bool = True,
        provider_payload: dict[str, Any] | None = None,
        request_mode: str | None = None,
        user_id: uuid.UUID | None = None,
    ) -> VideoGenerationResult:
        """
        Generate video with support for long durations.

        Args:
            start_frame: URL of start frame image (https:// or gs://)
            end_frame: URL of end frame image (https:// or gs://)
        """
        start_frame = await self._normalize_frame_input(
            frame_name="start_frame",
            frame_url=start_frame,
            frame_base64=start_frame_base64,
            frame_mime_type=start_frame_mime_type,
            user_id=user_id,
        )
        end_frame = await self._normalize_frame_input(
            frame_name="end_frame",
            frame_url=end_frame,
            frame_base64=end_frame_base64,
            frame_mime_type=end_frame_mime_type,
            user_id=user_id,
        )

        provider_key = (provider or "").lower()
        if model_name is None:
            if provider_key in MINIMAX_PROVIDER_ALIASES:
                model_name = self._config.minimax_model_name or MINIMAX_DEFAULT_MODEL
            elif provider_key not in {"fal", "fal-ai", "fal_ai"}:
                model_name = "veo-3.1-generate-preview"
        if not is_supported_video_model(model_name):
            raise ValueError(f"Unsupported video model: {model_name}")

        video_generation_client = self._get_client(provider=provider)
        supports_long_generation = getattr(
            video_generation_client, "supports_long_generation", True
        )
        supported_durations = get_model_supported_duration_seconds(model_name)
        direct_supported_durations = get_model_direct_supported_duration_seconds(model_name)
        max_direct_duration_seconds = get_max_direct_video_duration_seconds(model_name)

        logger.info(
            f"[VideoGenerationService] Request: duration_seconds={duration_seconds}, "
            f"max_direct_duration_seconds={max_direct_duration_seconds}, "
            f"supports_long_generation={supports_long_generation}, "
            f"use_extension_api={use_extension_api}, audio_included={audio_included}, "
            f"llm_client={self.llm_client is not None}"
        )

        if duration_seconds <= max_direct_duration_seconds:
            direct_duration_seconds = utils.get_nearest_valid_duration(
                duration_seconds,
                allowed_durations=direct_supported_durations,
            )
            return await self._generate_direct_video(
                video_generation_client=video_generation_client,
                prompt=prompt,
                model_name=model_name,
                aspect_ratio=aspect_ratio,
                duration_seconds=direct_duration_seconds,
                resolution=resolution,
                audio_included=audio_included,
                multishot_mode=multishot_mode,
                start_frame=start_frame,
                end_frame=end_frame,
                session_id=session_id,
                negative_prompt=negative_prompt,
                person_generation=person_generation,
                seed=seed,
                reference_images=reference_images,
                provider_payload=provider_payload,
                request_mode=request_mode,
                provider=provider,
            )

        if supported_durations and duration_seconds not in supported_durations:
            raise ValueError(
                f"Requested duration {duration_seconds}s is not supported for model {model_name}."
            )

        # For long videos, choose between extension API and concatenation
        if (
            use_extension_api
            and audio_included
            and getattr(video_generation_client, "supports_extension_api", False)
        ):
            return await self._generate_with_extension_api(
                video_generation_client=video_generation_client,
                prompt=prompt,
                model_name=model_name,
                aspect_ratio=aspect_ratio,
                duration_seconds=duration_seconds,
                resolution=resolution,
                audio_included=audio_included,
                start_frame=start_frame,
                session_id=session_id,
                negative_prompt=negative_prompt,
                person_generation=person_generation,
                seed=seed,
                reference_images=reference_images,
                provider_payload=provider_payload,
                request_mode=request_mode,
            )

        durations = utils.split_long_duration(
            duration_seconds,
            allowed_durations=direct_supported_durations,
            allow_approximate=False,
        )
        if not durations or sum(durations) != duration_seconds or len(durations) == 1:
            if not supports_long_generation:
                direct_duration_seconds = utils.get_nearest_valid_duration(
                    min(duration_seconds, max_direct_duration_seconds),
                    allowed_durations=direct_supported_durations,
                )
                return await self._generate_direct_video(
                    video_generation_client=video_generation_client,
                    prompt=prompt,
                    model_name=model_name,
                    aspect_ratio=aspect_ratio,
                    duration_seconds=direct_duration_seconds,
                    resolution=resolution,
                    audio_included=audio_included,
                    multishot_mode=multishot_mode,
                    start_frame=start_frame,
                    end_frame=end_frame,
                    session_id=session_id,
                    negative_prompt=negative_prompt,
                    person_generation=person_generation,
                    seed=seed,
                    reference_images=reference_images,
                    provider_payload=provider_payload,
                    request_mode=request_mode,
                    provider=provider,
                )
            raise ValueError(
                f"Requested duration {duration_seconds}s is not supported for model {model_name}."
            )

        n_scenes = len(durations)
        logger.info(
            f"[VideoGenerationService] Split into {n_scenes} scenes with durations: {durations}"
        )

        scenes = [prompt] * n_scenes
        scene_breakdown_cost = 0.0
        if self.llm_client:
            try:
                scene_breakdown_prompt = utils.get_scene_breakdown_prompt(prompt, n_scenes)
                scene_breakdown_response = await self.llm_client.generate(scene_breakdown_prompt)
                scene_breakdown_content = scene_breakdown_response.content
                scene_breakdown_cost = scene_breakdown_response.cost
                parsed_scenes = utils.parse_scenes(scene_breakdown_content)
                if parsed_scenes:
                    scenes = parsed_scenes
                else:
                    logger.warning(
                        "LLM returned no scenes for video generation; reusing the original prompt for each segment"
                    )
            except Exception:
                logger.exception(
                    "Failed to generate scene breakdown; reusing the original prompt for each segment",
                    extra={"prompt": prompt, "duration_seconds": duration_seconds},
                )

        if len(scenes) != n_scenes:
            logger.warning(
                "LLM returned %s scenes but expected %s. Adjusting...",
                len(scenes),
                n_scenes,
            )
            if len(scenes) < n_scenes:
                while len(scenes) < n_scenes:
                    scenes.append(scenes[-1] if scenes else prompt)
            else:
                scenes = scenes[:n_scenes]

        logger.info("-" * 100)
        logger.info("Scenes and durations:")
        for i, scene in enumerate(scenes):
            logger.info(f"- Scene {i} duration {durations[i]}(s): {scene}")
        logger.info("-" * 100)

        temp_video_dir = self.base_temp_dir / uuid.uuid4().hex
        temp_video_dir.mkdir(parents=True, exist_ok=True)

        scene_video_paths = []

        # Generate first scene
        try:
            scene_0_end_frame = end_frame if n_scenes == 1 else None
            logger.info(f"[VideoGenerationService] Generating scene 0 ({durations[0]}s)...")
            scene_0_result = await video_generation_client.generate_video(
                prompt=scenes[0],
                model_name=model_name,
                aspect_ratio=aspect_ratio,
                duration_seconds=durations[0],
                resolution=resolution,
                audio_included=audio_included,
                start_frame=start_frame,
                end_frame=scene_0_end_frame,
                session_id=session_id,
                negative_prompt=negative_prompt,
                person_generation=person_generation,
                seed=seed,
                reference_images=reference_images,
                provider_payload=provider_payload,
                request_mode=request_mode,
            )

            if not scene_0_result.url:
                error_msg = scene_0_result.error or "no video URL returned"
                raise RuntimeError(f"Scene 0 video generation failed - {error_msg}")

            logger.info(
                f"[VideoGenerationService] Scene 0 generated successfully: {scene_0_result.url}"
            )

            scene_0_path = temp_video_dir / "scene_0.mp4"
            logger.info(f"[VideoGenerationService] Downloading scene 0 to {scene_0_path}...")
            await utils.download_video(scene_0_result.url, scene_0_path)
            logger.info(
                f"[VideoGenerationService] Scene 0 downloaded: {scene_0_path.stat().st_size} bytes"
            )
            scene_video_paths.append(scene_0_path)
        except Exception:
            logger.exception("Failed to generate first scene", extra={"scene": scenes[0]})
            raise

        cost = scene_0_result.cost + scene_breakdown_cost

        # Generate subsequent scenes
        for i, scene in enumerate(scenes[1:], 1):
            logger.info(
                f"[VideoGenerationService] Generating scene {i} of {n_scenes} ({durations[i]}s)..."
            )
            prev_video_path = scene_video_paths[-1]
            last_frame_path = temp_video_dir / f"last_frame_{i - 1}.png"
            logger.info(f"[VideoGenerationService] Extracting last frame from {prev_video_path}...")
            await utils.extract_last_frame(prev_video_path, last_frame_path)

            if not last_frame_path.exists():
                raise RuntimeError(f"Failed to extract last frame from {prev_video_path}")
            logger.info(
                f"[VideoGenerationService] Last frame extracted: {last_frame_path.stat().st_size} bytes"
            )

            # Upload extracted frame to GCS and use URL
            frame_blob_path = utils.construct_blob_path(
                user_id, f"frame_{uuid.uuid4().hex[:8]}.png"
            )
            await self.storage.write_from_local_path(
                str(last_frame_path), frame_blob_path, "image/png"
            )
            last_frame_url = self.storage.get_public_url(frame_blob_path)
            logger.info(f"[VideoGenerationService] Uploaded frame to: {last_frame_url}")

            try:
                is_last_scene = i == n_scenes - 1
                scene_end_frame = end_frame if is_last_scene else None

                scene_video_result = await video_generation_client.generate_video(
                    prompt=scene,
                    model_name=model_name,
                    aspect_ratio=aspect_ratio,
                    duration_seconds=durations[i],
                    resolution=resolution,
                    audio_included=audio_included,
                    start_frame=last_frame_url,  # URL from uploaded frame
                    end_frame=scene_end_frame,
                    session_id=session_id,
                    negative_prompt=negative_prompt,
                    person_generation=person_generation,
                    seed=seed,
                    reference_images=reference_images,
                    provider_payload=provider_payload,
                    request_mode=request_mode,
                )
            except Exception:
                logger.exception("Failed to generate scene", extra={"scene": scene})
                raise

            if not scene_video_result.url:
                error_msg = scene_video_result.error or "no video URL returned"
                raise RuntimeError(f"Scene {i} video generation failed - {error_msg}")

            logger.info(
                f"[VideoGenerationService] Scene {i} generated successfully: {scene_video_result.url}"
            )

            scene_video_path = temp_video_dir / f"scene_{i}.mp4"
            logger.info(f"[VideoGenerationService] Downloading scene {i} to {scene_video_path}...")
            await utils.download_video(scene_video_result.url, scene_video_path)
            logger.info(
                f"[VideoGenerationService] Scene {i} downloaded: {scene_video_path.stat().st_size} bytes"
            )

            scene_video_paths.append(scene_video_path)
            cost += scene_video_result.cost

        # Merge scenes
        logger.info(f"[VideoGenerationService] Merging {len(scene_video_paths)} scenes...")
        merged_video_path = temp_video_dir / "merged_video.mp4"
        await utils.merge_videos(scene_video_paths, merged_video_path, temp_video_dir)
        logger.info(
            f"[VideoGenerationService] Merge complete: {merged_video_path.stat().st_size} bytes"
        )

        name = utils.generate_unique_video_name()
        blob_path = utils.construct_blob_path(user_id, f"{name}.mp4")
        try:
            await self.storage.write_from_local_path(
                str(merged_video_path),
                blob_path,
                "video/mp4",
            )
        except Exception:
            logger.exception("Failed to upload merged video", extra={"blob_path": blob_path})
            raise

        public_url = self.storage.get_public_url(blob_path)
        file_name = f"{name}.mp4"

        return VideoGenerationResult(
            url=public_url,
            mime_type="video/mp4",
            size=merged_video_path.stat().st_size,
            cost=cost,
            storage_path=blob_path,
            file_name=file_name,
        )

    async def extend_video(
        self,
        source_video_url: str,
        prompt: str,
        extension_seconds: int = 7,
        generate_audio: bool = True,
        person_generation: Literal["allow_all", "allow_adult"] | None = None,
        end_frame: str | None = None,
        provider: str | None = None,
        user_id: uuid.UUID | None = None,
    ) -> VideoGenerationResult:
        """Extend an existing video using Veo's video extension API.

        Args:
            person_generation: Person generation mode ("allow_all" or "allow_adult")
            end_frame: URL of end frame image (https:// or gs://)
        """
        video_generation_client = self._get_client(provider=provider)

        extension_seconds = min(extension_seconds, 7)

        if not hasattr(video_generation_client, "extend_video"):
            return VideoGenerationResult(
                url=None,
                mime_type=None,
                size=0,
                cost=0,
                error="Video extension not supported by current provider",
            )

        video_uri = source_video_url
        if source_video_url.startswith("http"):
            logger.info(
                f"[VideoGenerationService] Downloading source video for extension: {source_video_url}"
            )
            try:
                name = utils.generate_unique_video_name()
                blob_path = utils.construct_blob_path(user_id, f"{name}_source.mp4")
                await self.storage.write_from_url(source_video_url, blob_path, "video/mp4")

                output_bucket = getattr(video_generation_client, "output_bucket", None)
                if not output_bucket:
                    output_bucket = getattr(self.storage, "bucket_name", None)

                if output_bucket:
                    video_uri = f"gs://{output_bucket}/{blob_path}"
                    logger.info(f"[VideoGenerationService] Uploaded source video to: {video_uri}")
                else:
                    return VideoGenerationResult(
                        url=None,
                        mime_type=None,
                        size=0,
                        cost=0,
                        error="Could not determine GCS bucket for video extension",
                    )
            except Exception as e:
                logger.error(f"[VideoGenerationService] Failed to prepare source video: {e}")
                return VideoGenerationResult(
                    url=None,
                    mime_type=None,
                    size=0,
                    cost=0,
                    error=f"Failed to prepare source video: {str(e)}",
                )

        logger.info(
            f"[VideoGenerationService] Extending video: {video_uri} by {extension_seconds}s"
        )

        try:
            result = await video_generation_client.extend_video(
                video_uri=video_uri,
                prompt=prompt,
                extension_seconds=extension_seconds,
                generate_audio=generate_audio,
                person_generation=person_generation,
                end_frame=end_frame,
            )
            return result
        except Exception as e:
            logger.exception(
                "Video extension failed",
                extra={
                    "source_video_url": source_video_url,
                    "extension_seconds": extension_seconds,
                },
            )
            return VideoGenerationResult(
                url=None,
                mime_type=None,
                size=0,
                cost=0,
                error=f"Video extension failed: {str(e)}",
            )
