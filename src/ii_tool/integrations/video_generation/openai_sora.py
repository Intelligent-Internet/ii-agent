"""OpenAI Sora video generation client."""

import asyncio
import time
from typing import Any, Literal

from openai import OpenAI

from .base import (
    BaseVideoGenerationClient,
    VideoGenerationError,
    VideoGenerationResult,
)

# Sora supported sizes and their aspect ratio mappings
# sora-2: 720x1280, 1280x720
# sora-2-pro: 720x1280, 1280x720, 1024x1792, 1792x1024
_ASPECT_RATIO_TO_SIZE = {
    "16:9": "1280x720",
    "9:16": "720x1280",
}

_ASPECT_RATIO_TO_SIZE_PRO = {
    "16:9": "1792x1024",
    "9:16": "1024x1792",
}

# Sora allowed durations (in seconds) - only 4, 8, or 12 are valid
_VALID_DURATIONS = [4, 8, 12]

# Sora pricing per second (based on OpenAI's pricing page)
# See: https://platform.openai.com/docs/pricing
_SORA_COST_PER_SECOND = {
    "sora-2": {
        "1280x720": 0.10,
        "720x1280": 0.10,
    },
    "sora-2-pro": {
        "1280x720": 0.30,
        "720x1280": 0.30,
        "1792x1024": 0.50,
        "1024x1792": 0.50,
    },
}


class OpenAIVideoGenerationClient(BaseVideoGenerationClient):
    """Video generation client using OpenAI's Sora model."""

    supports_long_generation: bool = True

    def __init__(
        self,
        api_key: str,
        model: Literal["sora-2", "sora-2-pro"] = "sora-2",
        poll_interval: float = 10.0,
        max_wait_seconds: float = 600.0,  # 10 minutes max
        use_high_res: bool = False,  # Use higher resolution for sora-2-pro
    ) -> None:
        """
        Initialize the OpenAI Sora client.

        Args:
            api_key: OpenAI API key
            model: Model to use (sora-2 or sora-2-pro)
            poll_interval: Seconds between status polls
            max_wait_seconds: Maximum time to wait for video generation
            use_high_res: If True and using sora-2-pro, use 1792x1024/1024x1792 instead of 1280x720/720x1280
        """
        self._client = OpenAI(api_key=api_key)
        self._model = model
        self._poll_interval = poll_interval
        self._max_wait_seconds = max_wait_seconds
        self._use_high_res = use_high_res

    def _get_nearest_duration(self, requested: int) -> int:
        """Get the nearest valid duration (4, 8, or 12 seconds)."""
        if requested <= 6:
            return 4
        elif requested <= 10:
            return 8
        else:
            return 12

    async def generate_video(
        self,
        prompt: str,
        aspect_ratio: Literal["16:9", "9:16"] = "16:9",
        duration_seconds: int = 5,
        image_base64: str | None = None,
        image_mime_type: str | None = None,
    ) -> VideoGenerationResult:
        """
        Generate a video using Sora.

        Args:
            prompt: Text description of the video to generate
            aspect_ratio: Desired aspect ratio (16:9 or 9:16)
            duration_seconds: Requested duration - will be mapped to nearest valid value (4, 8, or 12)
            image_base64: Optional base64-encoded image for first frame reference (not yet supported)
            image_mime_type: MIME type of the reference image

        Returns:
            VideoGenerationResult with the generated video URL

        Raises:
            VideoGenerationError: If generation fails
        """
        # Select size based on model and aspect ratio
        if self._model == "sora-2-pro" and self._use_high_res:
            size = _ASPECT_RATIO_TO_SIZE_PRO.get(aspect_ratio, "1792x1024")
        else:
            size = _ASPECT_RATIO_TO_SIZE.get(aspect_ratio, "1280x720")

        # Map to nearest valid duration (4, 8, or 12)
        actual_duration = self._get_nearest_duration(duration_seconds)

        def _create_video() -> str:
            """Create the video generation job and return the video ID."""
            # Note: image reference support via input_reference requires multipart form
            # For now, we only support text-to-video generation
            response = self._client.videos.create(
                model=self._model,
                prompt=prompt,
                size=size,
                seconds=str(actual_duration),
            )
            return response.id

        def _poll_status(video_id: str) -> dict:
            """Poll until video is complete or failed."""
            start_time = time.time()

            while True:
                elapsed = time.time() - start_time
                if elapsed > self._max_wait_seconds:
                    raise VideoGenerationError(
                        f"Video generation timed out after {self._max_wait_seconds}s"
                    )

                video = self._client.videos.retrieve(video_id)

                if video.status == "completed":
                    return {"status": "completed", "video": video}
                elif video.status == "failed":
                    raise VideoGenerationError(
                        f"Sora video generation failed: {getattr(video, 'error', 'Unknown error')}"
                    )

                # Still in progress, wait before polling again
                time.sleep(self._poll_interval)

        def _download_video(video_id: str) -> str:
            """Download the video and return the URL."""
            # The download returns a response with the URL
            # URLs are valid for 1 hour after generation
            content = self._client.videos.download_content(video_id)
            # The content object has a url attribute or we need to get it differently
            # Based on the API docs, we may need to construct the URL
            return f"https://api.openai.com/v1/videos/{video_id}/content"

        try:
            # Create the video job
            video_id = await asyncio.to_thread(_create_video)

            # Poll for completion
            result = await asyncio.to_thread(_poll_status, video_id)

            # Get the video URL
            # For Sora, we can use the video ID to construct the download URL
            # The actual download requires auth, so we store the video_id
            video_url = f"https://api.openai.com/v1/videos/{video_id}/content"

        except VideoGenerationError:
            raise
        except Exception as exc:
            raise VideoGenerationError(f"Sora video generation failed: {exc}") from exc

        # Calculate cost based on model, size, and actual duration
        model_costs = _SORA_COST_PER_SECOND.get(self._model, {})
        cost_per_second = model_costs.get(size, 0.10)
        cost = cost_per_second * actual_duration

        return VideoGenerationResult(
            url=video_url,
            mime_type="video/mp4",
            size=None,  # Size unknown until downloaded
            cost=cost,
            search_results=None,
        )
