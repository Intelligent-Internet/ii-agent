import json
import os
import requests
import urllib
from .utils import truncate_content


class BaseSearchClient:
    """
    A base class for search clients.
    """

    max_results: int
    name: str

    def forward(self, query: str) -> str:
        raise NotImplementedError("Subclasses must implement this method.")


class JinaSearchClient(BaseSearchClient):
    """
    A client for the Jina search engine.
    """

    name = "Jina"

    def __init__(self, max_results=10, **kwargs):
        self.max_results = max_results
        self.api_key = os.environ.get("JINA_API_KEY", "")

    def _search_query_by_jina(self, query, max_results=10):
        """Searches the query using Jina AI search API."""
        jina_api_key = self.api_key
        if not jina_api_key:
            print("Error: JINA_API_KEY environment variable not set")
            return []

        url = "https://s.jina.ai/"
        params = {"q": query, "num": max_results}
        encoded_url = url + "?" + urllib.parse.urlencode(params)

        headers = {
            "Authorization": f"Bearer {jina_api_key}",
            "X-Respond-With": "no-content",
            "Accept": "application/json",
        }

        search_response = []
        try:
            response = requests.get(encoded_url, headers=headers)
            if response.status_code == 200:
                search_results = response.json()["data"]
                if search_results:
                    for result in search_results:
                        search_response.append(
                            {
                                "title": result.get("title", ""),
                                "url": result.get("url", ""),
                                "content": result.get("description", ""),
                            }
                        )
                return search_response
        except Exception as e:
            print(f"Error: {e}. Failed fetching sources. Resulting in empty response.")
            search_response = []

        return search_response

    def forward(self, query: str) -> str:
        try:
            response = self._search_query_by_jina(query, self.max_results)
            formatted_results = json.dumps(response, indent=4)
            return truncate_content(formatted_results)
        except Exception as e:
            return f"Error searching with Jina: {str(e)}"


class SerpAPISearchClient(BaseSearchClient):
    """
    A client for the SerpAPI search engine.
    """

    name = "SerpAPI"

    def __init__(self, max_results=10, **kwargs):
        self.max_results = max_results
        self.api_key = os.environ.get("SERPAPI_API_KEY", "")

    def _search_query_by_serp_api(self, query, max_results=10):
        """Searches the query using SerpAPI."""

        serpapi_api_key = self.api_key

        url = "https://serpapi.com/search.json"
        params = {"q": query, "api_key": serpapi_api_key}
        encoded_url = url + "?" + urllib.parse.urlencode(params)
        search_response = []
        try:
            response = requests.get(encoded_url)
            if response.status_code == 200:
                search_results = response.json()
                if search_results:
                    results = search_results["organic_results"]
                    results_processed = 0
                    for result in results:
                        if results_processed >= max_results:
                            break
                        search_response.append(
                            {
                                "title": result["title"],
                                "url": result["link"],
                                "content": result["snippet"],
                            }
                        )
                        results_processed += 1
        except Exception as e:
            print(f"Error: {e}. Failed fetching sources. Resulting in empty response.")
            search_response = []

        return search_response

    def forward(self, query: str) -> str:
        try:
            response = self._search_query_by_serp_api(query, self.max_results)
            formatted_results = json.dumps(response, indent=4)
            return truncate_content(formatted_results)
        except Exception as e:
            return f"Error searching with SerpAPI: {str(e)}"


class DuckDuckGoSearchClient(BaseSearchClient):
    """
    A client for the DuckDuckGo search engine.
    """

    name = "DuckDuckGo"

    def __init__(self, max_results=10, **kwargs):
        self.max_results = max_results
        try:
            from duckduckgo_search import DDGS
        except ImportError as e:
            raise ImportError(
                "You must install package `duckduckgo-search` to run this tool: for instance run `pip install duckduckgo-search`."
            ) from e
        self.ddgs = DDGS(**kwargs)

    def forward(self, query: str) -> str:
        results = self.ddgs.text(query, max_results=self.max_results)
        if len(results) == 0:
            raise Exception("No results found! Try a less restrictive/shorter query.")
        postprocessed_results = [
            f"[{result['title']}]({result['href']})\n{result['body']}"
            for result in results
        ]
        return truncate_content(
            "## Search Results\n\n" + "\n\n".join(postprocessed_results)
        )


class TavilySearchClient(BaseSearchClient):
    """
    A client for the Tavily search engine.
    """

    name = "Tavily"

    def __init__(self, max_results=5, **kwargs):
        self.max_results = max_results
        self.api_key = os.environ.get("TAVILY_API_KEY", "")
        if not self.api_key:
            print(
                "Warning: TAVILY_API_KEY environment variable not set. Tool may not function correctly."
            )

    def forward(self, query: str) -> str:
        try:
            from tavily import TavilyClient
        except ImportError as e:
            raise ImportError(
                "You must install package `tavily` to run this tool: for instance run `pip install tavily-python`."
            ) from e

        try:
            # Initialize Tavily client
            tavily_client = TavilyClient(api_key=self.api_key)

            # Perform search
            response = tavily_client.search(query=query, max_results=self.max_results)

            # Check if response contains results
            if not response or "results" not in response or not response["results"]:
                return f"No search results found for query: {query}"

            # Format and return the results
            formatted_results = json.dumps(response["results"], indent=4)
            return truncate_content(formatted_results)

        except Exception as e:
            return f"Error searching with Tavily: {str(e)}"


def create_search_client(max_results=10, **kwargs) -> BaseSearchClient:
    """
    A search client that selects from available search APIs in the following order:
    Tavily > Jina > SerpAPI > DuckDuckGo

    It defaults to DuckDuckGo if no API keys are found for the other services.
    """

    serp_api_key = os.environ.get("SERPAPI_API_KEY", "")
    if serp_api_key:
        print("Using SerpAPI to search")
        return SerpAPISearchClient(max_results=max_results, **kwargs)

    jina_api_key = os.environ.get("JINA_API_KEY", "")
    if jina_api_key:
        print("Using Jina to search")
        return JinaSearchClient(max_results=max_results, **kwargs)

    tavily_api_key = os.environ.get("TAVILY_API_KEY", "")
    if tavily_api_key:
        print("Using Tavily to search")
        return TavilySearchClient(max_results=max_results, **kwargs)

    print("Using DuckDuckGo to search")
    return DuckDuckGoSearchClient(max_results=max_results, **kwargs)
