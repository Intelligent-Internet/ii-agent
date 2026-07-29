"""
Native MiniMax implementation of the video generation client.

Unlike the FAL client, which reaches MiniMax models indirectly through a
third-party proxy, this client talks to the first-party MiniMax video
generation REST API directly:

    * submit   -> POST {base_url}/video_generation
    * poll     -> GET  {base_url}/query/video_generation?task_id=...
    * retrieve -> GET  {base_url}/files/retrieve?file_id=...

Both the global (``api.minimax.io``) and China (``api.minimaxi.com``) hosts are
supported by pointing ``base_url`` at the matching ``/v1`` root. The client
covers both text-to-video (``prompt``) and image-to-video (``first_frame_image``)
requests, task polling, file retrieval and response parsing.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from io import BytesIO
from typing import Any, Literal

import anyio
import httpx

from ii_agent.core.storage.path_resolver import path_resolver
from .base import (
    BaseVideoGenerationClient,
    VideoGenerationResult,
    VideoReferenceImage,
)


DEFAULT_BASE_URL = "https://api.minimax.io/v1"
DEFAULT_MODEL = "MiniMax-Hailuo-2.3"

# Models exposed by the native MiniMax video generation API.
SUPPORTED_MODELS = (
    "MiniMax-Hailuo-2.3",
    "MiniMax-Hailuo-2.3-Fast",
    "MiniMax-Hailuo-02",
    "T2V-01-Director",
    "T2V-01",
    "I2V-01-Director",
    "I2V-01-live",
    "I2V-01",
)

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

# Task states returned by the query endpoint.
_SUCCESS_STATUS = "Success"
_FAILURE_STATUSES = frozenset({"Fail"})


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
        if not model_name:
            return self.model_name or DEFAULT_MODEL
        return model_name

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
        payload = self._build_payload(
            model=model,
            prompt=prompt,
            first_frame_image=start_frame,
            duration_seconds=duration_seconds,
            resolution=resolution,
            provider_payload=provider_payload if isinstance(provider_payload, dict) else None,
        )

        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            task_id = await self._submit(client, payload)
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

    async def _submit(self, client: httpx.AsyncClient, payload: dict[str, Any]) -> str:
        """Submit a generation task and return its task id."""
        response = await client.post(
            f"{self.base_url}/video_generation",
            headers=self._headers,
            params=self._params({}),
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
                f"{self.base_url}/query/video_generation",
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

    async def _resolve_download_url(self, client: httpx.AsyncClient, file_id: str) -> str:
        """Retrieve the downloadable URL for a rendered video file."""
        response = await client.get(
            f"{self.base_url}/files/retrieve",
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
