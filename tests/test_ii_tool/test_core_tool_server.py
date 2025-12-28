"""Unit tests for ii_tool.core.tool_server module.

This module tests the ToolServerURLSingleton pattern:
- Thread-safe singleton behavior
- URL get/set operations
- Error handling for unconfigured state
"""

import pytest
from threading import Thread
from concurrent.futures import ThreadPoolExecutor
import time

from ii_tool.core.tool_server import (
    ToolServerURLSingleton,
    get_tool_server_url,
    set_tool_server_url,
)


class TestToolServerURLSingleton:
    """Tests for ToolServerURLSingleton class."""

    def setup_method(self):
        """Reset singleton state before each test."""
        # Access the singleton and reset its URL
        singleton = ToolServerURLSingleton()
        singleton._state.url = None

    def test_singleton_returns_same_instance(self):
        """Multiple calls to ToolServerURLSingleton() return same instance."""
        instance1 = ToolServerURLSingleton()
        instance2 = ToolServerURLSingleton()
        assert instance1 is instance2

    def test_set_url(self):
        """set_url stores the URL in singleton state."""
        singleton = ToolServerURLSingleton()
        singleton.set_url("http://localhost:8000")
        assert singleton._state.url == "http://localhost:8000"

    def test_get_url_success(self):
        """get_url returns stored URL when configured."""
        singleton = ToolServerURLSingleton()
        singleton.set_url("http://localhost:9000")
        assert singleton.get_url() == "http://localhost:9000"

    def test_get_url_raises_when_not_configured(self):
        """get_url raises RuntimeError when URL not set."""
        singleton = ToolServerURLSingleton()
        singleton._state.url = None
        with pytest.raises(RuntimeError, match="Tool server URL is not configured"):
            singleton.get_url()

    def test_url_can_be_updated(self):
        """URL can be changed after initial set."""
        singleton = ToolServerURLSingleton()
        singleton.set_url("http://first:8000")
        assert singleton.get_url() == "http://first:8000"
        
        singleton.set_url("http://second:9000")
        assert singleton.get_url() == "http://second:9000"


class TestModuleFunctions:
    """Tests for module-level convenience functions."""

    def setup_method(self):
        """Reset singleton state before each test."""
        singleton = ToolServerURLSingleton()
        singleton._state.url = None

    def test_set_tool_server_url_function(self):
        """set_tool_server_url convenience function works."""
        set_tool_server_url("http://test:8080")
        assert get_tool_server_url() == "http://test:8080"

    def test_get_tool_server_url_function(self):
        """get_tool_server_url convenience function works."""
        set_tool_server_url("http://api:3000")
        url = get_tool_server_url()
        assert url == "http://api:3000"

    def test_get_raises_without_set(self):
        """get_tool_server_url raises when not configured."""
        with pytest.raises(RuntimeError):
            get_tool_server_url()


class TestThreadSafety:
    """Tests for thread-safety of the singleton."""

    def setup_method(self):
        """Reset singleton state before each test."""
        singleton = ToolServerURLSingleton()
        singleton._state.url = None

    def test_concurrent_singleton_access(self):
        """Multiple threads get the same singleton instance."""
        instances = []
        
        def get_instance():
            instances.append(ToolServerURLSingleton())
        
        threads = [Thread(target=get_instance) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # All instances should be the same object
        assert len(set(id(i) for i in instances)) == 1

    def test_concurrent_url_set(self):
        """Concurrent URL sets don't cause race conditions."""
        results = []
        
        def set_and_get(url: str):
            set_tool_server_url(url)
            # Small delay to increase chance of race condition
            time.sleep(0.001)
            results.append(get_tool_server_url())
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            urls = [f"http://server{i}:8000" for i in range(5)]
            executor.map(set_and_get, urls)
        
        # All results should be valid URLs (one of the set values)
        for result in results:
            assert result.startswith("http://server")
            assert ":8000" in result


class TestURLFormats:
    """Tests for various URL format handling."""

    def setup_method(self):
        """Reset singleton state before each test."""
        singleton = ToolServerURLSingleton()
        singleton._state.url = None

    def test_http_url(self):
        """Standard HTTP URL is accepted."""
        set_tool_server_url("http://localhost:8000")
        assert get_tool_server_url() == "http://localhost:8000"

    def test_https_url(self):
        """HTTPS URL is accepted."""
        set_tool_server_url("https://secure.example.com:443")
        assert get_tool_server_url() == "https://secure.example.com:443"

    def test_url_with_path(self):
        """URL with path component is accepted."""
        set_tool_server_url("http://localhost:8000/api/v1")
        assert get_tool_server_url() == "http://localhost:8000/api/v1"

    def test_localhost_variations(self):
        """Various localhost formats are accepted."""
        for url in ["http://localhost:8000", "http://127.0.0.1:8000", "http://0.0.0.0:8000"]:
            set_tool_server_url(url)
            assert get_tool_server_url() == url

    def test_empty_string_url(self):
        """Empty string URL is stored (validation is caller's responsibility)."""
        set_tool_server_url("")
        # Empty string is falsy, so get_url should raise
        with pytest.raises(RuntimeError):
            get_tool_server_url()
