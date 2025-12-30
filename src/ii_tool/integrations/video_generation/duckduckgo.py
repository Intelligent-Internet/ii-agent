import asyncio
from typing import Any, Dict, List, Literal, Tuple

import httpx
from duckduckgo_search import DDGS

from .base import BaseVideoGenerationClient, VideoGenerationResult

_DURATION_TO_FILTER = {
    "short": range(0, 9),
    "medium": range(9, 21),
    "long": range(21, 10_000),
}


class DuckDuckGoVideoGenerationClient(BaseVideoGenerationClient):
    """Fallback client that surfaces public videos via DuckDuckGo search."""

    supports_long_generation = False

    def __init__(self, timeout: float = 12.0, max_results: int = 25) -> None:
        self._timeout = timeout
        self._max_results = max_results

    async def generate_video(
        self,
        prompt: str,
        aspect_ratio: Literal["16:9", "9:16"] = "16:9",
        duration_seconds: int = 5,
        image_base64: str | None = None,
        image_mime_type: str | None = None,
    ) -> VideoGenerationResult:
        duration_filter = self._duration_filter(duration_seconds)
        search_results = await self._run_search(prompt, duration_filter)
        sanitized_results = self._sanitize_results(search_results, aspect_ratio)

        if not sanitized_results:
            return VideoGenerationResult(
                url=None,
                mime_type=None,
                size=0,
                cost=0.0,
                search_results=[],
            )

        async with httpx.AsyncClient(
            timeout=self._timeout, follow_redirects=True
        ) as client:
            for result in sanitized_results:
                video_url = result.get("video_url")
                if not video_url:
                    continue
                mime_type, size = await self._probe_url(client, video_url)
                if mime_type and mime_type.startswith("video/"):
                    return VideoGenerationResult(
                        url=video_url,
                        mime_type=mime_type,
                        size=size or 0,
                        cost=0.0,
                        search_results=sanitized_results[:5],
                    )

        # No direct video URLs; return the curated search list.
        return VideoGenerationResult(
            url=None,
            mime_type=None,
            size=0,
            cost=0.0,
            search_results=sanitized_results[:5],
        )

    def _duration_filter(self, duration_seconds: int) -> str | None:
        for key, allowed_range in _DURATION_TO_FILTER.items():
            if duration_seconds in allowed_range:
                return key
        return None

    async def _run_search(
        self, prompt: str, duration: str | None
    ) -> List[Dict[str, Any]]:
        def _search() -> List[Dict[str, Any]]:
            with DDGS(timeout=self._timeout) as ddgs:
                return list(
                    ddgs.videos(
                        prompt,
                        duration=duration,
                        max_results=self._max_results,
                    )
                )

        try:
            return await asyncio.to_thread(_search)
        except httpx.TimeoutException as exc:  # pragma: no cover
            raise RuntimeError("DuckDuckGo video request timeout") from exc
        except httpx.HTTPError as exc:  # pragma: no cover
            raise RuntimeError("DuckDuckGo video network error") from exc
        except Exception as exc:  # pragma: no cover - ddgs errors vary
            raise RuntimeError(f"DuckDuckGo video search failed: {exc}") from exc

    @staticmethod
    def _sanitize_results(
        results: List[Dict[str, Any]], aspect_ratio: str
    ) -> List[Dict[str, Any]]:
        sanitized: List[Dict[str, Any]] = []
        for result in results:
            video_url = result.get("content") or result.get("url") or ""
            if not video_url:
                continue
            sanitized.append(
                {
                    "title": result.get("title") or "",
                    "description": result.get("description") or "",
                    "video_url": video_url,
                    "thumbnail_url": result.get("image") or "",
                    "source": result.get("source") or "",
                    "duration": result.get("duration") or "",
                    "published": result.get("published") or "",
                    "aspect_ratio": aspect_ratio,
                }
            )
        return sanitized

    async def _probe_url(
        self, client: httpx.AsyncClient, url: str
    ) -> Tuple[str | None, int | None]:
        try:
            response = await client.head(url)
            if response.status_code >= 400:
                response = await client.get(url, headers={"Range": "bytes=0-1023"})
            if response.status_code >= 400:
                return None, None
        except httpx.HTTPError:
            return None, None

        mime_type = response.headers.get("content-type")
        if mime_type:
            mime_type = mime_type.split(";")[0].strip()

        content_length = response.headers.get("content-length")
        size = (
            int(content_length)
            if content_length and content_length.isdigit()
            else None
        )

        return mime_type, size
