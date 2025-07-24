import aiohttp
import json
import urllib
from typing import Optional
from ii_tool.core.config import ImageSearchConfig

class ImageSearchClient:
    """
    A client for the SerpAPI search engine.
    """

    name = "ImageSerpAPI"

    def __init__(self, max_results=10, api_key: Optional[str] = None, **kwargs):
        self.max_results = max_results
        self.api_key = api_key or ""

    async def _search_query_by_serp_api(self, query, max_results=10):
        """Searches the query using SerpAPI."""

        serpapi_api_key = self.api_key

        url = "https://serpapi.com/search.json"
        params = {"q": query, "api_key": serpapi_api_key, "engine": "google_images"}
        encoded_url = url + "?" + urllib.parse.urlencode(params)
        search_response = []
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(encoded_url) as response:
                    if response.status == 200:
                        search_results = await response.json()
                        if search_results:
                            results = search_results["images_results"]
                            results_processed = 0
                            for result in results:
                                if results_processed >= max_results:
                                    break
                                search_response.append(
                                    {
                                        "title": result["title"],
                                        "image_url": result["original"],
                                        "width": result["original_width"],
                                        "height": result["original_height"],
                                    }
                                )
                                results_processed += 1
        except Exception as e:
            print(f"Error: {e}. Failed fetching sources. Resulting in empty response.")
            search_response = []

        return search_response

    async def forward_async(self, query: str) -> str:
        try:
            response = await self._search_query_by_serp_api(query, self.max_results)
            formatted_results = json.dumps(response, indent=4)
            return formatted_results
        except Exception as e:
            return f"Error searching with SerpAPI: {str(e)}"


def create_image_search_client(
    settings: ImageSearchConfig, **kwargs
) -> Optional[ImageSearchClient]:
    """
    A search client that selects from available image search APIs.

    Args:
        settings: Settings object containing API keys
        max_results: Maximum number of results to return
        **kwargs: Additional arguments
    """

    serpapi_key = settings.serpapi_api_key
    max_results = settings.max_results

    if serpapi_key:
        print("Using SerpAPI to search for images")
        return ImageSearchClient(max_results=max_results, api_key=serpapi_key, **kwargs)
    else:
        print("No image search API key found")
        return None