import asyncio
from typing import Any, List, Dict

import httpx
from duckduckgo_search import DDGS

from .base import BaseImageSearchClient, ImageSearchResult, ImageSearchError

_ASPECT_RATIO_TO_LAYOUT = {
    "square": "Square",
    "tall": "Tall",
    "wide": "Wide",
    "panoramic": "Panoramic",
}


class DuckDuckGoImageSearchClient(BaseImageSearchClient):
    """DuckDuckGo implementation of image search client."""

    def __init__(self, timeout: int = 10):
        self._timeout = timeout

    async def search(
        self,
        query: str,
        aspect_ratio: str,
        image_type: str,
        min_width: int = 0,
        min_height: int = 0,
        is_product: bool = False,
        **kwargs: Any,
    ) -> ImageSearchResult:
        layout = _ASPECT_RATIO_TO_LAYOUT.get(aspect_ratio)
        type_image = None if image_type == "all" else image_type

        def _run_search() -> List[Dict[str, Any]]:
            with DDGS(timeout=self._timeout) as ddgs:
                return list(
                    ddgs.images(
                        query,
                        type_image=type_image,
                        layout=layout,
                        max_results=50,
                    )
                )

        try:
            ddg_results = await asyncio.to_thread(_run_search)
        except httpx.TimeoutException as exc:  # pragma: no cover
            raise ImageSearchError("DuckDuckGo image request timeout") from exc
        except httpx.HTTPError as exc:  # pragma: no cover
            raise ImageSearchError("DuckDuckGo image network error") from exc
        except Exception as exc:  # pragma: no cover - duckduckgo_search errors vary
            raise ImageSearchError(f"DuckDuckGo image search failed: {exc}") from exc

        search_response = []
        for result in ddg_results:
            original_url = result.get("image") or result.get("thumbnail")
            if not original_url:
                continue

            width = int(result.get("width") or 0)
            height = int(result.get("height") or 0)

            if width < min_width or height < min_height:
                continue

            result_is_product = bool(result.get("is_product", False))
            if result_is_product != is_product:
                continue

            search_response.append(
                {
                    "title": result.get("title", ""),
                    "source": result.get("source", ""),
                    "image_url": original_url,
                    "width": width,
                    "height": height,
                    "is_product": result_is_product,
                }
            )

        return ImageSearchResult(result=search_response, cost=0.0)
