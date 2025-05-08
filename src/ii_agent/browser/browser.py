"""
Streamlined Playwright browser implementation.
"""

import time
import base64
import io
import logging
from dataclasses import dataclass, field
from importlib import resources
from typing import Any, Optional

from PIL import Image
from playwright.sync_api import (
    Browser as PlaywrightBrowser,
)
from playwright.sync_api import (
    BrowserContext as PlaywrightBrowserContext,
)
from playwright.sync_api import (
    Page,
    Playwright,
    StorageState,
    sync_playwright,
)
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from typing_extensions import TypedDict  # to account for older python versions

# Import detector class
from ii_agent.browser.detector import Detector
from ii_agent.browser.models import (
    BrowserError,
    BrowserState,
    InteractiveElementsData,
    TabInfo,
)
from ii_agent.browser.utils import (
    filter_elements,
    put_highlight_elements_on_screenshot,
    scale_b64_image,
)

logger = logging.getLogger(__name__)

INTERACTIVE_ELEMENTS_JS_CODE = resources.read_text(
    "src.ii_agent.browser", "findVisibleInteractiveElements.js"
)


class ViewportSize(TypedDict):
    width: int
    height: int


@dataclass
class BrowserConfig:
    """
    Simplified configuration for the Browser.

    Parameters:
            cdp_url: Optional[str] = None
                    Connect to a browser instance via CDP

            viewport_size: ViewportSize = {"width": 1024, "height": 768}
                    Default browser window size

            storage_state: Optional[StorageState] = None
                    Storage state to set

            detector: Optional[Detector] = None
                    Detector instance for CV element detection. If None, CV detection is disabled.

    """

    cdp_url: Optional[str] = None
    viewport_size: ViewportSize = field(
        default_factory=lambda: {"width": 1200, "height": 800}
    )
    storage_state: Optional[StorageState] = None
    detector: Optional[Detector] = None


