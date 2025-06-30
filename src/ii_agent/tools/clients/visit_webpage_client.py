import asyncio
import aiohttp
import os
from ii_agent.utils.constants import VISIT_WEB_PAGE_MAX_OUTPUT_LENGTH
from ii_agent.tools.utils import truncate_content
from ii_agent.core.storage.models.settings import Settings
from typing import Optional


class WebpageVisitException(Exception):
    """Base exception for webpage visit errors"""

    pass


class ContentExtractionError(WebpageVisitException):
    """Raised when content cannot be extracted from the webpage"""

    pass


class NetworkError(WebpageVisitException):
    """Raised when there are network-related errors"""

    pass


class BaseVisitClient:
    name: str = "Base"
    max_output_length: int

    def forward(self, url: str) -> str:
        return asyncio.run(self.forward_async(url))

    async def forward_async(self, url: str) -> str:
        raise NotImplementedError("Subclasses must implement this method")


class MarkdownifyVisitClient(BaseVisitClient):
    name = "Markdownify"

    def __init__(self, max_output_length: int = VISIT_WEB_PAGE_MAX_OUTPUT_LENGTH):
        self.max_output_length = max_output_length

    async def forward_async(self, url: str) -> str:
        try:
            import re
            from markdownify import markdownify

        except ImportError:
            raise WebpageVisitException(
                "Required package 'markdownify' is not installed"
            )

        try:
            # Send a GET request to the URL with a 20-second timeout
            timeout = aiohttp.ClientTimeout(total=20)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    response.raise_for_status()
                    html_content = await response.text()

            # Convert the HTML content to Markdown (run in executor since markdownify is not async)
            loop = asyncio.get_event_loop()
            markdown_content = await loop.run_in_executor(
                None, markdownify, html_content
            )
            markdown_content = markdown_content.strip()

            # Remove multiple line breaks
            markdown_content = re.sub(r"\n{3,}", "\n\n", markdown_content)

            if not markdown_content:
                raise ContentExtractionError("No content found in the webpage")

            return truncate_content(markdown_content, self.max_output_length)

        except asyncio.TimeoutError:
            raise NetworkError("The request timed out")
        except aiohttp.ClientError as e:
            raise NetworkError(f"Error fetching the webpage: {str(e)}")


class TavilyVisitClient(BaseVisitClient):
    name = "Tavily"

    def __init__(
        self,
        max_output_length: int = VISIT_WEB_PAGE_MAX_OUTPUT_LENGTH,
        api_key: Optional[str] = None,
    ):
        self.max_output_length = max_output_length
        self.api_key = api_key or ""
        if not self.api_key:
            raise WebpageVisitException("Tavily API key not provided")

    async def forward_async(self, url: str) -> str:
        try:
            from tavily import AsyncTavilyClient
        except ImportError as e:
            raise ImportError(
                "You must install package `tavily` to run this tool: for instance run `pip install tavily-python`."
            ) from e

        try:
            tavily_client = AsyncTavilyClient(api_key=self.api_key)

            # Extract webpage content
            response = await tavily_client.extract(
                url, include_images=True, extract_depth="advanced"
            )

            # Check if response contains results
            if not response or "results" not in response or not response["results"]:
                return f"No content could be extracted from {url}"

            # Format the content from the first result
            data = response["results"][0]
            if not data:
                return f"No textual content could be extracted from {url}"

            content = data["raw_content"]
            # Format images as markdown
            images = response["results"][0].get("images", [])
            if images:
                image_markdown = "\n\n### Images:\n"
                for i, img_url in enumerate(images):
                    image_markdown += f"![Image {i + 1}]({img_url})\n"
                content += image_markdown

            return truncate_content(content, self.max_output_length)

        except Exception as e:
            raise WebpageVisitException(f"Error using Tavily: {str(e)}")


