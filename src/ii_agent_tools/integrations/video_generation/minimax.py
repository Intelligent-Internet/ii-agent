"""
Native MiniMax implementation of the video generation client.

Unlike the FAL client, which reaches MiniMax models indirectly through a
third-party proxy, this client talks to the first-party MiniMax video
generation REST API directly:

    * v2 submit/poll -> POST /v2/video_generation, GET /v2/query/video_generation/{task_id}
    * v1 submit/poll -> POST /v1/video_generation, GET /v1/query/video_generation
    * v1 retrieve    -> GET /v1/files/retrieve?file_id=...

Both the global (``api.minimax.io``) and China (``api.minimaxi.com``) hosts are
supported. The client selects the API version from the model, covers text and
image inputs, polls the matching task endpoint, and downloads the result.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from io import BytesIO
from typing import Any, Literal
from urllib.parse import urlparse

import anyio
import httpx

from ii_agent.core.storage.path_resolver import path_resolver
from .base import (
    BaseVideoGenerationClient,
    VideoGenerationResult,
    VideoReferenceImage,
)


DEFAULT_BASE_URL = "https://api.minimax.io/v1"
DEFAULT_MODEL = "MiniMax-H3"

# Models exposed by the native MiniMax video generation API.
SUPPORTED_MODELS = (
    "MiniMax-H3",
    "MiniMax-Hailuo-2.3",
    "MiniMax-Hailuo-2.3-Fast",
    "MiniMax-Hailuo-02",
    "T2V-01-Director",
    "T2V-01",
    "I2V-01-Director",
    "I2V-01-live",
    "I2V-01",
)
V2_MODELS = frozenset({"MiniMax-H3"})
MODEL_SUPPORTED_DURATIONS = {
    "MiniMax-H3": tuple(range(4, 16)),
    "MiniMax-Hailuo-2.3": (6, 10),
    "MiniMax-Hailuo-2.3-Fast": (6, 10),
    "MiniMax-Hailuo-02": (6, 10),
    "T2V-01-Director": (6,),
    "T2V-01": (6,),
    "I2V-01-Director": (6,),
    "I2V-01-live": (6,),
    "I2V-01": (6,),
}

# Request fields accepted by each operation (native API allow-lists).
_TEXT_TO_VIDEO_FIELDS = (
    "model",
    "prompt",
    "prompt_optimizer",
    "fast_pretreatment",
    "duration",
    "resolution",
    "callback_url",
)
_IMAGE_TO_VIDEO_FIELDS = (
    "model",
    "first_frame_image",
    "prompt",
    "prompt_optimizer",
    "fast_pretreatment",
    "duration",
    "resolution",
    "callback_url",
)
_V2_PASSTHROUGH_FIELDS = frozenset({"callback_url", "aigc_watermark"})
_V2_CONTENT_TYPES = frozenset({"text", "image_url", "video_url", "audio_url"})
_V2_CONTENT_ROLES = frozenset(
    {"first_frame", "last_frame", "reference_image", "reference_video", "reference_audio"}
)
_V2_FRAME_ROLES = frozenset({"first_frame", "last_frame"})
_V2_REFERENCE_ROLES = frozenset({"reference_image", "reference_video", "reference_audio"})
_V2_RATIO_VALUES = frozenset({"adaptive", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16"})
_V2_MAX_REQUEST_BYTES = 64 * 1024 * 1024

# Task states returned by the query endpoint.
_SUCCESS_STATUS = "Success"
_FAILURE_STATUSES = frozenset({"Fail"})
_V2_SUCCESS_STATUS = "succeeded"
_V2_FAILURE_STATUSES = frozenset({"failed", "cancelled"})


class MiniMaxVideoGenerationClient(BaseVideoGenerationClient):
    """Native MiniMax video generation client (text-to-video and image-to-video)."""

    supports_long_generation: bool = False
    supports_extension_api: bool = False

    polling_interval_seconds: int = 5
    max_wait_time_seconds: int = 600  # 10 minutes for video generation

    def __init__(
        self,
        api_key: str,
        model_name: str | None = None,
        base_url: str | None = None,
        group_id: str | None = None,
        output_bucket: str | None = None,
        project_id: str | None = None,
        custom_domain: str | None = None,
    ):
        """
        Initialize the native MiniMax video generation client.

        Args:
            api_key: MiniMax API key used as a Bearer token.
            model_name: Default model when a request does not specify one.
            base_url: ``/v1`` root of the regional host (global or China).
            group_id: Optional GroupId, forwarded as a query parameter when set.
            output_bucket: GCS bucket for storing rendered videos.
            project_id: GCP project id (kept for parity with other clients).
            custom_domain: Custom domain for building public URLs.
        """
        self.api_key = api_key
        self.model_name = model_name
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.group_id = group_id or os.getenv("VIDEO_GENERATE_MINIMAX_GROUP_ID")
        self.project_id = project_id
        self.output_bucket = output_bucket or os.getenv("VIDEO_GENERATE_GCS_OUTPUT_BUCKET")
        self.custom_domain = custom_domain or os.getenv("CUSTOM_DOMAIN")
        # Initialize GCS bucket if configured
        self.bucket = None
        if self.output_bucket:
            try:
                from google.cloud import storage

                gcs_client = storage.Client()
                self.bucket = gcs_client.bucket(self.output_bucket)
            except Exception:
                pass  # GCS not available, upload will raise a clear error later

    def _resolve_model_name(self, model_name: str | None) -> str:
        """Resolve the model, falling back to the configured or default model."""
        resolved_model = model_name or self.model_name or DEFAULT_MODEL
        if resolved_model not in SUPPORTED_MODELS:
            raise ValueError(f"Unsupported MiniMax video model: {resolved_model}")
        return resolved_model

    def _version_base_url(self, api_version: str) -> str:
        """Return the configured regional base URL with the requested API version."""
        base_url = self.base_url
        if base_url.endswith(("/v1", "/v2")):
            base_url = base_url.rsplit("/", 1)[0]
        return f"{base_url}/{api_version}"

    @property
    def _is_cn_region(self) -> bool:
        return urlparse(self.base_url).hostname == "api.minimaxi.com"

    def _build_payload(
        self,
        *,
        model: str,
        prompt: str,
        first_frame_image: str | None,
        duration_seconds: int | None,
        resolution: str | None,
        provider_payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Build the video generation request body from the native field set."""
        image_to_video = bool(first_frame_image)
        allowed = _IMAGE_TO_VIDEO_FIELDS if image_to_video else _TEXT_TO_VIDEO_FIELDS

        payload: dict[str, Any] = {"model": model}
        if image_to_video:
            payload["first_frame_image"] = first_frame_image
            if prompt:
                payload["prompt"] = prompt
        else:
            payload["prompt"] = prompt

        if duration_seconds and duration_seconds > 0:
            payload["duration"] = int(duration_seconds)

        # MiniMax expects resolution tokens such as "768P"/"1080P". Only forward a
        # value that already matches that shape so we never invent one.
        if resolution and resolution.endswith("P") and resolution[:-1].isdigit():
            payload["resolution"] = resolution

        # Raw passthrough for any remaining native request fields
        # (e.g. prompt_optimizer, fast_pretreatment, resolution, callback_url).
        if isinstance(provider_payload, dict):
            for key, value in provider_payload.items():
                if key in allowed and value is not None:
                    payload[key] = value

        return payload

    def _build_v2_content(
        self,
        *,
        prompt: str,
        first_frame_image: str | None,
        last_frame_image: str | None,
        reference_images: list[VideoReferenceImage] | None,
        provider_payload: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        raw_content = provider_payload.get("content") if provider_payload else None
        if raw_content is not None:
            if not isinstance(raw_content, list):
                raise ValueError("MiniMax-H3 content must be a list")
            content = [dict(item) for item in raw_content if isinstance(item, dict)]
            if len(content) != len(raw_content):
                raise ValueError("MiniMax-H3 content items must be objects")
        else:
            content = [{"type": "text", "text": prompt}]
            if first_frame_image:
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": first_frame_image},
                        "role": "first_frame",
                    }
                )
            if last_frame_image:
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": last_frame_image},
                        "role": "last_frame",
                    }
                )
            for reference_image in reference_images or []:
                if reference_image.url:
                    content.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": reference_image.url},
                            "role": "reference_image",
                        }
                    )

        text_items = [item for item in content if item.get("type") == "text"]
        for item in text_items:
            text = item.get("text")
            if not isinstance(text, str) or not text.strip():
                raise ValueError("MiniMax-H3 content requires a non-empty text item")
            if len(text) > 7000:
                raise ValueError("MiniMax-H3 text content must not exceed 7000 characters")
        if not text_items:
            raise ValueError("MiniMax-H3 content requires a non-empty text item")

        roles: set[str] = set()
        for item in content:
            content_type = item.get("type")
            if content_type not in _V2_CONTENT_TYPES:
                raise ValueError(f"Unsupported MiniMax-H3 content type: {content_type}")
            role = item.get("role")
            if role is not None:
                if role not in _V2_CONTENT_ROLES:
                    raise ValueError(f"Unsupported MiniMax-H3 content role: {role}")
                roles.add(role)
            if content_type != "text":
                media = item.get(content_type)
                if not isinstance(media, dict) or not media.get("url"):
                    raise ValueError(f"MiniMax-H3 {content_type} content requires a URL")

        if roles & _V2_FRAME_ROLES and roles & _V2_REFERENCE_ROLES:
            raise ValueError("MiniMax-H3 frame and reference roles cannot be mixed")
        if "reference_audio" in roles and not roles & {"reference_image", "reference_video"}:
            raise ValueError("MiniMax-H3 reference audio requires a reference image or video")
        return content

    def _build_v2_payload(
        self,
        *,
        model: str,
        prompt: str,
        first_frame_image: str | None,
        last_frame_image: str | None,
        reference_images: list[VideoReferenceImage] | None,
        duration_seconds: int,
        aspect_ratio: str,
        provider_payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not 4 <= duration_seconds <= 15:
            raise ValueError("MiniMax-H3 duration must be between 4 and 15 seconds")

        content = self._build_v2_content(
            prompt=prompt,
            first_frame_image=first_frame_image,
            last_frame_image=last_frame_image,
            reference_images=reference_images,
            provider_payload=provider_payload,
        )
        roles = {item.get("role") for item in content if item.get("role")}
        has_unroled_image = any(
            item.get("type") == "image_url" and not item.get("role") for item in content
        )
        ratio = "adaptive" if roles & _V2_FRAME_ROLES or has_unroled_image else aspect_ratio
        if ratio == "auto":
            ratio = "adaptive"
        if ratio not in _V2_RATIO_VALUES:
            raise ValueError(f"Unsupported MiniMax-H3 aspect ratio: {ratio}")
        if len(content) == 1 and ratio == "adaptive":
            raise ValueError("MiniMax-H3 text-to-video requires a concrete aspect ratio")

        payload: dict[str, Any] = {
            "model": model,
            "content": content,
            "resolution": "2K",
            "duration": int(duration_seconds),
            "ratio": ratio,
        }
        if provider_payload:
            for key in _V2_PASSTHROUGH_FIELDS:
                if key == "aigc_watermark" and not self._is_cn_region:
                    continue
                value = provider_payload.get(key)
                if value is not None:
                    payload[key] = value
        if len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > _V2_MAX_REQUEST_BYTES:
            raise ValueError("MiniMax-H3 request body must not exceed 64 MB")
        return payload

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _params(self, extra: dict[str, str]) -> dict[str, str]:
        params = dict(extra)
        if self.group_id:
            params["GroupId"] = self.group_id
        return params

    @staticmethod
    def _check_base_resp(body: dict[str, Any]) -> None:
        """Raise if the MiniMax envelope reports a non-zero status code."""
        base_resp = body.get("base_resp") or {}
        status_code = base_resp.get("status_code", 0)
        if status_code not in (0, None):
            message = base_resp.get("status_msg") or "unknown error"
            raise RuntimeError(f"MiniMax API error {status_code}: {message}")

    async def generate_video(
        self,
        prompt: str,
        model_name: str,
        aspect_ratio: Literal["auto", "1:1", "3:4", "4:3", "9:16", "16:9", "21:9"] = "16:9",
        duration_seconds: int = 5,
        resolution: str = "720p",
        audio_included: bool = False,
        start_frame: str | None = None,
        end_frame: str | None = None,
        negative_prompt: str | None = None,
        person_generation: Literal["allow_all", "allow_adult"] | None = None,
        seed: int | None = None,
        reference_images: list[VideoReferenceImage] | None = None,
        **kwargs: Any,
    ) -> VideoGenerationResult:
        """
        Generate a video from a text prompt (text-to-video) or a first frame
        image (image-to-video) using the native MiniMax API.

        A ``start_frame`` selects image-to-video; otherwise text-to-video is used.
        Extra native request fields may be supplied via ``provider_payload``.
        """
        model = self._resolve_model_name(model_name)
        provider_payload = kwargs.get("provider_payload")
        native_provider_payload = provider_payload if isinstance(provider_payload, dict) else None
        api_version = "v2" if model in V2_MODELS else "v1"
        if api_version == "v2":
            payload = self._build_v2_payload(
                model=model,
                prompt=prompt,
                first_frame_image=start_frame,
                last_frame_image=end_frame,
                reference_images=reference_images,
                duration_seconds=duration_seconds,
                aspect_ratio=aspect_ratio,
                provider_payload=native_provider_payload,
            )
        else:
            payload = self._build_payload(
                model=model,
                prompt=prompt,
                first_frame_image=start_frame,
                duration_seconds=duration_seconds,
                resolution=resolution,
                provider_payload=native_provider_payload,
            )

        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            task_id = await self._submit(client, payload, api_version=api_version)
            if api_version == "v2":
                download_url = await self._poll_v2_until_ready(client, task_id)
            else:
                file_id = await self._poll_until_ready(client, task_id)
                download_url = await self._resolve_download_url(client, file_id)
            video_bytes = await self._download_bytes(client, download_url)

        user_id = kwargs.get("user_id")
        metadata = kwargs.get("metadata") or {}
        if user_id is None and isinstance(metadata, dict):
            user_id = metadata.get("user_id")

        public_url, storage_path, file_name, size = await self._upload_video(video_bytes, user_id)
        return VideoGenerationResult(
            url=public_url,
            mime_type="video/mp4",
            size=size,
            storage_path=storage_path,
            file_name=file_name,
        )

    async def _submit(
        self,
        client: httpx.AsyncClient,
        payload: dict[str, Any],
        *,
        api_version: str = "v1",
    ) -> str:
        """Submit a generation task and return its task id."""
        response = await client.post(
            f"{self._version_base_url(api_version)}/video_generation",
            headers=self._headers,
            params=self._params({}) if api_version == "v1" else None,
            json=payload,
        )
        response.raise_for_status()
        body = response.json()
        self._check_base_resp(body)
        task_id = body.get("task_id")
        if not task_id:
            raise RuntimeError("MiniMax video generation did not return a task_id")
        return str(task_id)

    async def _poll_until_ready(self, client: httpx.AsyncClient, task_id: str) -> str:
        """Poll the query endpoint until the task succeeds and return the file id."""
        elapsed_time = 0
        while True:
            response = await client.get(
                f"{self._version_base_url('v1')}/query/video_generation",
                headers=self._headers,
                params=self._params({"task_id": task_id}),
            )
            response.raise_for_status()
            body = response.json()
            self._check_base_resp(body)
            status = body.get("status")
            if status == _SUCCESS_STATUS:
                file_id = body.get("file_id")
                if not file_id:
                    raise RuntimeError("MiniMax task succeeded but returned no file_id")
                return str(file_id)
            if status in _FAILURE_STATUSES:
                raise RuntimeError(f"MiniMax video generation failed with status '{status}'")
            if elapsed_time >= self.max_wait_time_seconds:
                raise TimeoutError(
                    f"MiniMax video generation timed out after "
                    f"{self.max_wait_time_seconds} seconds."
                )
            await asyncio.sleep(self.polling_interval_seconds)
            elapsed_time += self.polling_interval_seconds

    async def _poll_v2_until_ready(self, client: httpx.AsyncClient, task_id: str) -> str:
        """Poll a v2 task until it succeeds and return its output URL."""
        elapsed_time = 0
        while True:
            response = await client.get(
                f"{self._version_base_url('v2')}/query/video_generation/{task_id}",
                headers=self._headers,
            )
            response.raise_for_status()
            body = response.json()
            task = body.get("task") or {}
            status = task.get("status")
            if status == _V2_SUCCESS_STATUS:
                content = task.get("content") or {}
                download_url = content.get("url")
                if not download_url:
                    raise RuntimeError("MiniMax-H3 task succeeded but returned no content URL")
                return str(download_url)
            if status in _V2_FAILURE_STATUSES:
                error = task.get("error") or {}
                message = error.get("message") or f"status '{status}'"
                raise RuntimeError(f"MiniMax-H3 video generation failed: {message}")
            if elapsed_time >= self.max_wait_time_seconds:
                raise TimeoutError(
                    f"MiniMax-H3 video generation timed out after "
                    f"{self.max_wait_time_seconds} seconds."
                )
            await asyncio.sleep(self.polling_interval_seconds)
            elapsed_time += self.polling_interval_seconds

    async def _resolve_download_url(self, client: httpx.AsyncClient, file_id: str) -> str:
        """Retrieve the downloadable URL for a rendered video file."""
        response = await client.get(
            f"{self._version_base_url('v1')}/files/retrieve",
            headers=self._headers,
            params=self._params({"file_id": str(file_id)}),
        )
        response.raise_for_status()
        body = response.json()
        self._check_base_resp(body)
        file_info = body.get("file") or {}
        download_url = file_info.get("download_url") or file_info.get("backup_download_url")
        if not download_url:
            raise RuntimeError("MiniMax file retrieval returned no download_url")
        return str(download_url)

    async def _download_bytes(self, client: httpx.AsyncClient, url: str) -> bytes:
        """Download the rendered video bytes from a MiniMax file URL."""
        response = await client.get(url)
        response.raise_for_status()
        return response.content

    async def _upload_video(
        self, video_bytes: bytes, user_id: uuid.UUID | None
    ) -> tuple[str, str, str, int]:
        """Upload video bytes to GCS and return (public_url, storage_path, file_name, size)."""
        video_size = len(video_bytes)
        file_id = str(uuid.uuid4())
        file_name = f"video-{file_id[:8]}.mp4"
        blob_name = path_resolver.user_file(user_id, "video", f"video-{file_id[:8]}", "mp4")

        if not self.bucket:
            raise RuntimeError("GCS bucket not configured for video storage")

        def _upload_sync() -> str:
            blob = self.bucket.blob(blob_name)
            blob.cache_control = "public, max-age=31536000"
            blob.upload_from_file(BytesIO(video_bytes), content_type="video/mp4")
            if self.custom_domain:
                return f"https://{self.custom_domain}/{blob_name}"
            return f"https://storage.googleapis.com/{self.output_bucket}/{blob_name}"

        public_url = await anyio.to_thread.run_sync(_upload_sync)
        return public_url, blob_name, file_name, video_size
