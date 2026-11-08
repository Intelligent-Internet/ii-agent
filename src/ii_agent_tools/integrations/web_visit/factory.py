from typing import List

from ii_agent_tools.logger import get_logger
from ii_agent_tools.integrations.web_visit.base import (
    BaseWebVisitClient,
    WebVisitServiceType,
)
from ii_agent_tools.integrations.web_visit.firecrawl import FireCrawlWebVisitClient
from ii_agent_tools.integrations.web_visit.gemini import GeminiWebVisitClient
from ii_agent_tools.integrations.web_visit.jina import JinaWebVisitClient
from ii_agent_tools.integrations.web_visit.outcrawl import OutcrawlWebVisitClient
from ii_agent_tools.integrations.web_visit.tavily import TavilyWebVisitClient
from ii_agent_tools.integrations.web_visit.beautifulsoup import (
    BeautifulSoupWebVisitClient,
)
from ii_agent_tools.integrations.web_visit.config import WebVisitConfig

logger = get_logger("ii_tool.web_visit.factory")


def create_web_visit_client(
    settings: WebVisitConfig,
    client_type: WebVisitServiceType | None = None,
) -> BaseWebVisitClient:
    """
    Factory function that creates a web visit client based on available API keys.
    Priority order: FireCrawl > Gemini > Jina > Tavily > Outcrawl > BeautifulSoup

    Args:
        settings: Settings object containing API keys
        client_type: Specific client type to use (optional)

    Returns:
        BaseWebVisitClient: An instance of a web visit client
    """
    firecrawl_key = settings.firecrawl_api_key
    gemini_key = settings.gemini_api_key
    jina_key = settings.jina_api_key
    tavily_key = settings.tavily_api_key
    outcrawl_key = settings.outcrawl_api_key

    priority_order = ["firecrawl", "gemini", "jina", "tavily", "outcrawl", "beautifulsoup"]
    display_names = {
        "firecrawl": "FireCrawl",
        "gemini": "Gemini",
        "jina": "Jina",
        "tavily": "Tavily",
        "outcrawl": "Outcrawl",
        "beautifulsoup": "BeautifulSoup",
    }
    client_keys = {
        "firecrawl": firecrawl_key,
        "gemini": gemini_key,
        "jina": jina_key,
        "tavily": tavily_key,
        "outcrawl": outcrawl_key,
        "beautifulsoup": True,
    }

    def _get_next_available_client(current_client: str) -> str:
        try:
            current_index = priority_order.index(current_client)
        except ValueError:
            current_index = -1
        for candidate in priority_order[current_index + 1 :]:
            if candidate == "beautifulsoup" or client_keys.get(candidate):
                return display_names[candidate]
        return display_names["beautifulsoup"]

    if client_type == "firecrawl":
        if not firecrawl_key:
            next_client = _get_next_available_client("firecrawl")
            logger.warning("FireCrawl API key not found. Falling back to %s client", next_client)
        else:
            logger.info("Using FireCrawl Client")
            return FireCrawlWebVisitClient(api_key=firecrawl_key)

    if client_type == "gemini":
        if not gemini_key:
            next_client = _get_next_available_client("gemini")
            logger.warning("Gemini API key not found. Falling back to %s client", next_client)
        else:
            logger.info("Using Gemini Client")
            return GeminiWebVisitClient(api_key=gemini_key)

    if client_type == "jina":
        if not jina_key:
            next_client = _get_next_available_client("jina")
            logger.warning("Jina API key not found. Falling back to %s client", next_client)
        else:
            logger.info("Using Jina Client")
            return JinaWebVisitClient(api_key=jina_key)

    if client_type == "tavily":
        if not tavily_key:
            next_client = _get_next_available_client("tavily")
            logger.warning("Tavily API key not found. Falling back to %s client", next_client)
        else:
            logger.info("Using Tavily Client")
            return TavilyWebVisitClient(api_key=tavily_key)

    if client_type == "outcrawl":
        if not outcrawl_key:
            next_client = _get_next_available_client("outcrawl")
            logger.warning("Outcrawl API key not found. Falling back to %s client", next_client)
        else:
            logger.info("Using Outcrawl Client")
            return OutcrawlWebVisitClient(api_key=outcrawl_key)

    if client_type == "beautifulsoup":
        logger.info("Using Soup Client")
        return BeautifulSoupWebVisitClient()

    # Default priority order if no client_type specified
    if firecrawl_key:
        logger.info("Using FireCrawl to visit webpage")
        return FireCrawlWebVisitClient(api_key=firecrawl_key)

    if gemini_key:
        logger.info("Using Gemini to visit webpage")
        return GeminiWebVisitClient(api_key=gemini_key)

    if jina_key:
        logger.info("Using Jina to visit webpage")
        return JinaWebVisitClient(api_key=jina_key)

    if tavily_key:
        logger.info("Using Tavily to visit webpage")
        return TavilyWebVisitClient(api_key=tavily_key)

    if outcrawl_key:
        logger.info("Using Outcrawl to visit webpage")
        return OutcrawlWebVisitClient(api_key=outcrawl_key)

    # Fall back to BeautifulSoup if no API keys are available
    logger.info("Using BeautifulSoup to visit webpage (no API keys found)")
    return BeautifulSoupWebVisitClient()


def create_all_web_visit_clients(settings: WebVisitConfig) -> List[BaseWebVisitClient]:
    """
    Creates a list of all available web visit clients in fallback order.
    Priority order: FireCrawl > Jina > Tavily > Outcrawl > BeautifulSoup

    Args:
        settings: Settings object containing API keys

    Returns:
        List[BaseWebVisitClient]: List of available web visit clients
    """
    clients = []

    # Add clients in priority order: FireCrawl > Jina > Tavily > Outcrawl > BeautifulSoup
    firecrawl_key = settings.firecrawl_api_key
    jina_key = settings.jina_api_key
    tavily_key = settings.tavily_api_key
    gemini_key = settings.gemini_api_key
    outcrawl_key = settings.outcrawl_api_key

    if firecrawl_key:
        try:
            clients.append(FireCrawlWebVisitClient(api_key=firecrawl_key))
        except Exception:
            pass

    if jina_key:
        try:
            clients.append(JinaWebVisitClient(api_key=jina_key))
        except Exception:
            pass

    if tavily_key:
        try:
            clients.append(TavilyWebVisitClient(api_key=tavily_key))
        except Exception:
            pass

    if outcrawl_key:
        try:
            clients.append(OutcrawlWebVisitClient(api_key=outcrawl_key))
        except Exception:
            pass

    # Always add BeautifulSoup as the last fallback
    clients.append(BeautifulSoupWebVisitClient())

    return clients