class Browser:
    """
    Unified Browser responsible for interacting with the browser via Playwright.
    """

    def __init__(
        self, config: BrowserConfig = BrowserConfig(), close_context: bool = True
    ):
        logger.debug("Initializing browser")
        self.config = config
        self.close_context = close_context
        # Playwright-related attributes
        self.playwright: Optional[Playwright] = None
        self.playwright_browser: Optional[PlaywrightBrowser] = None
        self.context: Optional[PlaywrightBrowserContext] = None

        # Page and state management
        self.current_page: Optional[Page] = None
        self._state: Optional[BrowserState] = None
        self._cdp_session = None

        # CV detection-related attributes
        self.detector: Optional[Detector] = config.detector

        self.screenshot_scale_factor = None

        # Initialize state
        self._init_state()

    def __enter__(self):
        """Context manager entry"""
        self._init_browser()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        if self.close_context:
            self.close()

    def _init_state(self, url: str = "") -> None:
        """Initialize browser state"""
        self._state = BrowserState(
            url=url,
            screenshot_with_highlights=None,
            tabs=[],
            interactive_elements={},
        )

    def _init_browser(self):
        """Initialize the browser and context"""
        logger.debug("Initializing browser context")
        # Start playwright if needed
        if self.playwright is None:
            self.playwright = sync_playwright().start()

        # Initialize browser if needed
        if self.playwright_browser is None:
            if self.config.cdp_url:
                logger.info(
                    f"Connecting to remote browser via CDP {self.config.cdp_url}"
                )
                attempts = 0
                while True:
                    try:
                        self.playwright_browser = (
                            self.playwright.chromium.connect_over_cdp(
                                self.config.cdp_url,
                                timeout=2500,
                            )
                        )
                        break
                    except Exception as e:
                        logger.error(
                            f"Failed to connect to remote browser via CDP {self.config.cdp_url}: {e}. Retrying..."
                        )
                        time.sleep(1)
                        attempts += 1
                        if attempts > 3:
                            raise e
                logger.info(
                    f"Connected to remote browser via CDP {self.config.cdp_url}"
                )
            else:
                logger.info("Launching new browser instance")
                self.playwright_browser = self.playwright.chromium.launch(
                    headless=False,
                    args=[
                        "--no-sandbox",
                        "--disable-blink-features=AutomationControlled",
                        "--disable-web-security",
                        "--disable-site-isolation-trials",
                        "--disable-features=IsolateOrigins,site-per-process",
                        f"--window-size={self.config.viewport_size['width']},{self.config.viewport_size['height']}",
                    ],
                )

        # Create context if needed
        if self.context is None:
            if len(self.playwright_browser.contexts) > 0:
                self.context = self.playwright_browser.contexts[0]
            else:
                self.context = self.playwright_browser.new_context(
                    viewport=self.config.viewport_size,
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.102 Safari/537.36",
                    java_script_enabled=True,
                    bypass_csp=True,
                    ignore_https_errors=True,
                )

            # Apply anti-detection scripts
            self._apply_anti_detection_scripts()

        self.context.on("page", self._on_page_change)

        if self.config.storage_state and "cookies" in self.config.storage_state:
            self.context.add_cookies(self.config.storage_state["cookies"])

        # Create page if needed
        if self.current_page is None:
            if len(self.context.pages) > 0:
                self.current_page = self.context.pages[-1]
            else:
                self.current_page = self.context.new_page()

        return self

    def _on_page_change(self, page: Page):
        """Handle page change events"""
        logger.info(f"Current page changed to {page.url}")

        self._cdp_session = self.context.new_cdp_session(page)
        self.current_page = page

    def _apply_anti_detection_scripts(self):
        """Apply scripts to avoid detection as automation"""
        self.context.add_init_script(
            """
			// Webdriver property
			Object.defineProperty(navigator, 'webdriver', {
				get: () => undefined
			});

			// Languages
			Object.defineProperty(navigator, 'languages', {
				get: () => ['en-US']
			});

			// Plugins
			Object.defineProperty(navigator, 'plugins', {
				get: () => [1, 2, 3, 4, 5]
			});

			// Chrome runtime
			window.chrome = { runtime: {} };

			// Permissions
			const originalQuery = window.navigator.permissions.query;
			window.navigator.permissions.query = (parameters) => (
				parameters.name === 'notifications' ?
					Promise.resolve({ state: Notification.permission }) :
					originalQuery(parameters)
			);
			(function () {
				const originalAttachShadow = Element.prototype.attachShadow;
				Element.prototype.attachShadow = function attachShadow(options) {
					return originalAttachShadow.call(this, { ...options, mode: "open" });
				};
			})();
			"""
        )

    def close(self):
        """Close the browser instance and cleanup resources"""
        logger.debug("Closing browser")

        try:
            # Close CDP session if exists
            self._cdp_session = None

            # Close context
            if self.context:
                try:
                    self.context.close()
                except Exception as e:
                    logger.debug(f"Failed to close context: {e}")
                self.context = None

            # Close browser
            if self.playwright_browser:
                try:
                    self.playwright_browser.close()
                except Exception as e:
                    logger.debug(f"Failed to close browser: {e}")
                self.playwright_browser = None

            # Stop playwright
            if self.playwright:
                self.playwright.stop()
                self.playwright = None
        except Exception as e:
            logger.error(f"Error during browser cleanup: {e}")
        finally:
            self.context = None
            self.current_page = None
            self._state = None
            self.playwright_browser = None
            self.playwright = None

    def restart(self):
        """Restart the browser"""
        self.close()
        self._init_browser()

    def goto(self, url: str):
        """Navigate to a URL"""
        page = self.get_current_page()
        page.goto(url, wait_until="domcontentloaded")
        time.sleep(2)

    def get_tabs_info(self) -> list[TabInfo]:
        """Get information about all tabs"""

        tabs_info = []
        for page_id, page in enumerate(self.context.pages):
            tab_info = TabInfo(page_id=page_id, url=page.url, title=page.title())
            tabs_info.append(tab_info)

        return tabs_info

    def switch_to_tab(self, page_id: int) -> None:
        """Switch to a specific tab by its page_id"""
        if self.context is None:
            self._init_browser()

        pages = self.context.pages
        if page_id >= len(pages):
            raise BrowserError(f"No tab found with page_id: {page_id}")

        page = pages[page_id]
        self.current_page = page

        page.bring_to_front()
        page.wait_for_load_state()

    def create_new_tab(self, url: str | None = None) -> None:
        """Create a new tab and optionally navigate to a URL"""
        if self.context is None:
            self._init_browser()

        new_page = self.context.new_page()
        self.current_page = new_page

        new_page.wait_for_load_state()

        if url:
            new_page.goto(url, wait_until="domcontentloaded")

    def close_current_tab(self):
        """Close the current tab"""
        if self.current_page is None:
            return

        self.current_page.close()

        # Switch to the first available tab if any exist
        if self.context and self.context.pages:
            self.switch_to_tab(0)

    def get_current_page(self) -> Page:
        """Get the current page"""
        if self.current_page is None:
            self._init_browser()
        return self.current_page

    def get_state(self) -> BrowserState:
        """Get the current browser state"""
        return self._state

    def update_state(self) -> BrowserState:
        """Update the browser state with current page information and return it"""
        self._state = self._update_state()
        return self._state

    def _update_state(self) -> BrowserState:
        """Update and return state."""

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=2),
            retry=retry_if_exception_type((Exception)),
            reraise=True,
        )
        def get_stable_state():
            if self.current_page is None:
                self._init_browser()
            url = self.current_page.url

            detect_sheets = "docs.google.com/spreadsheets/d" in url

            screenshot_b64 = self.fast_screenshot()

            interactive_elements_data = self.get_interactive_elements(
                screenshot_b64, detect_sheets
            )
            interactive_elements = {
                element.index: element for element in interactive_elements_data.elements
            }

            # Create highlighted version of the screenshot
            screenshot_with_highlights = put_highlight_elements_on_screenshot(
                interactive_elements, screenshot_b64
            )

            tabs = self.get_tabs_info()

            return BrowserState(
                url=url,
                tabs=tabs,
                screenshot_with_highlights=screenshot_with_highlights,
                screenshot=screenshot_b64,
                viewport=interactive_elements_data.viewport,
                interactive_elements=interactive_elements,
            )

        try:
            self._state = get_stable_state()
            return self._state
        except Exception as e:
            logger.error(f"Failed to update state after multiple attempts: {str(e)}")
            # Return last known good state if available
            if hasattr(self, "_state"):
                return self._state
            raise

    def detect_browser_elements(self) -> InteractiveElementsData:
        """Get all interactive elements on the page"""
        page = self.get_current_page()
        result = page.evaluate(INTERACTIVE_ELEMENTS_JS_CODE)
        interactive_elements_data = InteractiveElementsData(**result)

        return interactive_elements_data

    def get_interactive_elements(
        self, screenshot_b64: str, detect_sheets: bool = False
    ) -> InteractiveElementsData:
        """
        Get interactive elements using combined browser and CV detection.

        Args:
                screenshot_b64: Optional base64 encoded screenshot. If None, a new screenshot will be taken.
                detect_sheets: Whether to detect sheets elements
        Returns:
                Combined detection results
        """

        elements = []

        if self.detector is not None:
            browser_elements_data = self.detect_browser_elements()

            scale_factor = browser_elements_data.viewport.width / 1024

            cv_elements = self.detector.detect_from_image(
                screenshot_b64, scale_factor, detect_sheets
            )

            # Combine and filter detections
            elements = filter_elements(browser_elements_data.elements + cv_elements)
        else:
            browser_elements_data = self.detect_browser_elements()
            elements = browser_elements_data.elements

        # Create new InteractiveElementsData with combined elements
        return InteractiveElementsData(
            viewport=browser_elements_data.viewport, elements=elements
        )

    def get_cdp_session(self):
        """Get or create a CDP session for the current page"""

        # Create a new session if we don't have one or the page has changed
        if (
            self._cdp_session is None
            or not hasattr(self._cdp_session, "_page")
            or self._cdp_session._page != self.current_page
        ):
            self._cdp_session = self.context.new_cdp_session(self.current_page)
            # Store reference to the page this session belongs to
            self._cdp_session._page = self.current_page

        return self._cdp_session

    def fast_screenshot(self) -> str:
        """
        Returns a base64 encoded screenshot of the current page.

        Returns:
                Base64 encoded screenshot
        """
        # Use cached CDP session instead of creating a new one each time
        cdp_session = self.get_cdp_session()
        screenshot_params = {
            "format": "png",
            "fromSurface": False,
            "captureBeyondViewport": False,
        }

        # Capture screenshot using CDP Session
        screenshot_data = cdp_session.send("Page.captureScreenshot", screenshot_params)
        screenshot_b64 = screenshot_data["data"]

        if self.screenshot_scale_factor is None:
            test_img_data = base64.b64decode(screenshot_b64)
            test_img = Image.open(io.BytesIO(test_img_data))
            logger.info(f"Test image size: {test_img.size}")
            self.screenshot_scale_factor = 1024 / test_img.size[0]
            logger.info(f"Screenshot scale factor: {self.screenshot_scale_factor}")

        screenshot_b64 = scale_b64_image(screenshot_b64, self.screenshot_scale_factor)
        return screenshot_b64

    def get_cookies(self) -> list[dict[str, Any]]:
        """Get cookies from the browser"""
        if self.context:
            cookies = self.context.cookies()
            return cookies
        return []

    def get_storage_state(self) -> dict[str, Any]:
        """Get local storage from the browser"""

        if self.context:
            cookies = self.context.cookies()

            return {
                "cookies": cookies,
            }
        return {}
