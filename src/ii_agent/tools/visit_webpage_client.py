import requests
from .utils import truncate_content
import os
import json


class BaseVisitClient:
    name: str = "Base"
    max_output_length: int

    def forward(self, url: str) -> str:
        raise NotImplementedError("Subclasses must implement this method")


class MarkdownifyVisitClient(BaseVisitClient):
    name = "Markdownify"

    def __init__(self, max_output_length: int = 40000):
        self.max_output_length = max_output_length

    def forward(self, url: str) -> str:
        try:
            import re
            import requests
            from markdownify import markdownify
            from requests.exceptions import RequestException

        except ImportError as e:
            raise ImportError(
                "You must install packages `markdownify` and `requests` to run this tool: for instance run `pip install markdownify requests`."
            ) from e
        try:
            # Send a GET request to the URL with a 20-second timeout
            response = requests.get(url, timeout=20)
            response.raise_for_status()  # Raise an exception for bad status codes

            # Convert the HTML content to Markdown
            markdown_content = markdownify(response.text).strip()

            # Remove multiple line breaks
            markdown_content = re.sub(r"\n{3,}", "\n\n", markdown_content)

            return truncate_content(markdown_content, self.max_output_length)

        except requests.exceptions.Timeout:
            return "The request timed out. Please try again later or check the URL."
        except RequestException as e:
            return f"Error fetching the webpage: {str(e)}"
        except Exception as e:
            return f"An unexpected error occurred: {str(e)}"


class TavilyVisitClient(BaseVisitClient):
    name = "Tavily"

    def __init__(self, max_output_length: int = 40000):
        self.max_output_length = max_output_length
        self.api_key = os.environ.get("TAVILY_API_KEY", "")
        if not self.api_key:
            print(
                "Warning: TAVILY_API_KEY environment variable not set. Tool may not function correctly."
            )

    def forward(self, url: str) -> str:
        try:
            from tavily import TavilyClient
        except ImportError as e:
            raise ImportError(
                "You must install package `tavily` to run this tool: for instance run `pip install tavily-python`."
            ) from e

        try:
            # Initialize Tavily client
            tavily_client = TavilyClient(api_key=self.api_key)

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

        except Exception as e:
            return f"Error extracting the webpage content using Tavily: {str(e)}"


class FireCrawlVisitClient(BaseVisitClient):
    name = "FireCrawl"

    def __init__(self, max_output_length: int = 40000):
        self.max_output_length = max_output_length
        self.api_key = os.environ.get("FIRECRAWL_API_KEY", "")
        if not self.api_key:
            print(
                "Warning: FIRECRAWL_API_KEY environment variable not set. Tool may not function correctly."
            )

    def forward(self, url: str) -> str:
        """
        Scrapes the url using FireCrawl

        Returns:
            str: Scraped content as formatted text
        """
        base_url = "https://api.firecrawl.dev/v1/scrape"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {"url": url, "onlyMainContent": False, "formats": ["markdown"]}
        response = requests.request(
            "POST", base_url, headers=headers, data=json.dumps(payload)
        )
        if response.status_code == 200:
            data = response.json().get("data")
            if not data:
                return f"No content could be extracted from {url}"

            content = data["markdown"]
            return truncate_content(content, self.max_output_length)
        else:
            return f"Error scraping the webpage: {response.status_code}"


class JinaVisitClient(BaseVisitClient):
    name = "Jina"

    def __init__(self, max_output_length: int = 40000):
        self.max_output_length = max_output_length
        self.api_key = os.environ.get("JINA_API_KEY", "")
        if not self.api_key:
            print(
                "Warning: JINA_API_KEY environment variable not set. Tool may not function correctly."
            )

    def forward(self, url: str) -> str:
        """
        Scrapes the url using Jina

        Returns:
            str: Scraped content as formatted text
        """
        print("Using Jina to visit webpage")
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

            if response.status_code == 200:
                json_response = response.json()
                data = json_response["data"]
                if not data:
                    return f"No content could be extracted from {url}"
                content = data["title"] + "\n\n" + data["content"]
                return truncate_content(content, self.max_output_length)
            else:
                return f"Error scraping the webpage: {response.status_code}"
        except Exception as e:
            return f"Error scraping the webpage: {str(e)}"


def create_visit_client(max_output_length: int = 40000) -> BaseVisitClient:
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
