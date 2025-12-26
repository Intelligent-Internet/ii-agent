"""OpenAI DALL-E image generation client."""

import asyncio
from typing import Any, Literal

from openai import OpenAI

from .base import (
    BaseImageGenerationClient,
    ImageGenerationError,
    ImageGenerationResult,
)

# DALL-E 3 supported sizes and their aspect ratio mappings
_ASPECT_RATIO_TO_SIZE = {
    "1:1": "1024x1024",
    "16:9": "1792x1024",
    "9:16": "1024x1792",
    "4:3": "1792x1024",  # Closest match
    "3:4": "1024x1792",  # Closest match
}

# DALL-E 3 pricing per image (standard quality)
# See: https://openai.com/api/pricing/
_DALLE3_STANDARD_COST = {
    "1024x1024": 0.040,
    "1024x1792": 0.080,
    "1792x1024": 0.080,
}


class OpenAIImageGenerationClient(BaseImageGenerationClient):
    """Image generation client using OpenAI's DALL-E 3 model."""

    def __init__(
        self,
        api_key: str,
        model: str = "dall-e-3",
        quality: Literal["standard", "hd"] = "standard",
        style: Literal["vivid", "natural"] = "vivid",
    ) -> None:
        """
        Initialize the OpenAI DALL-E client.

        Args:
            api_key: OpenAI API key
            model: Model to use (dall-e-3 or dall-e-2)
            quality: Image quality - "standard" or "hd" (dall-e-3 only)
            style: Image style - "vivid" or "natural" (dall-e-3 only)
        """
        self._client = OpenAI(api_key=api_key)
        self._model = model
        self._quality = quality
        self._style = style

    async def generate_image(
        self,
        prompt: str,
        aspect_ratio: Literal["1:1", "16:9", "9:16", "4:3", "3:4"] = "1:1",
        **kwargs: Any,
    ) -> ImageGenerationResult:
        """
        Generate an image using DALL-E 3.

        Args:
            prompt: Text description of the image to generate
            aspect_ratio: Desired aspect ratio

        Returns:
            ImageGenerationResult with the generated image URL

        Raises:
            ImageGenerationError: If generation fails
        """
        size = _ASPECT_RATIO_TO_SIZE.get(aspect_ratio, "1024x1024")

        # Allow kwargs to override defaults
        quality = kwargs.get("quality", self._quality)
        style = kwargs.get("style", self._style)

        def _generate() -> tuple[str, str]:
            response = self._client.images.generate(
                model=self._model,
                prompt=prompt,
                size=size,
                quality=quality,
                style=style,
                n=1,
                response_format="url",
            )

            if not response.data or not response.data[0].url:
                raise ImageGenerationError("DALL-E returned no image data")

            return response.data[0].url, response.data[0].revised_prompt or prompt

        try:
            url, revised_prompt = await asyncio.to_thread(_generate)
        except Exception as exc:
            raise ImageGenerationError(f"DALL-E image generation failed: {exc}") from exc

        # Calculate cost based on size and quality
        base_cost = _DALLE3_STANDARD_COST.get(size, 0.040)
        cost = base_cost * 2 if quality == "hd" else base_cost

        return ImageGenerationResult(
            url=url,
            mime_type="image/png",
            size=0,  # URL-based, size unknown until downloaded
            cost=cost,
            search_results=None,
        )
