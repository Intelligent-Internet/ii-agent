"""Unit tests for resource limit features.

This module tests the resource limits implemented to prevent
resource exhaustion in browser and shell operations.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from typing import List


class TestBrowserTabLimit:
    """Tests for MAX_TABS limit in Browser.create_new_tab()."""

    @pytest.fixture
    def mock_context(self):
        """Create a mock browser context with configurable pages."""
        context = MagicMock()
        context.pages = []
        context.new_page = AsyncMock()
        return context

    def _create_mock_page(self, url: str = "about:blank"):
        """Create a mock page object."""
        page = MagicMock()
        page.url = url
        page.close = AsyncMock()
        page.wait_for_load_state = AsyncMock()
        page.goto = AsyncMock()
        page.bring_to_front = AsyncMock()
        return page

    @pytest.mark.asyncio
    async def test_creates_tab_when_under_limit(self, mock_context):
        """Test that tabs are created normally when under the limit."""
        from ii_tool.browser.browser import Browser, BrowserConfig

        browser = Browser(BrowserConfig())
        browser.context = mock_context
        browser.current_page = self._create_mock_page()

        # Start with 5 pages (under limit of 20)
        mock_context.pages = [self._create_mock_page(f"http://page{i}.com") for i in range(5)]

        new_page = self._create_mock_page("about:blank")
        mock_context.new_page.return_value = new_page

        await browser.create_new_tab("http://example.com")

        mock_context.new_page.assert_called_once()
        new_page.goto.assert_called_once_with("http://example.com", wait_until="domcontentloaded", timeout=30000)

    @pytest.mark.asyncio
    async def test_closes_oldest_tab_at_limit(self, mock_context):
        """Test that oldest tab is closed when at MAX_TABS limit."""
        from ii_tool.browser.browser import Browser, BrowserConfig

        browser = Browser(BrowserConfig())
        browser.context = mock_context

        # Create 20 pages (at limit)
        pages = [self._create_mock_page(f"http://page{i}.com") for i in range(20)]
        mock_context.pages = pages

        # Current page is NOT the oldest
        browser.current_page = pages[10]

        new_page = self._create_mock_page("about:blank")
        mock_context.new_page.return_value = new_page

        # Simulate page removal when close is called
        async def close_and_remove():
            mock_context.pages.remove(pages[0])
        pages[0].close = close_and_remove

        await browser.create_new_tab()

        # Oldest page (pages[0]) should have been closed
        # new_page should be created
        mock_context.new_page.assert_called_once()

    @pytest.mark.asyncio
    async def test_closes_second_oldest_when_current_is_oldest(self, mock_context):
        """Test that second oldest tab is closed when current page is oldest."""
        from ii_tool.browser.browser import Browser, BrowserConfig

        browser = Browser(BrowserConfig())
        browser.context = mock_context

        # Create 20 pages (at limit)
        pages = [self._create_mock_page(f"http://page{i}.com") for i in range(20)]
        mock_context.pages = pages

        # Current page IS the oldest
        browser.current_page = pages[0]

        new_page = self._create_mock_page("about:blank")
        mock_context.new_page.return_value = new_page

        # Simulate page removal when close is called on pages[1]
        async def close_and_remove():
            mock_context.pages.remove(pages[1])
        pages[1].close = close_and_remove

        await browser.create_new_tab()

        # Should still create new page
        mock_context.new_page.assert_called_once()

    @pytest.mark.asyncio
    async def test_initializes_browser_if_context_none(self, mock_context):
        """Test that browser is initialized if context is None."""
        from ii_tool.browser.browser import Browser, BrowserConfig

        browser = Browser(BrowserConfig())
        browser.context = None

        # Mock _init_browser to set up the context
        async def mock_init():
            browser.context = mock_context
            mock_context.pages = []
            new_page = self._create_mock_page()
            mock_context.new_page.return_value = new_page

        browser._init_browser = mock_init

        await browser.create_new_tab()

        mock_context.new_page.assert_called_once()

    def test_max_tabs_constant_value(self):
        """Test that MAX_TABS is set to expected value."""
        # Read the source to verify the constant (defined as class constant)
        import inspect
        from ii_tool.browser import browser

        source = inspect.getsource(browser.Browser)

        assert "MAX_TABS = 20" in source


class TestShellSessionLimit:
    """Tests for MAX_SHELL_SESSIONS limit in ShellInit."""

    @pytest.fixture
    def mock_shell_manager(self):
        """Create a mock shell manager."""
        manager = MagicMock()
        manager.get_all_sessions = MagicMock(return_value=[])
        manager.create_session = MagicMock()
        return manager

    @pytest.fixture
    def mock_workspace_manager(self):
        """Create a mock workspace manager."""
        from pathlib import Path

        manager = MagicMock()
        manager.get_workspace_path = MagicMock(return_value=Path("/workspace"))
        manager.validate_existing_directory_path = MagicMock()
        return manager

    @pytest.mark.asyncio
    async def test_creates_session_when_under_limit(
        self, mock_shell_manager, mock_workspace_manager
    ):
        """Test that sessions are created when under the limit."""
        from ii_tool.tools.shell.shell_init import ShellInit

        mock_shell_manager.get_all_sessions.return_value = ["session1", "session2"]

        tool = ShellInit(mock_shell_manager, mock_workspace_manager)

        result = await tool.execute({"session_name": "new_session"})

        assert not result.is_error
        assert "initialized successfully" in result.llm_content
        mock_shell_manager.create_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_rejects_session_at_limit(
        self, mock_shell_manager, mock_workspace_manager
    ):
        """Test that session creation is rejected at MAX_SHELL_SESSIONS limit."""
        from ii_tool.tools.shell.shell_init import ShellInit, MAX_SHELL_SESSIONS

        # Simulate being at the limit (10 sessions)
        existing_sessions = [f"session{i}" for i in range(MAX_SHELL_SESSIONS)]
        mock_shell_manager.get_all_sessions.return_value = existing_sessions

        tool = ShellInit(mock_shell_manager, mock_workspace_manager)

        result = await tool.execute({"session_name": "new_session"})

        assert result.is_error
        assert f"Maximum number of shell sessions ({MAX_SHELL_SESSIONS})" in result.llm_content
        assert "Please close existing sessions" in result.llm_content
        mock_shell_manager.create_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_error_message_includes_active_sessions(
        self, mock_shell_manager, mock_workspace_manager
    ):
        """Test that error message lists active sessions."""
        from ii_tool.tools.shell.shell_init import ShellInit, MAX_SHELL_SESSIONS

        existing_sessions = [f"worker{i}" for i in range(MAX_SHELL_SESSIONS)]
        mock_shell_manager.get_all_sessions.return_value = existing_sessions

        tool = ShellInit(mock_shell_manager, mock_workspace_manager)

        result = await tool.execute({"session_name": "another_session"})

        assert result.is_error
        assert "Active sessions:" in result.llm_content
        assert "worker0" in result.llm_content

    @pytest.mark.asyncio
    async def test_rejects_duplicate_session_name(
        self, mock_shell_manager, mock_workspace_manager
    ):
        """Test that duplicate session names are rejected."""
        from ii_tool.tools.shell.shell_init import ShellInit

        mock_shell_manager.get_all_sessions.return_value = ["existing_session"]

        tool = ShellInit(mock_shell_manager, mock_workspace_manager)

        result = await tool.execute({"session_name": "existing_session"})

        assert result.is_error
        assert "already exists" in result.llm_content
        mock_shell_manager.create_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_allows_session_at_one_below_limit(
        self, mock_shell_manager, mock_workspace_manager
    ):
        """Test that session creation works at limit-1."""
        from ii_tool.tools.shell.shell_init import ShellInit, MAX_SHELL_SESSIONS

        # 9 sessions (one below limit of 10)
        existing_sessions = [f"session{i}" for i in range(MAX_SHELL_SESSIONS - 1)]
        mock_shell_manager.get_all_sessions.return_value = existing_sessions

        tool = ShellInit(mock_shell_manager, mock_workspace_manager)

        result = await tool.execute({"session_name": "ninth_session"})

        assert not result.is_error
        mock_shell_manager.create_session.assert_called_once()

    def test_max_sessions_constant_value(self):
        """Test that MAX_SHELL_SESSIONS is set to expected value."""
        from ii_tool.tools.shell.shell_init import MAX_SHELL_SESSIONS

        assert MAX_SHELL_SESSIONS == 10


class TestResourceLimitIntegration:
    """Integration tests for resource limits."""

    def test_browser_and_shell_limits_are_documented(self):
        """Test that resource limits are properly documented in source code."""
        import inspect
        from ii_tool.browser import browser
        from ii_tool.tools.shell import shell_init

        # Browser should have MAX_TABS in the source
        browser_source = inspect.getsource(browser.Browser.create_new_tab)
        assert "MAX_TABS" in browser_source, "Browser tab limit should be defined"

        # Shell should have MAX_SHELL_SESSIONS defined
        assert hasattr(shell_init, 'MAX_SHELL_SESSIONS'), "Shell session limit should be defined"

        # Check that the comment about resource exhaustion exists
        shell_source = inspect.getsource(shell_init)
        assert "resource exhaustion" in shell_source.lower(), "Shell should document resource limit reason"

    def test_limits_are_reasonable_values(self):
        """Test that resource limits are reasonable for sandboxed environments."""
        from ii_tool.tools.shell.shell_init import MAX_SHELL_SESSIONS

        # Shell sessions: should be reasonable (not too many, not too few)
        assert 5 <= MAX_SHELL_SESSIONS <= 50, "Shell session limit should be between 5 and 50"

        # Browser tabs: read from source since it's a class constant
        import inspect
        from ii_tool.browser import browser

        source = inspect.getsource(browser.Browser)
        # Extract MAX_TABS value (defined as class constant)
        import re
        match = re.search(r'MAX_TABS\s*=\s*(\d+)', source)
        assert match, "MAX_TABS should be defined in Browser class"

        max_tabs = int(match.group(1))
        assert 10 <= max_tabs <= 100, "Browser tab limit should be between 10 and 100"
