import asyncio
from typing import Any, List

import aiohttp

from ii_agent_tools.integrations.web_visit.base import (
    BaseWebVisitClient,
    WebVisitError,
    WebVisitResult,
)


class OutcrawlWebVisitClient(BaseWebVisitClient):
    """Outcrawl implementation of web visit client."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.outcrawl.ai/v1/scrape"

    async def _extract(self, url: str) -> dict[str, Any]:
        """Visit webpage and extract content using the Outcrawl scrape API."""

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {
            "url": url,
            "formats": ["markdown"],
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.base_url,
                headers=headers,
                json=payload,
            ) as response:
                response.raise_for_status()
                return await response.json()

    async def extract(self, url: str) -> WebVisitResult:
        """Visit webpage and extract content using Outcrawl."""
        try:
            data = await self._extract(url)
        except Exception as e:
            raise WebVisitError(f"Outcrawl extraction error: {str(e)}")

        markdown = data.get("markdown")
        if markdown is None or (isinstance(markdown, str) and not markdown.strip()):
            raise WebVisitError("No content could be extracted from webpage")
        return WebVisitResult(
            content=markdown,
            cost=0.0,  # Outcrawl cost calculation can be added here if needed
        )

    async def batch_extract(self, urls: List[str]) -> WebVisitResult:
        """Visit multiple webpages using Outcrawl."""
        tasks = [self.extract(url) for url in urls]
        results = await asyncio.gather(*tasks)
        return WebVisitResult(
            content="\n".join(result.content for result in results),
            cost=sum(result.cost for result in results),
        )
