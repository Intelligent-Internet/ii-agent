import json
from utils.common import (
    DialogMessages,
    LLMTool,
    ToolImplOutput,
)
import os
import time
import random
from PIL import Image
from io import BytesIO
from base64 import b64decode
from playwright.sync_api import sync_playwright
from asyncio import Queue
from typing import Any, Optional
from pydantic import BaseModel
from typing import Any, Optional


def save_base64_image_png(base64_str: str, path: str) -> None:
    """
    Saves a base64-encoded image to a PNG file.

    Args:
        base64_str (str): Base64-encoded image string.
        path (str): Destination file path (should end with .png).
    """
    # Strip off any data URL prefix
    if ',' in base64_str:
        base64_str = base64_str.split(',')[1]

    image_data = b64decode(base64_str)
    image = Image.open(BytesIO(image_data)).convert("RGBA")
    image.save(path, format="PNG")


class RealtimeEvent(BaseModel):
    type: str
    raw_message: dict[str, Any]


class FakeBrowserUse:
    def __init__(self, url: str, message_queue: Queue | None = None):
        # self._init_browser()
        self.url = url
        self.message_queue = message_queue
        self._cdp_session = None
        self.playwright = sync_playwright().start()
        self.playwright_browser = self.playwright.chromium.launch(
                headless=False,
                channel="chrome",
                args=[
                    '--no-sandbox',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-web-security',
                    '--disable-site-isolation-trials',
                    '--disable-features=IsolateOrigins,site-per-process',
                ]
            )
        self.context = self.playwright_browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.102 Safari/537.36',
                java_script_enabled=True,
                bypass_csp=True,
                ignore_https_errors=True,
            )

        self.is_pdf = self._is_pdf_url(self.url)
        self.current_page = self.context.new_page()
        self.current_page.goto(self.url, wait_until="domcontentloaded")

    def get_cdp_session(self):
        # Create a new session if we don't have one or the page has changed
        if (self._cdp_session is None or 
            not hasattr(self._cdp_session, '_page') or 
            self._cdp_session._page != self.current_page):
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
            "captureBeyondViewport": False
        }

        # Capture screenshot using CDP Session
        screenshot_data = cdp_session.send("Page.captureScreenshot", screenshot_params)
        screenshot_b64 = screenshot_data["data"]

        return screenshot_b64

    def forward(self):
        if self.is_pdf:
            time.sleep(5)
            self.current_page.keyboard.press("Control+\\")
            num_down_scrolls = random.randint(5, 8)
            delay = 3
        else:   
            num_down_scrolls = random.randint(3, 6)
            delay = 3

        for i in range(num_down_scrolls):
            time.sleep(delay)
            screenshot = self.fast_screenshot()
            if self.message_queue:
                self.message_queue.put_nowait(
                    RealtimeEvent(
                        type="browser_use",
                        raw_message={
                            "url": self.url,
                            "screenshot": screenshot,
                        }
                    )
                )
            self.current_page.keyboard.press("PageDown")

        time.sleep(delay)

        self.current_page.close()

    def _is_pdf_url(self, url: str, timeout: float = 5.0) -> bool:
        import requests
        import urllib
        """
        Checks if a given URL points to a PDF file.

        Args:
            url (str): The URL to check.
            timeout (float): Timeout for HTTP requests.

        Returns:
            bool: True if the URL points to a PDF, False otherwise.
        """
        try:
            # Quick extension check
            parsed = urllib.parse.urlparse(url)
            if parsed.path.lower().endswith(".pdf"):
                return True

            # Try HEAD request to get Content-Type
            head = requests.head(url, allow_redirects=True, timeout=timeout)
            content_type = head.headers.get("Content-Type", "").lower()
            if "application/pdf" in content_type:
                return True

            # Fallback: Try a minimal GET request
            get = requests.get(url, stream=True, timeout=timeout)
            content_type = get.headers.get("Content-Type", "").lower()
            return "application/pdf" in content_type

        except requests.RequestException as e:
            # Log or handle as needed in real prod code
            return False
        

class TavilyVisitWebpageTool(LLMTool):
    name = "tavily_visit_webpage"
    description = (
        "Visits a webpage at the given url and extracts its content using Tavily API. Returns webpage content as text."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The url of the webpage to visit.",
            }
        },
        "required": ["url"],
    }
    output_type = "string"

    def __init__(self, max_output_length: int = 40000, message_queue: Queue | None = None):
        self.max_output_length = max_output_length
        self.api_key = os.environ.get("TAVILY_API_KEY", "")
        if not self.api_key:
            print("Warning: TAVILY_API_KEY environment variable not set. Tool may not function correctly.")
        self.message_queue = message_queue

    def forward(self, url: str) -> str:
        try:
            from tavily import TavilyClient
            from .utils import truncate_content
        except ImportError as e:
            raise ImportError(
                "You must install package `tavily` to run this tool: for instance run `pip install tavily`."
            ) from e

        browser_use = FakeBrowserUse(url, self.message_queue)
        browser_use.forward()
        
        try:
            # Initialize Tavily client
            tavily_client = TavilyClient(api_key=self.api_key)
            
            # Extract webpage content
            response = tavily_client.extract(url)
            
            # Check if response contains results
            if not response or 'results' not in response or not response['results']:
                return f"No content could be extracted from {url}"
            
            # Extract the content from the first result
            content = json.dumps(response['results'][0], indent=4)
            if not content:
                return f"No textual content could be extracted from {url}"
            
            return truncate_content(content, self.max_output_length)

        except Exception as e:
            return f"Error extracting the webpage content using Tavily: {str(e)}"

    def run_impl(
        self,
        tool_input: dict[str, Any],
        dialog_messages: Optional[DialogMessages] = None,
    ) -> ToolImplOutput:
        url = tool_input["url"]
        output = self.forward(url)
        return ToolImplOutput(
            output,
            f"Webpage {url} successfully visited using Tavily",
            auxiliary_data={"success": True},
        ) 