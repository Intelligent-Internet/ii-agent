"""Tests for WebSearchClient."""

import pytest
import os
import json
from unittest.mock import Mock, AsyncMock, patch

from ii_agent.tools.clients.web_search_client import (
    JinaSearchClient,
    SerpAPISearchClient,
    DuckDuckGoSearchClient,
    TavilySearchClient,
    ImageSearchClient,
    create_search_client,
    create_image_search_client,
)


class TestJinaSearchClient:
    """Test cases for JinaSearchClient."""

    @pytest.fixture
    def jina_client(self):
        """Create a JinaSearchClient instance."""
        return JinaSearchClient(api_key=os.getenv("JINA_API_KEY", "test-key"))

    def test_jina_client_initialization(self, jina_client):
        """Test JinaSearchClient initialization."""
        assert jina_client.name == "Jina"
        assert jina_client.api_key == os.getenv("JINA_API_KEY", "test-key")
        assert jina_client.max_results == 10

    @pytest.mark.asyncio
    async def test_jina_search_successful(self, jina_client, web_search_vcr):
        """Test successful search with Jina."""
        with web_search_vcr.use_cassette("jina_search_success.json"):
            result = await jina_client.forward_async("Intelligent Internet ii.inc")

            assert isinstance(result, str)
            data = json.loads(result)
            assert len(data) > 0
            assert "https://ii.inc" in result
            assert "Intelligent Internet" in result

    @pytest.mark.asyncio
    async def test_jina_search_no_api_key(self):
        """Test Jina search with no API key."""
        client = JinaSearchClient(api_key="")
        result = await client.forward_async("test query")
        assert json.loads(result) == []

    @pytest.mark.asyncio
    async def test_jina_search_network_error(self, jina_client):
        """Test handling of network errors in Jina search."""
        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = AsyncMock()
            mock_session.get.side_effect = Exception("Network error")
            mock_session_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_session_class.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await jina_client.forward_async("test query")
            assert json.loads(result) == []

    @pytest.mark.asyncio
    async def test_jina_search_http_error(self, jina_client):
        """Test handling of HTTP errors in Jina search."""
        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status = 404
            mock_session.get.return_value.__aenter__ = AsyncMock(
                return_value=mock_response
            )
            mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_session_class.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await jina_client.forward_async("test query")
            assert json.loads(result) == []


class TestSerpAPISearchClient:
    """Test cases for SerpAPISearchClient."""

    @pytest.fixture
    def serpapi_client(self):
        """Create a SerpAPISearchClient instance."""
        return SerpAPISearchClient(api_key=os.getenv("SERPAPI_API_KEY", "test-key"))

    @pytest.fixture
    def serp_api_no_api_key_client(self):
        """Create a SerpAPISearchClient instance."""
        return SerpAPISearchClient(api_key="")

    def test_serpapi_client_initialization(self, serpapi_client):
        """Test SerpAPISearchClient initialization."""
        assert serpapi_client.name == "SerpAPI"
        assert serpapi_client.api_key == os.getenv("SERPAPI_API_KEY", "test-key")
        assert serpapi_client.max_results == 10

    @pytest.mark.asyncio
    async def test_serpapi_search_successful(self, serpapi_client, web_search_vcr):
        """Test successful search with SerpAPI."""
        with web_search_vcr.use_cassette("serpapi_search_success.json"):
            result = await serpapi_client.forward_async("Intelligent Internet ii.inc")

            assert isinstance(result, str)
            data = json.loads(result)
            assert len(data) > 0
            assert "https://ii.inc" in result
            assert "Intelligent Internet" in result

    @pytest.mark.asyncio
    async def test_serpapi_search_max_results_limit(
        self, serpapi_client, web_search_vcr
    ):
        """Test SerpAPI search respects max_results limit."""
        serpapi_client.max_results = 1

        with web_search_vcr.use_cassette("serpapi_search_max_results_limit.json"):
            result = await serpapi_client.forward_async("Intelligent Internet ii.inc")

            assert isinstance(result, str)
            data = json.loads(result)
            assert len(data) == 1

    @pytest.mark.asyncio
    async def test_serpapi_search_no_api_key(
        self, serp_api_no_api_key_client, web_search_vcr
    ):
        """Test SerpAPI search with no API key."""
        with web_search_vcr.use_cassette("serpapi_search_no_api_key.json"):
            result = await serp_api_no_api_key_client.forward_async("test query")
            assert json.loads(result) == []


