"""Tests for WebVisitClient."""

import asyncio
import pytest
import os
from unittest.mock import Mock, AsyncMock, patch

from ii_agent.tools.clients.web_visit_client import (
    MarkdownifyVisitClient,
    TavilyVisitClient,
    FireCrawlVisitClient,
    JinaVisitClient,
    WebpageVisitException,
    ContentExtractionError,
    NetworkError,
    create_visit_client,
)


class TestMarkdownifyVisitClient:
    """Test cases for MarkdownifyVisitClient."""

    @pytest.fixture
    def markdownify_client(self):
        """Create a MarkdownifyVisitClient instance."""
        return MarkdownifyVisitClient()

    def test_markdownify_client_initialization(self, markdownify_client):
        """Test MarkdownifyVisitClient initialization."""
        assert markdownify_client.name == "Markdownify"
        assert hasattr(markdownify_client, "forward_async")
        assert callable(markdownify_client.forward_async)

    @pytest.mark.asyncio
    async def test_markdownify_visit_successful(
        self, markdownify_client, web_visit_vcr
    ):
        """Test successful web page visit with Markdownify."""
        with web_visit_vcr.use_cassette("markdownify_visit_success.json"):
            result = await markdownify_client.forward_async("https://httpbin.org/html")

            assert isinstance(result, str)
            assert len(result) > 0

    @pytest.mark.asyncio
    async def test_markdownify_visit_timeout(self, markdownify_client):
        """Test handling of request timeouts."""
        with patch(
            "ii_agent.tools.clients.web_visit_client.aiohttp.ClientSession"
        ) as mock_session_class:
            # Create proper async context manager mock
            mock_session = Mock()

            # Mock the session context manager
            mock_session_cm = Mock()
            mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_cm.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session_cm

            # Mock the get method to raise TimeoutError when used as context manager
            mock_get_cm = Mock()
            mock_get_cm.__aenter__ = AsyncMock(side_effect=asyncio.TimeoutError)
            mock_get_cm.__aexit__ = AsyncMock(return_value=None)
            mock_session.get.return_value = mock_get_cm

            with pytest.raises(NetworkError):
                await markdownify_client.forward_async("https://slow-example.com")

    @pytest.mark.asyncio
    async def test_markdownify_visit_empty_content(self, markdownify_client):
        """Test handling of empty content."""
        with patch(
            "ii_agent.tools.clients.web_visit_client.aiohttp.ClientSession"
        ) as mock_session_class:
            # Create proper mocks
            mock_session = Mock()
            mock_response = Mock()
            mock_response.text = AsyncMock(return_value="")
            mock_response.raise_for_status = Mock()

            # Mock the session context manager
            mock_session_cm = Mock()
            mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_cm.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session_cm

            # Mock the get method context manager
            mock_get_cm = Mock()
            mock_get_cm.__aenter__ = AsyncMock(return_value=mock_response)
            mock_get_cm.__aexit__ = AsyncMock(return_value=None)
            mock_session.get.return_value = mock_get_cm

            with patch("markdownify.markdownify", return_value=""):
                with pytest.raises(ContentExtractionError):
                    await markdownify_client.forward_async("https://empty-example.com")


