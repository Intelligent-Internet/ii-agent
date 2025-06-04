import requests
from .utils import truncate_content
import os
import json
from ii_agent.utils.constants import VISIT_WEB_PAGE_MAX_OUTPUT_LENGTH



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
        raise NotImplementedError("Subclasses must implement this method")


class MarkdownifyVisitClient(BaseVisitClient):
    name = "Markdownify"

    def __init__(self, max_output_length: int = VISIT_WEB_PAGE_MAX_OUTPUT_LENGTH):
        self.max_output_length = max_output_length

    def forward(self, url: str) -> str:
        try:
            import re
            import requests
            from markdownify import markdownify
            from requests.exceptions import RequestException

        except ImportError:
            raise WebpageVisitException(
                "Required packages 'markdownify' and 'requests' are not installed"
            )

        try:
            # Send a GET request to the URL with a 20-second timeout
            response = requests.get(url, timeout=20)
            response.raise_for_status()

            # Convert the HTML content to Markdown
            markdown_content = markdownify(response.text).strip()

            # Remove multiple line breaks
            markdown_content = re.sub(r"\n{3,}", "\n\n", markdown_content)

            if not markdown_content:
                raise ContentExtractionError("No content found in the webpage")

            return truncate_content(markdown_content, self.max_output_length)

        except requests.exceptions.Timeout:
            raise NetworkError("The request timed out")
        except RequestException as e:
            raise NetworkError(f"Error fetching the webpage: {str(e)}")


class TavilyVisitClient(BaseVisitClient):
    name = "Tavily"

    def __init__(self, max_output_length: int = VISIT_WEB_PAGE_MAX_OUTPUT_LENGTH):
        self.max_output_length = max_output_length
        self.api_key = os.environ.get("TAVILY_API_KEY", "")
        if not self.api_key:
            raise WebpageVisitException("TAVILY_API_KEY environment variable not set")

    def forward(self, url: str) -> str:
        try:
            from tavily import TavilyClient
        except ImportError as e:
            raise ImportError(
                "You must install package `tavily` to run this tool: for instance run `pip install tavily-python`."
            ) from e

        tavily_client = TavilyClient(api_key=self.api_key)
        response = tavily_client.extract(url)

        # Extract webpage content
        response = tavily_client.extract(
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


class FireCrawlVisitClient(BaseVisitClient):
    name = "FireCrawl"

    def __init__(self, max_output_length: int = VISIT_WEB_PAGE_MAX_OUTPUT_LENGTH):
        self.max_output_length = max_output_length
        self.api_key = os.environ.get("FIRECRAWL_API_KEY", "")
        if not self.api_key:
            raise WebpageVisitException(
                "FIRECRAWL_API_KEY environment variable not set"
            )

    def forward(self, url: str) -> str:
        base_url = "https://api.firecrawl.dev/v1/scrape"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {"url": url, "onlyMainContent": False, "formats": ["markdown"]}

        try:
            response = requests.request(
                "POST", base_url, headers=headers, data=json.dumps(payload)
            )
            response.raise_for_status()

            data = response.json().get("data").get("markdown")
            if not data:
                raise ContentExtractionError(
                    "No content could be extracted from webpage"
                )

            return truncate_content(data, self.max_output_length)

        except requests.exceptions.RequestException as e:
            raise NetworkError(f"Error making request: {str(e)}")


class JinaVisitClient(BaseVisitClient):
    name = "Jina"

    def __init__(self, max_output_length: int = VISIT_WEB_PAGE_MAX_OUTPUT_LENGTH):
        self.max_output_length = max_output_length
        self.api_key = os.environ.get("JINA_API_KEY", "")
        if not self.api_key:
            raise WebpageVisitException("JINA_API_KEY environment variable not set")

    def forward(self, url: str) -> str:
        jina_url = f"https://r.jina.ai/{url}"
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "X-Engine": "browser",
            "X-Return-Format": "markdown",
            "X-With-Images-Summary": "true",
        }

        try:
            response = requests.get(jina_url, headers=headers)
            response.raise_for_status()

            json_response = response.json()
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

        except requests.exceptions.RequestException as e:
            raise NetworkError(f"Error making request: {str(e)}")


def create_visit_client(max_output_length: int = VISIT_WEB_PAGE_MAX_OUTPUT_LENGTH) -> BaseVisitClient:
    """
    Factory function that creates a visit client based on available API keys.
    Priority order: Tavily > Jina > FireCrawl > Markdown

    Args:
        max_output_length (int): Maximum length of the output text

    Returns:
        BaseVisitClient: An instance of a visit client
    """
    if os.environ.get("FIRECRAWL_API_KEY"):
        print("Using FireCrawl to visit webpage")
        return FireCrawlVisitClient(max_output_length=max_output_length)

    if os.environ.get("JINA_API_KEY"):
        print("Using Jina to visit webpage")
        return JinaVisitClient(max_output_length=max_output_length)

    if os.environ.get("TAVILY_API_KEY"):
        print("Using Tavily to visit webpage")
        return TavilyVisitClient(max_output_length=max_output_length)

    print("Using Markdownify to visit webpage")
    return MarkdownifyVisitClient(max_output_length=max_output_length)
