from abc import ABC, abstractmethod
from typing import List, Literal
from pydantic import BaseModel

WebVisitServiceType = Literal[
    "firecrawl",
    "gemini",
    "jina",
    "tavily",
    "outcrawl",
    "beautifulsoup",
]
WEB_VISIT_SERVICE_TYPES: tuple[str, ...] = (
    "firecrawl",
    "gemini",
    "jina",
    "tavily",
    "outcrawl",
    "beautifulsoup",
)


class WebVisitError(Exception):
    """Base exception for web visit errors"""

    pass


class WebVisitResult(BaseModel):
    content: str
    cost: float


class BaseWebVisitClient(ABC):
    """Base interface for web visit clients."""

    @abstractmethod
    async def extract(self, url: str) -> WebVisitResult:
        """Extract content from a webpage."""
        pass

    @abstractmethod
    async def batch_extract(self, urls: List[str]) -> WebVisitResult:
        """Extract content from a webpage and compress it."""
        pass