class TestTavilyVisitClient:
    """Test cases for TavilyVisitClient."""

    @pytest.fixture
    def tavily_client(self):
        """Create a TavilyVisitClient instance."""
        return TavilyVisitClient(api_key="test-key")

    def test_tavily_client_initialization(self, tavily_client):
        """Test TavilyVisitClient initialization."""
        assert tavily_client.name == "Tavily"
        assert tavily_client.api_key == "test-key"

    def test_tavily_client_no_api_key_raises_error(self):
        """Test that missing API key raises error."""
        with pytest.raises(WebpageVisitException, match="Tavily API key not provided"):
            TavilyVisitClient(api_key="")

    @pytest.mark.asyncio
    async def test_tavily_visit_successful(self, tavily_client, web_visit_vcr):
        """Test successful web page visit with Tavily."""
        with web_visit_vcr.use_cassette("tavily_visit_success.json"):
            with patch("tavily.AsyncTavilyClient") as mock_tavily:
                mock_client = AsyncMock()
                mock_client.extract.return_value = {
                    "results": [
                        {
                            "raw_content": "# Test Page\n\nThis is test content",
                            "images": ["https://example.com/image.jpg"],
                        }
                    ]
                }
                mock_tavily.return_value = mock_client

                result = await tavily_client.forward_async("https://example.com")

                assert isinstance(result, str)
                assert "Test Page" in result
                assert "test content" in result
                assert "Images:" in result

    @pytest.mark.asyncio
    async def test_tavily_visit_no_results(self, tavily_client):
        """Test handling of no results from Tavily."""
        with patch("tavily.AsyncTavilyClient") as mock_tavily:
            mock_client = AsyncMock()
            mock_client.extract.return_value = {"results": []}
            mock_tavily.return_value = mock_client

            result = await tavily_client.forward_async("https://example.com")
            assert "No content could be extracted" in result

    @pytest.mark.asyncio
    async def test_tavily_visit_error(self, tavily_client):
        """Test error handling in Tavily client."""
        with patch("tavily.AsyncTavilyClient") as mock_tavily:
            mock_client = AsyncMock()
            mock_client.extract.side_effect = Exception("API Error")
            mock_tavily.return_value = mock_client

            with pytest.raises(WebpageVisitException, match="Error using Tavily"):
                await tavily_client.forward_async("https://example.com")


class TestFireCrawlVisitClient:
    """Test cases for FireCrawlVisitClient."""

    @pytest.fixture
    def firecrawl_client(self):
        """Create a FireCrawlVisitClient instance."""
        return FireCrawlVisitClient(api_key=os.getenv("FIRECRAWL_API_KEY", "test-key"))

    def test_firecrawl_client_initialization(self, firecrawl_client):
        """Test FireCrawlVisitClient initialization."""
        assert firecrawl_client.name == "FireCrawl"
        assert firecrawl_client.api_key == os.getenv("FIRECRAWL_API_KEY", "test-key")

    def test_firecrawl_client_no_api_key_raises_error(self):
        """Test that missing API key raises error."""
        with pytest.raises(
            WebpageVisitException, match="FireCrawl API key not provided"
        ):
            FireCrawlVisitClient(api_key="")

    @pytest.mark.asyncio
    async def test_firecrawl_visit_successful(self, firecrawl_client, web_visit_vcr):
        """Test successful web page visit with FireCrawl."""
        with web_visit_vcr.use_cassette("firecrawl_visit_success.json"):
            result = await firecrawl_client.forward_async("https://example.com")
            assert isinstance(result, str)
            assert "Example Domain" in result

    @pytest.mark.asyncio
    async def test_firecrawl_visit_no_content(self, firecrawl_client, web_visit_vcr):
        """Test handling of no content from FireCrawl."""
        with web_visit_vcr.use_cassette("firecrawl_visit_no_content.json"):
            with pytest.raises(NetworkError, match="Error making request"):
                await firecrawl_client.forward_async("https://example-unknown.com")


class TestJinaVisitClient:
    """Test cases for JinaVisitClient."""

    @pytest.fixture
    def jina_client(self):
        """Create a JinaVisitClient instance."""
        return JinaVisitClient(api_key=os.getenv("JINA_API_KEY", "test-key"))

    def test_jina_client_initialization(self, jina_client):
        """Test JinaVisitClient initialization."""
        assert jina_client.name == "Jina"
        assert jina_client.api_key == os.getenv("JINA_API_KEY", "test-key")

    def test_jina_client_no_api_key_raises_error(self):
        """Test that missing API key raises error."""
        with pytest.raises(WebpageVisitException, match="Jina API key not provided"):
            JinaVisitClient(api_key="")

    @pytest.mark.asyncio
    async def test_jina_visit_successful(self, jina_client, web_visit_vcr):
        """Test successful web page visit with Jina."""
        with web_visit_vcr.use_cassette("jina_visit_success.json"):
            result = await jina_client.forward_async("https://example.com")
            assert isinstance(result, str)
            assert "Example Domain" in result

    @pytest.mark.asyncio
    async def test_jina_visit_no_data(self, jina_client, web_visit_vcr):
        """Test handling of response with no data."""
        with web_visit_vcr.use_cassette("jina_visit_no_data.json"):
            with pytest.raises(NetworkError, match="Error making request"):
                await jina_client.forward_async("https://example-unknown.com")