class TestDuckDuckGoSearchClient:
    """Test cases for DuckDuckGoSearchClient."""

    @pytest.fixture
    def ddg_client(self):
        """Create a DuckDuckGoSearchClient instance."""
        with patch("duckduckgo_search.DDGS"):
            return DuckDuckGoSearchClient()

    def test_ddg_client_initialization(self, ddg_client):
        """Test DuckDuckGoSearchClient initialization."""
        assert ddg_client.name == "DuckDuckGo"
        assert ddg_client.max_results == 10

    def test_ddg_client_missing_import_raises_error(self):
        """Test that missing duckduckgo-search package raises ImportError."""
        with patch.dict("sys.modules", {"duckduckgo_search": None}):
            with pytest.raises(
                ImportError, match="You must install package `duckduckgo-search`"
            ):
                DuckDuckGoSearchClient()

    @pytest.mark.asyncio
    async def test_ddg_search_successful(self, ddg_client, web_search_vcr):
        """Test successful search with DuckDuckGo."""
        with web_search_vcr.use_cassette("ddg_search_success.json"):
            mock_results = [
                {
                    "title": "Python Tutorial",
                    "href": "https://example.com/python",
                    "body": "Learn Python programming",
                },
                {
                    "title": "Advanced Python",
                    "href": "https://example.com/advanced",
                    "body": "Advanced Python concepts",
                },
            ]
            ddg_client.ddgs.text = Mock(return_value=mock_results)

            result = await ddg_client.forward_async("python tutorial")

            assert isinstance(result, str)
            assert "Python Tutorial" in result
            assert "https://example.com/python" in result
            assert "Learn Python programming" in result

    @pytest.mark.asyncio
    async def test_ddg_search_no_results_raises_error(self, ddg_client):
        """Test that no results raises an exception."""
        ddg_client.ddgs.text = Mock(return_value=[])

        with pytest.raises(Exception, match="No results found"):
            await ddg_client.forward_async("nonexistent query")

    @pytest.mark.asyncio
    async def test_ddg_search_thread_execution(self, ddg_client):
        """Test that DuckDuckGo search runs in thread executor."""
        ddg_client.ddgs.text = Mock(
            return_value=[
                {"title": "Test", "href": "https://example.com", "body": "Test content"}
            ]
        )

        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(
                return_value=[
                    {
                        "title": "Test",
                        "href": "https://example.com",
                        "body": "Test content",
                    }
                ]
            )

            result = await ddg_client.forward_async("test query")

            mock_loop.return_value.run_in_executor.assert_called_once()
            assert "Test" in result


class TestTavilySearchClient:
    """Test cases for TavilySearchClient."""

    @pytest.fixture
    def tavily_client(self):
        """Create a TavilySearchClient instance."""
        return TavilySearchClient(api_key="test-key")

    def test_tavily_client_initialization(self, tavily_client):
        """Test TavilySearchClient initialization."""
        assert tavily_client.name == "Tavily"
        assert tavily_client.api_key == "test-key"
        assert tavily_client.max_results == 5

    def test_tavily_client_no_api_key_warning(self):
        """Test warning when no API key provided."""
        with patch("builtins.print") as mock_print:
            TavilySearchClient(api_key="")
            mock_print.assert_called_with(
                "Warning: Tavily API key not provided. Tool may not function correctly."
            )

    @pytest.mark.asyncio
    async def test_tavily_search_successful(self, tavily_client, web_search_vcr):
        """Test successful search with Tavily."""
        with web_search_vcr.use_cassette("tavily_search_success.json"):
            with patch("tavily.AsyncTavilyClient") as mock_tavily:
                mock_client = AsyncMock()
                mock_client.search.return_value = {
                    "results": [
                        {
                            "title": "Python Tutorial",
                            "url": "https://example.com/python",
                            "content": "Learn Python programming",
                        },
                        {
                            "title": "Advanced Python",
                            "url": "https://example.com/advanced",
                            "content": "Advanced Python concepts",
                        },
                    ]
                }
                mock_tavily.return_value = mock_client

                result = await tavily_client.forward_async("python tutorial")

                assert isinstance(result, str)
                data = json.loads(result)
                assert len(data) == 2
                assert data[0]["title"] == "Python Tutorial"

    @pytest.mark.asyncio
    async def test_tavily_search_no_results(self, tavily_client):
        """Test handling of no results from Tavily."""
        with patch("tavily.AsyncTavilyClient") as mock_tavily:
            mock_client = AsyncMock()
            mock_client.search.return_value = {"results": []}
            mock_tavily.return_value = mock_client

            result = await tavily_client.forward_async("nonexistent query")
            assert "No search results found" in result

    @pytest.mark.asyncio
    async def test_tavily_search_missing_import_raises_error(self, tavily_client):
        """Test that missing tavily package raises ImportError."""
        with patch.dict("sys.modules", {"tavily": None}):
            with pytest.raises(ImportError, match="You must install package `tavily`"):
                await tavily_client.forward_async("test query")

    @pytest.mark.asyncio
    async def test_tavily_search_api_error(self, tavily_client):
        """Test handling of API errors in Tavily search."""
        with patch("tavily.AsyncTavilyClient") as mock_tavily:
            mock_client = AsyncMock()
            mock_client.search.side_effect = Exception("API Error")
            mock_tavily.return_value = mock_client

            result = await tavily_client.forward_async("test query")
            assert "Error searching with Tavily" in result


