"""Tests for browser tab limit enforcement."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from ii_tool.browser.browser import Browser, BrowserConfig


@pytest.mark.asyncio
async def test_max_tabs_constant_exists():
    """Test that MAX_TABS and TAB_OPERATION_TIMEOUT constants are defined."""
    browser = Browser(BrowserConfig())
    assert hasattr(browser, 'MAX_TABS')
    assert browser.MAX_TABS == 20
    assert hasattr(browser, 'TAB_OPERATION_TIMEOUT')
    assert browser.TAB_OPERATION_TIMEOUT == 10000


@pytest.mark.asyncio
async def test_create_new_tab_enforces_limit():
    """Test that create_new_tab enforces MAX_TABS limit."""
    browser = Browser(BrowserConfig())

    # Mock the context and pages
    mock_context = AsyncMock()
    mock_context.new_page = AsyncMock()
    browser.context = mock_context

    # Create mock pages (simulate 20 existing tabs)
    mock_pages = []
    for i in range(20):
        mock_page = MagicMock()
        mock_page.url = f"https://example.com/page{i}"
        mock_pages.append(mock_page)

    mock_context.pages = mock_pages

    # Mock the current page as the oldest (index 0)
    # In this case, _enforce_tab_limit should close the second oldest (index 1)
    browser.current_page = mock_pages[0]

    # Mock _force_close_page to track calls
    close_calls = []
    async def mock_force_close(page):
        close_calls.append(page)
        mock_context.pages.remove(page)
        return True

    browser._force_close_page = mock_force_close

    # Mock new page creation
    new_mock_page = MagicMock()
    new_mock_page.wait_for_load_state = AsyncMock()
    new_mock_page.goto = AsyncMock()
    mock_context.new_page.return_value = new_mock_page

    # Create a new tab - should trigger cleanup
    await browser.create_new_tab("https://newpage.com")

    # Verify that a tab was closed
    # Since current_page is the oldest (index 0), it should close second oldest (index 1)
    assert len(close_calls) > 0
    assert close_calls[0].url == "https://example.com/page1"


@pytest.mark.asyncio
async def test_enforce_tab_limit_method():
    """Test the _enforce_tab_limit method directly."""
    browser = Browser(BrowserConfig())

    # Mock the context and pages
    mock_context = AsyncMock()
    browser.context = mock_context

    # Create mock pages exceeding limit
    mock_pages = []
    for i in range(25):  # Exceeds MAX_TABS of 20
        mock_page = MagicMock()
        mock_page.url = f"https://example.com/page{i}"
        mock_pages.append(mock_page)

    mock_context.pages = mock_pages
    browser.current_page = mock_pages[10]  # Not the oldest

    # Mock _force_close_page
    close_calls = []
    async def mock_force_close(page):
        close_calls.append(page)
        mock_context.pages.remove(page)
        return True

    browser._force_close_page = mock_force_close

    # Call enforce_tab_limit
    await browser._enforce_tab_limit()

    # Should have closed tabs until we're under limit
    # With max_cleanup_attempts=3, it will do at most 3 cleanup iterations
    # Each iteration closes one tab if pages >= MAX_TABS
    assert len(close_calls) == 3  # Should close exactly 3 tabs (limited by max_cleanup_attempts)
    # Should have closed oldest tabs first (skipping current page at index 10)
    assert close_calls[0].url == "https://example.com/page0"


@pytest.mark.asyncio
async def test_init_browser_respects_limit():
    """Test that _init_browser enforces tab limit when creating initial page."""
    browser = Browser(BrowserConfig())

    with patch('ii_tool.browser.browser.async_playwright') as mock_playwright:
        # Setup mocks
        mock_pw_context = AsyncMock()
        mock_pw = AsyncMock()
        mock_playwright.return_value = mock_pw_context
        mock_pw_context.__aenter__.return_value = mock_pw

        mock_browser = AsyncMock()
        mock_pw.chromium.launch.return_value = mock_browser

        mock_context = AsyncMock()
        mock_browser.new_context.return_value = mock_context
        mock_browser.contexts = []

        # Simulate 20 existing pages (at limit)
        mock_pages = []
        for i in range(20):
            mock_page = MagicMock()
            mock_page.url = f"https://example.com/page{i}"
            mock_pages.append(mock_page)

        mock_context.pages = mock_pages
        mock_context.on = MagicMock()
        mock_context.add_cookies = AsyncMock()

        # Track enforcement calls
        enforce_called = []
        original_enforce = browser._enforce_tab_limit
        async def mock_enforce():
            enforce_called.append(True)
            await original_enforce()

        browser._enforce_tab_limit = mock_enforce

        # Mock _force_close_page to actually remove pages
        async def mock_force_close(page):
            if page in mock_context.pages:
                mock_context.pages.remove(page)
            return True

        browser._force_close_page = mock_force_close

        # Mock other required methods
        browser._apply_anti_detection_scripts = AsyncMock()
        browser._on_page_change = AsyncMock()

        # Initialize browser - should call enforce if creating new page
        mock_new_page = MagicMock()
        mock_new_page.wait_for_load_state = AsyncMock()
        mock_context.new_page.return_value = mock_new_page

        await browser._init_browser()

        # Verify that _enforce_tab_limit was called
        assert len(enforce_called) > 0


@pytest.mark.asyncio
async def test_close_stuck_tab_handling():
    """Test that _enforce_tab_limit handles stuck tabs that won't close."""
    browser = Browser(BrowserConfig())

    # Mock the context and pages
    mock_context = AsyncMock()
    browser.context = mock_context

    # Create 21 mock pages (over limit)
    mock_pages = []
    for i in range(21):
        mock_page = MagicMock()
        mock_page.url = f"https://example.com/page{i}"
        mock_pages.append(mock_page)

    mock_context.pages = mock_pages
    browser.current_page = mock_pages[10]  # Not the oldest

    # Mock _force_close_page - first call fails, second succeeds
    close_attempts = []
    async def mock_force_close(page):
        close_attempts.append(page)
        if len(close_attempts) == 1:
            # First call fails (stuck tab)
            return False
        else:
            # Second call succeeds
            mock_context.pages.remove(page)
            return True

    browser._force_close_page = mock_force_close

    # Call enforce_tab_limit
    await browser._enforce_tab_limit()

    # Should have tried to close two tabs (first failed, second succeeded)
    assert len(close_attempts) == 2
    assert close_attempts[0].url == "https://example.com/page0"
    assert close_attempts[1].url == "https://example.com/page1"


@pytest.mark.asyncio
async def test_max_cleanup_attempts_limit():
    """Test that cleanup stops after max_cleanup_attempts to prevent infinite loops."""
    browser = Browser(BrowserConfig())

    # Mock the context and pages
    mock_context = AsyncMock()
    browser.context = mock_context

    # Create 25 mock pages (well over limit)
    mock_pages = []
    for i in range(25):
        mock_page = MagicMock()
        mock_page.url = f"https://example.com/page{i}"
        mock_pages.append(mock_page)

    mock_context.pages = mock_pages
    browser.current_page = mock_pages[10]

    # Mock _force_close_page to successfully close tabs
    close_calls = []
    async def mock_force_close(page):
        close_calls.append(page)
        mock_context.pages.remove(page)
        return True

    browser._force_close_page = mock_force_close

    # Call enforce_tab_limit
    await browser._enforce_tab_limit()

    # Should stop after max_cleanup_attempts (3), not close all 5 excess tabs
    assert len(close_calls) == 3