class TestCreateVisitClient:
    """Test cases for create_visit_client factory function."""

    def test_create_visit_client_with_firecrawl_key(self):
        """Test creating client with FireCrawl API key."""
        with patch.dict(os.environ, {"FIRECRAWL_API_KEY": "test-key"}, clear=True):
            client = create_visit_client()
            assert isinstance(client, FireCrawlVisitClient)
            assert client.name == "FireCrawl"

    def test_create_visit_client_with_jina_key(self):
        """Test creating client with Jina API key."""
        with patch.dict(os.environ, {"JINA_API_KEY": "test-key"}, clear=True):
            client = create_visit_client()
            assert isinstance(client, JinaVisitClient)
            assert client.name == "Jina"

    def test_create_visit_client_with_tavily_key(self):
        """Test creating client with Tavily API key."""
        with patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}, clear=True):
            client = create_visit_client()
            assert isinstance(client, TavilyVisitClient)
            assert client.name == "Tavily"

    def test_create_visit_client_defaults_to_markdownify(self):
        """Test creating client defaults to Markdownify when no API keys."""
        with patch.dict(os.environ, {}, clear=True):
            client = create_visit_client()
            assert isinstance(client, MarkdownifyVisitClient)
            assert client.name == "Markdownify"

    def test_create_visit_client_priority_order(self):
        """Test client priority order: FireCrawl > Jina > Tavily > Markdownify."""
        # When all keys are present, should choose FireCrawl
        with patch.dict(
            os.environ,
            {
                "FIRECRAWL_API_KEY": "firecrawl_key",
                "JINA_API_KEY": "jina_key",
                "TAVILY_API_KEY": "tavily_key",
            },
            clear=True,
        ):
            client = create_visit_client()
            assert isinstance(client, FireCrawlVisitClient)

    def test_create_visit_client_with_settings(self):
        """Test creating client with settings object."""
        from pydantic import SecretStr

        search_config = Mock()
        mock_secret = Mock(spec=SecretStr)
        mock_secret.get_secret_value.return_value = "test-key"
        search_config.firecrawl_api_key = mock_secret
        search_config.jina_api_key = None
        search_config.tavily_api_key = None

        settings = Mock()
        settings.search_config = search_config

        client = create_visit_client(settings=settings)
        assert isinstance(client, FireCrawlVisitClient)

    def test_create_visit_client_custom_max_length(self):
        """Test creating client with custom max output length."""
        client = create_visit_client(max_output_length=5000)
        assert client.max_output_length == 5000


class TestSyncMethods:
    """Test cases for synchronous wrapper methods."""

    def test_markdownify_forward_sync(self):
        """Test synchronous forward method."""
        client = MarkdownifyVisitClient()

        with patch.object(client, "forward_async") as mock_async:
            mock_async.return_value = "test result"

            result = client.forward("https://example.com")

            assert result == "test result"
            mock_async.assert_called_once_with("https://example.com")

    def test_tavily_forward_sync(self):
        """Test synchronous forward method for Tavily."""
        client = TavilyVisitClient(api_key="test-key")

        with patch.object(client, "forward_async") as mock_async:
            mock_async.return_value = "test result"

            result = client.forward("https://example.com")

            assert result == "test result"
            mock_async.assert_called_once_with("https://example.com")