class TestImageSearchClient:
    """Test cases for ImageSearchClient."""

    @pytest.fixture
    def image_client(self):
        """Create an ImageSearchClient instance."""
        return ImageSearchClient(api_key=os.getenv("SERPAPI_API_KEY", "test-key"))

    def test_image_client_initialization(self, image_client):
        """Test ImageSearchClient initialization."""
        assert image_client.name == "ImageSerpAPI"
        assert image_client.api_key == os.getenv("SERPAPI_API_KEY", "test-key")
        assert image_client.max_results == 10

    @pytest.mark.asyncio
    async def test_image_search_successful(self, image_client, web_search_vcr):
        """Test successful image search."""
        with web_search_vcr.use_cassette("image_search_success.json"):
            result = await image_client.forward_async("python logo")

            assert isinstance(result, str)
            data = json.loads(result)
            assert len(data) > 0

    @pytest.mark.asyncio
    async def test_image_search_max_results_limit(self, image_client, web_search_vcr):
        """Test image search respects max_results limit."""
        image_client.max_results = 1

        with web_search_vcr.use_cassette("image_search_max_results_limit.json"):
            result = await image_client.forward_async("test query")
            data = json.loads(result)
            assert len(data) == 1

    @pytest.mark.asyncio
    async def test_image_search_network_error(self, image_client):
        """Test handling of network errors in image search."""
        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = AsyncMock()
            mock_session.get.side_effect = Exception("Network error")
            mock_session_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_session_class.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await image_client.forward_async("test query")
            assert json.loads(result) == []


class TestCreateSearchClient:
    """Test cases for create_search_client factory function."""

    def test_create_search_client_with_serpapi_key(self):
        """Test creating client with SerpAPI key."""
        with patch.dict(os.environ, {"SERPAPI_API_KEY": "test-key"}, clear=True):
            client = create_search_client()
            assert isinstance(client, SerpAPISearchClient)
            assert client.name == "SerpAPI"

    def test_create_search_client_with_jina_key(self):
        """Test creating client with Jina API key."""
        with patch.dict(os.environ, {"JINA_API_KEY": "test-key"}, clear=True):
            client = create_search_client()
            assert isinstance(client, JinaSearchClient)
            assert client.name == "Jina"

    def test_create_search_client_with_tavily_key(self):
        """Test creating client with Tavily API key."""
        with patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}, clear=True):
            client = create_search_client()
            assert isinstance(client, TavilySearchClient)
            assert client.name == "Tavily"

    def test_create_search_client_defaults_to_duckduckgo(self):
        """Test creating client defaults to DuckDuckGo when no API keys."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("duckduckgo_search.DDGS"):
                client = create_search_client()
                assert isinstance(client, DuckDuckGoSearchClient)
                assert client.name == "DuckDuckGo"

    def test_create_search_client_priority_order(self):
        """Test client priority order: SerpAPI > Jina > Tavily > DuckDuckGo."""
        # When all keys are present, should choose SerpAPI
        with patch.dict(
            os.environ,
            {
                "SERPAPI_API_KEY": "serpapi_key",
                "JINA_API_KEY": "jina_key",
                "TAVILY_API_KEY": "tavily_key",
            },
            clear=True,
        ):
            client = create_search_client()
            assert isinstance(client, SerpAPISearchClient)

    def test_create_search_client_with_settings(self):
        """Test creating client with settings object."""
        search_config = Mock()
        search_config.serpapi_api_key = Mock()
        search_config.serpapi_api_key.get_secret_value.return_value = "test-key"
        search_config.jina_api_key = None
        search_config.tavily_api_key = None

        settings = Mock()
        settings.search_config = search_config

        client = create_search_client(settings=settings)
        assert isinstance(client, SerpAPISearchClient)

    def test_create_search_client_custom_max_results(self):
        """Test creating client with custom max_results."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("duckduckgo_search.DDGS"):
                client = create_search_client(max_results=20)
                assert client.max_results == 20


