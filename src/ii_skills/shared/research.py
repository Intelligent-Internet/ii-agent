"""
Research Integration for Skills

Provides unified access to ii-agent's research capabilities:
- Web search (SerpAPI, DuckDuckGo, Brave)
- Content extraction (FireCrawl, Jina, Tavily)
- Deep research via II-Researcher

Usage:
    from ii_skills.shared.research import ResearchClient, get_research_client

    client = get_research_client()

    # Quick web search
    results = await client.search("company name competitors")

    # Extract content from URL
    content = await client.extract_url("https://example.com/article")

    # Deep research on a topic
    report = await client.research("Investment thesis for XYZ Corp")
"""

import logging
import asyncio
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Web search result."""
    query: str
    title: str
    url: str
    snippet: str
    source: str = "web"


@dataclass
class ResearchReport:
    """Research report output."""
    topic: str
    summary: str
    key_findings: List[str]
    sources: List[Dict[str, str]]
    full_content: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class ResearchClient:
    """
    Unified research client for skills.

    Wraps ii-agent's web search and content extraction tools
    with a simple interface for skills to use.
    """

    def __init__(self):
        """Initialize the research client."""
        self._search_client = None
        self._visit_client = None
        self._initialized = False
        self._available_tools = {}

    async def _ensure_initialized(self):
        """Lazy initialization of research tools."""
        if self._initialized:
            return

        # Try to load web search client
        try:
            from ii_tool.integrations.web_search.factory import create_web_search_client
            from ii_tool.integrations.web_search.config import WebSearchConfig

            config = WebSearchConfig()
            self._search_client = create_web_search_client(config)
            self._available_tools["search"] = True
            logger.info(f"Web search client initialized: {type(self._search_client).__name__}")
        except ImportError as e:
            logger.warning(f"Web search not available: {e}")
            self._available_tools["search"] = False
        except Exception as e:
            logger.warning(f"Failed to initialize web search: {e}")
            self._available_tools["search"] = False

        # Try to load web visit client
        try:
            from ii_tool.integrations.web_visit.factory import create_web_visit_client
            from ii_tool.integrations.web_visit.config import WebVisitConfig, CompressorConfig

            config = WebVisitConfig()
            compressor_config = CompressorConfig()
            self._visit_client = create_web_visit_client(config, compressor_config)
            self._available_tools["extract"] = True
            logger.info(f"Web visit client initialized: {type(self._visit_client).__name__}")
        except ImportError as e:
            logger.warning(f"Web visit not available: {e}")
            self._available_tools["extract"] = False
        except Exception as e:
            logger.warning(f"Failed to initialize web visit: {e}")
            self._available_tools["extract"] = False

        self._initialized = True

    @property
    def is_available(self) -> bool:
        """Check if any research tools are available."""
        return any(self._available_tools.values())

    async def search(
        self,
        query: str,
        max_results: int = 10,
    ) -> List[SearchResult]:
        """
        Perform a web search.

        Args:
            query: Search query
            max_results: Maximum number of results

        Returns:
            List of SearchResult objects
        """
        await self._ensure_initialized()

        if not self._available_tools.get("search"):
            logger.warning("Web search not available, using fallback")
            return await self._fallback_search(query, max_results)

        try:
            result = await self._search_client.search(query, max_results=max_results)
            return [
                SearchResult(
                    query=r.get("query", query),
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    snippet=r.get("content", r.get("snippet", "")),
                    source="web_search",
                )
                for r in result.result
            ]
        except Exception as e:
            logger.error(f"Web search failed: {e}")
            return await self._fallback_search(query, max_results)

    async def batch_search(
        self,
        queries: List[str],
        max_results: int = 5,
    ) -> Dict[str, List[SearchResult]]:
        """
        Perform multiple web searches.

        Args:
            queries: List of search queries
            max_results: Maximum results per query

        Returns:
            Dictionary mapping query to results
        """
        await self._ensure_initialized()

        results = {}
        if self._available_tools.get("search"):
            try:
                batch_result = await self._search_client.batch_search(queries, max_results=max_results)
                for i, query in enumerate(queries):
                    if i < len(batch_result):
                        results[query] = [
                            SearchResult(
                                query=query,
                                title=r.get("title", ""),
                                url=r.get("url", ""),
                                snippet=r.get("content", ""),
                                source="web_search",
                            )
                            for r in batch_result[i].result
                        ]
                    else:
                        results[query] = []
                return results
            except Exception as e:
                logger.error(f"Batch search failed: {e}")

        # Fallback to individual searches
        for query in queries:
            results[query] = await self.search(query, max_results)
        return results

    async def extract_url(
        self,
        url: str,
        query: Optional[str] = None,
    ) -> str:
        """
        Extract content from a URL.

        Args:
            url: URL to extract content from
            query: Optional query to focus extraction

        Returns:
            Extracted content as markdown
        """
        await self._ensure_initialized()

        if not self._available_tools.get("extract"):
            return await self._fallback_extract(url)

        try:
            if query:
                result = await self._visit_client.extract_compress(url, query)
            else:
                result = await self._visit_client.extract(url)
            return result.content
        except Exception as e:
            logger.error(f"URL extraction failed: {e}")
            return await self._fallback_extract(url)

    async def extract_urls(
        self,
        urls: List[str],
        query: Optional[str] = None,
    ) -> Dict[str, str]:
        """
        Extract content from multiple URLs.

        Args:
            urls: List of URLs
            query: Optional query to focus extraction

        Returns:
            Dictionary mapping URL to content
        """
        await self._ensure_initialized()

        results = {}
        if self._available_tools.get("extract") and query:
            try:
                result = await self._visit_client.batch_extract_compress(urls, query)
                # Parse batch result (format varies by client)
                for url in urls:
                    results[url] = result.content if hasattr(result, 'content') else ""
                return results
            except Exception as e:
                logger.error(f"Batch extraction failed: {e}")

        # Fallback to individual extraction
        for url in urls:
            try:
                results[url] = await self.extract_url(url, query)
            except Exception as e:
                results[url] = f"Error extracting {url}: {e}"
        return results

    async def search_and_extract(
        self,
        query: str,
        max_results: int = 3,
        extract_top_n: int = 2,
    ) -> Dict[str, Any]:
        """
        Search and extract content from top results.

        Args:
            query: Search query
            max_results: Maximum search results
            extract_top_n: Number of top results to extract content from

        Returns:
            Dictionary with search results and extracted content
        """
        # Search
        search_results = await self.search(query, max_results)

        # Extract from top results
        urls_to_extract = [r.url for r in search_results[:extract_top_n] if r.url]
        extracted = {}
        for url in urls_to_extract:
            try:
                extracted[url] = await self.extract_url(url, query)
            except Exception as e:
                extracted[url] = f"Error: {e}"

        return {
            "query": query,
            "search_results": search_results,
            "extracted_content": extracted,
        }

    async def research(
        self,
        topic: str,
        depth: str = "basic",
        focus_areas: Optional[List[str]] = None,
    ) -> ResearchReport:
        """
        Conduct deep research on a topic.

        Args:
            topic: Research topic
            depth: "basic" or "advanced"
            focus_areas: Specific areas to focus on

        Returns:
            ResearchReport with findings
        """
        # Build search queries
        queries = [topic]
        if focus_areas:
            queries.extend([f"{topic} {area}" for area in focus_areas[:3]])

        # Perform searches
        all_results = []
        for query in queries:
            results = await self.search(query, max_results=5)
            all_results.extend(results)

        # Extract from top unique URLs
        seen_urls = set()
        urls_to_extract = []
        for result in all_results:
            if result.url and result.url not in seen_urls:
                seen_urls.add(result.url)
                urls_to_extract.append(result.url)
                if len(urls_to_extract) >= 5:
                    break

        # Extract content
        extracted_content = []
        for url in urls_to_extract:
            try:
                content = await self.extract_url(url, topic)
                if content and len(content) > 100:
                    extracted_content.append({
                        "url": url,
                        "content": content[:5000],  # Limit content length
                    })
            except Exception as e:
                logger.warning(f"Failed to extract {url}: {e}")

        # Build report
        sources = [
            {"title": r.title, "url": r.url, "snippet": r.snippet}
            for r in all_results[:10]
        ]

        key_findings = []
        for result in all_results[:5]:
            if result.snippet:
                key_findings.append(result.snippet[:200])

        full_content = "\n\n---\n\n".join([
            f"## Source: {ec['url']}\n\n{ec['content']}"
            for ec in extracted_content
        ])

        return ResearchReport(
            topic=topic,
            summary=f"Research on '{topic}' with {len(all_results)} search results and {len(extracted_content)} extracted sources.",
            key_findings=key_findings,
            sources=sources,
            full_content=full_content,
            metadata={
                "queries": queries,
                "depth": depth,
                "focus_areas": focus_areas,
                "urls_extracted": len(extracted_content),
            },
        )

    async def _fallback_search(
        self,
        query: str,
        max_results: int,
    ) -> List[SearchResult]:
        """Fallback search using DuckDuckGo directly."""
        try:
            from duckduckgo_search import DDGS

            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results))
                return [
                    SearchResult(
                        query=query,
                        title=r.get("title", ""),
                        url=r.get("href", r.get("link", "")),
                        snippet=r.get("body", r.get("snippet", "")),
                        source="duckduckgo_fallback",
                    )
                    for r in results
                ]
        except Exception as e:
            logger.error(f"Fallback search failed: {e}")
            return []

    async def _fallback_extract(self, url: str) -> str:
        """Fallback URL extraction using requests + BeautifulSoup."""
        try:
            import requests
            from bs4 import BeautifulSoup

            response = requests.get(url, timeout=10, headers={
                "User-Agent": "Mozilla/5.0 (compatible; ResearchBot/1.0)"
            })
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")

            # Remove script and style elements
            for element in soup(["script", "style", "nav", "footer", "header"]):
                element.decompose()

            # Get text
            text = soup.get_text(separator="\n", strip=True)

            # Clean up whitespace
            lines = [line.strip() for line in text.split("\n") if line.strip()]
            return "\n".join(lines[:200])  # Limit to first 200 lines

        except Exception as e:
            logger.error(f"Fallback extraction failed: {e}")
            return f"Error extracting content from {url}: {e}"


# Global client instance
_research_client: Optional[ResearchClient] = None


def get_research_client() -> ResearchClient:
    """Get or create the global ResearchClient instance."""
    global _research_client
    if _research_client is None:
        _research_client = ResearchClient()
    return _research_client
