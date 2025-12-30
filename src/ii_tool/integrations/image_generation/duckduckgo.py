import asyncio
from typing import Any, Dict, List, Literal, Tuple

import httpx
from duckduckgo_search import DDGS

from .base import (
    BaseImageGenerationClient,
    ImageGenerationError,
    ImageGenerationResult,
)

_ASPECT_RATIO_TO_LAYOUT = {
    "1:1": "Square",
    "16:9": "Wide",
    "9:16": "Tall",
    "4:3": "Wide",
    "3:4": "Tall",
}


class DuckDuckGoImageGenerationClient(BaseImageGenerationClient):
    """Fallback client that searches for existing images via DuckDuckGo."""

    def __init__(self, timeout: float = 10.0, max_results: int = 25) -> None:
        self._timeout = timeout
        self._max_results = max_results

    async def generate_image(
        self,
        prompt: str,
        aspect_ratio: Literal["1:1", "16:9", "9:16", "4:3", "3:4"] = "1:1",
        **_: Any,
    ) -> ImageGenerationResult:
        search_results = await self._run_search(prompt, aspect_ratio)
        sanitized_results = self._sanitize_results(search_results)

        if not sanitized_results:
            raise ImageGenerationError("DuckDuckGo image search returned no usable results")

        async with httpx.AsyncClient(
            timeout=self._timeout, follow_redirects=True
        ) as client:
            for result in sanitized_results:
                url = result["image_url"]
                if not url:
                    continue
                mime_type, size = await self._probe_url(client, url)
                if mime_type:
                    return ImageGenerationResult(
                        url=url,
                        mime_type=mime_type,
                        size=size or 0,
                        cost=0.0,
                        search_results=sanitized_results[:5],
                    )

        raise ImageGenerationError("DuckDuckGo image search results were not accessible")

    async def _run_search(
        self, prompt: str, aspect_ratio: str
    ) -> List[Dict[str, Any]]:
        layout = _ASPECT_RATIO_TO_LAYOUT.get(aspect_ratio)

        def _search() -> List[Dict[str, Any]]:
            with DDGS(timeout=self._timeout) as ddgs:
                return list(
                    ddgs.images(
                        prompt,
                        layout=layout,
                        max_results=self._max_results,
                    )
                )

        try:
            return await asyncio.to_thread(_search)
        except httpx.TimeoutException as exc:  # pragma: no cover
            raise ImageGenerationError("DuckDuckGo image request timeout") from exc
        except httpx.HTTPError as exc:  # pragma: no cover
            raise ImageGenerationError("DuckDuckGo image network error") from exc
        except Exception as exc:  # pragma: no cover - ddgs raises custom errors
            raise ImageGenerationError(f"DuckDuckGo image search failed: {exc}") from exc

    @staticmethod
    def _sanitize_results(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        sanitized: List[Dict[str, Any]] = []
        for result in results:
            image_url = (
                result.get("image")
                or result.get("thumbnail")
                or result.get("url")
                or ""
            )
            if not image_url:
                continue
            width = DuckDuckGoImageGenerationClient._try_parse_int(result.get("width"))
            height = DuckDuckGoImageGenerationClient._try_parse_int(result.get("height"))

            sanitized.append(
                {
                    "title": result.get("title") or "",
                    "source": result.get("source") or "",
                    "image_url": image_url,
                    "width": width,
                    "height": height,
                }
            )
        return sanitized

    async def _probe_url(
        self, client: httpx.AsyncClient, url: str
    ) -> Tuple[str | None, int | None]:
        try:
            response = await client.head(url)
            if response.status_code >= 400 or "content-type" not in response.headers:
                response = await client.get(url, headers={"Range": "bytes=0-1023"})
            if response.status_code >= 400:
                return None, None
        except httpx.HTTPError:
            return None, None

        mime_type = response.headers.get("content-type")
        if mime_type:
            mime_type = mime_type.split(";")[0].strip()
        else:
            mime_type = "image/jpeg"

        content_length = response.headers.get("content-length")
        size = (
            int(content_length)
            if content_length and content_length.isdigit()
            else None
        )

        return mime_type, size

    @staticmethod
    def _try_parse_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