class TestCreateImageSearchClient:
    """Test cases for create_image_search_client factory function."""

    def test_create_image_search_client_with_serpapi_key(self):
        """Test creating image client with SerpAPI key."""
        with patch.dict(os.environ, {"SERPAPI_API_KEY": "test-key"}, clear=True):
            client = create_image_search_client()
            assert isinstance(client, ImageSearchClient)
            assert client.name == "ImageSerpAPI"

    def test_create_image_search_client_no_key_returns_none(self):
        """Test creating image client with no API key returns None."""
        with patch.dict(os.environ, {}, clear=True):
            client = create_image_search_client()
            assert client is None

    def test_create_image_search_client_with_settings(self):
        """Test creating image client with settings object."""
        search_config = Mock()
        search_config.serpapi_api_key = Mock()
        search_config.serpapi_api_key.get_secret_value.return_value = "test-key"

        settings = Mock()
        settings.search_config = search_config

        client = create_image_search_client(settings=settings)
        assert isinstance(client, ImageSearchClient)

    def test_create_image_search_client_custom_max_results(self):
        """Test creating image client with custom max_results."""
        with patch.dict(os.environ, {"SERPAPI_API_KEY": "test-key"}, clear=True):
            client = create_image_search_client(max_results=20)
            assert client and client.max_results == 20


class TestSyncMethods:
    """Test cases for synchronous wrapper methods."""

    def test_jina_forward_sync(self):
        """Test synchronous forward method for Jina."""
        client = JinaSearchClient(api_key="test-key")

        with patch.object(client, "forward_async") as mock_async:
            mock_async.return_value = "test result"

            result = client.forward("test query")

            assert result == "test result"
            mock_async.assert_called_once_with("test query")

    def test_serpapi_forward_sync(self):
        """Test synchronous forward method for SerpAPI."""
        client = SerpAPISearchClient(api_key="test-key")

        with patch.object(client, "forward_async") as mock_async:
            mock_async.return_value = "test result"

            result = client.forward("test query")

            assert result == "test result"
            mock_async.assert_called_once_with("test query")

    def test_ddg_forward_sync(self):
        """Test synchronous forward method for DuckDuckGo."""
        with patch("duckduckgo_search.DDGS"):
            client = DuckDuckGoSearchClient()

        with patch.object(client, "forward_async") as mock_async:
            mock_async.return_value = "test result"

            result = client.forward("test query")

            assert result == "test result"
            mock_async.assert_called_once_with("test query")

    def test_tavily_forward_sync(self):
        """Test synchronous forward method for Tavily."""
        client = TavilySearchClient(api_key="test-key")

        with patch.object(client, "forward_async") as mock_async:
            mock_async.return_value = "test result"

            result = client.forward("test query")

            assert result == "test result"
            mock_async.assert_called_once_with("test query")


class TestSpecialCharactersAndEdgeCases:
    """Test cases for special characters and edge cases."""

    @pytest.mark.asyncio
    async def test_search_with_unicode_query(self):
        """Test search with unicode characters."""
        client = JinaSearchClient(api_key="test-key")

        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json.return_value = {"data": []}
            mock_session.get.return_value.__aenter__ = AsyncMock(
                return_value=mock_response
            )
            mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_session_class.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await client.forward_async("python test 测试 & symbols")
            assert isinstance(result, str)
            assert json.loads(result) == []

    @pytest.mark.asyncio
    async def test_search_with_empty_query(self):
        """Test search with empty query string."""
        client = JinaSearchClient(api_key="test-key")
        result = await client.forward_async("")
        assert json.loads(result) == []

    @pytest.mark.asyncio
    async def test_search_with_very_long_query(self):
        """Test search with very long query."""
        client = JinaSearchClient(api_key="test-key")
        long_query = "a" * 1000

        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json.return_value = {"data": []}
            mock_session.get.return_value.__aenter__ = AsyncMock(
                return_value=mock_response
            )
            mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_session_class.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await client.forward_async(long_query)
            assert isinstance(result, str)


class TestAsyncBehavior:
    """Test cases for async behavior verification."""

    def test_all_forward_async_methods_are_coroutines(self):
        """Test that all forward_async methods are coroutines."""
        import inspect

        clients = [
            JinaSearchClient(api_key="test"),
            SerpAPISearchClient(api_key="test"),
            TavilySearchClient(api_key="test"),
            ImageSearchClient(api_key="test"),
        ]

        with patch("duckduckgo_search.DDGS"):
            clients.append(DuckDuckGoSearchClient())

        for client in clients:
            assert inspect.iscoroutinefunction(client.forward_async)

    def test_all_forward_methods_are_sync(self):
        """Test that all forward methods are synchronous."""
        import inspect

        clients = [
            JinaSearchClient(api_key="test"),
            SerpAPISearchClient(api_key="test"),
            TavilySearchClient(api_key="test"),
        ]

        with patch("duckduckgo_search.DDGS"):
            clients.append(DuckDuckGoSearchClient())

        for client in clients:
            assert not inspect.iscoroutinefunction(client.forward)
