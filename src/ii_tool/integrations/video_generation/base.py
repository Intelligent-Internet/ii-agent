from abc import ABC, abstractmethod
from typing import Any, Dict, List, Literal
from pydantic import BaseModel


class VideoGenerationError(Exception):
    """Raised when video generation fails."""
    pass


class VideoGenerationResult(BaseModel):
    url: str | None = None
    mime_type: str | None = None
    size: int | None = None
    cost: float = 0.0
    search_results: List[Dict[str, Any]] | None = None


class BaseVideoGenerationClient(ABC):
    """Base interface for video generation clients."""

    supports_long_generation: bool = True

    @abstractmethod
    def __init__(self, **kwargs):
        """Initialize the client with provider-specific configuration."""
        pass

    @abstractmethod
    async def generate_video(
        self,
        prompt: str,
        aspect_ratio: Literal["16:9", "9:16"] = "16:9",
        duration_seconds: int = 5,
        image_base64: str | None = None,
        image_mime_type: str | None = None,
    ) -> VideoGenerationResult:
        """Generate video from text prompt or/and image."""
        pass