class FireCrawlVisitClient(BaseVisitClient):
    name = "FireCrawl"

    def __init__(
        self,
        max_output_length: int = VISIT_WEB_PAGE_MAX_OUTPUT_LENGTH,
        api_key: Optional[str] = None,
    ):
        self.max_output_length = max_output_length
        self.api_key = api_key or ""
        if not self.api_key:
            raise WebpageVisitException("FireCrawl API key not provided")

    async def forward_async(self, url: str) -> str:
        base_url = "https://api.firecrawl.dev/v1/scrape"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {"url": url, "onlyMainContent": False, "formats": ["markdown"]}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    base_url, headers=headers, json=payload
                ) as response:
                    response.raise_for_status()
                    response_data = await response.json()

            data = response_data.get("data", {}).get("markdown")
            if not data:
                raise ContentExtractionError(
                    "No content could be extracted from webpage"
                )

            return truncate_content(data, self.max_output_length)

        except aiohttp.ClientError as e:
            raise NetworkError(f"Error making request: {str(e)}")


class JinaVisitClient(BaseVisitClient):
    name = "Jina"

    def __init__(
        self,
        max_output_length: int = VISIT_WEB_PAGE_MAX_OUTPUT_LENGTH,
        api_key: Optional[str] = None,
    ):
        self.max_output_length = max_output_length
        self.api_key = api_key or ""
        if not self.api_key:
            raise WebpageVisitException("Jina API key not provided")

    async def forward_async(self, url: str) -> str:
        jina_url = f"https://r.jina.ai/{url}"
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "X-Engine": "browser",
            "X-Return-Format": "markdown",
            "X-With-Images-Summary": "true",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(jina_url, headers=headers) as response:
                    response.raise_for_status()
                    json_response = await response.json()

            if not json_response or "data" not in json_response:
                raise ContentExtractionError(
                    "No content could be extracted from webpage"
                )

            data = json_response["data"]

            content = data["title"] + "\n\n" + data["content"]
            if not content:
                raise ContentExtractionError(
                    "No content could be extracted from webpage"
                )

            return truncate_content(content, self.max_output_length)

        except aiohttp.ClientError as e:
            raise NetworkError(f"Error making request: {str(e)}")


def create_visit_client(
    settings: Optional[Settings] = None,
    max_output_length: int = VISIT_WEB_PAGE_MAX_OUTPUT_LENGTH,
) -> BaseVisitClient:
    """
    Factory function that creates a visit client based on available API keys.
    Priority order: FireCrawl > Jina > Tavily > Markdownify

    Args:
        settings: Settings object containing API keys
        max_output_length (int): Maximum length of the output text

    Returns:
        BaseVisitClient: An instance of a visit client
    """

    # Extract API keys from settings if available, otherwise fall back to environment
    firecrawl_key = None
    jina_key = None
    tavily_key = None

    if settings and settings.search_config:
        firecrawl_key = (
            settings.search_config.firecrawl_api_key.get_secret_value()
            if settings.search_config.firecrawl_api_key
            else None
        )
        jina_key = (
            settings.search_config.jina_api_key.get_secret_value()
            if settings.search_config.jina_api_key
            else None
        )
        tavily_key = (
            settings.search_config.tavily_api_key.get_secret_value()
            if settings.search_config.tavily_api_key
            else None
        )

    # Fall back to environment variables if not in settings
    if not firecrawl_key:
        firecrawl_key = os.environ.get("FIRECRAWL_API_KEY", "")
    if not jina_key:
        jina_key = os.environ.get("JINA_API_KEY", "")
    if not tavily_key:
        tavily_key = os.environ.get("TAVILY_API_KEY", "")

    if firecrawl_key:
        print("Using FireCrawl to visit webpage")
        return FireCrawlVisitClient(
            max_output_length=max_output_length, api_key=firecrawl_key
        )

    if jina_key:
        print("Using Jina to visit webpage")
        return JinaVisitClient(max_output_length=max_output_length, api_key=jina_key)

    if tavily_key:
        print("Using Tavily to visit webpage")
        return TavilyVisitClient(
            max_output_length=max_output_length, api_key=tavily_key
        )

    print("Using Markdownify to visit webpage")
    return MarkdownifyVisitClient(max_output_length=max_output_length)
