import asyncio
from typing import List

import httpx
from duckduckgo_search import DDGS

from .base import BaseWebSearchClient, WebSearchResult
from .exception import WebSearchProviderError, WebSearchNetworkError


class DuckDuckGoWebSearchClient(BaseWebSearchClient):
    """DuckDuckGo implementation of web search client."""

    def __init__(self, timeout: int = 10):
        self._timeout = timeout

    async def search(self, query: str, max_results: int = 10) -> WebSearchResult:
        def _run_search() -> list[dict[str, str]]:
            with DDGS(timeout=self._timeout) as ddgs:
                return list(ddgs.text(query, max_results=max_results))

        try:
            ddg_results = await asyncio.to_thread(_run_search)
        except httpx.TimeoutException as exc:  # pragma: no cover
            raise WebSearchNetworkError("DuckDuckGo request timeout") from exc
        except httpx.HTTPError as exc:  # pragma: no cover
            raise WebSearchNetworkError("DuckDuckGo network error") from exc
        except Exception as exc:  # pragma: no cover - duckduckgo_search errors vary
            raise WebSearchProviderError(f"DuckDuckGo search failed: {exc}") from exc

        search_response = [
            {
                "query": query,
                "title": result.get("title", ""),
                "url": result.get("href", ""),
                "content": result.get("body", ""),
            }
            for result in ddg_results
        ]

        return WebSearchResult(result=search_response, cost=0.0)

    async def batch_search(self, queries: List[str], max_results: int = 10) -> List[WebSearchResult]:
        tasks = [self.search(query, max_results) for query in queries]
        return await asyncio.gather(*tasks)
