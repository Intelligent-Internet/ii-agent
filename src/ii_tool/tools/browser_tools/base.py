import asyncio

from typing import Any, Optional

from ii_agent.browser.browser import Browser
from ii_agent.controller.state import State
from typing import Any
from ii_tool.core.config import ImageSearchConfig
from ii_tool.tools.base import BaseTool, ToolResult
from ii_tool.tools.web.clients.image_search_client import create_image_search_client





def get_event_loop():
    try:
        # Try to get the existing event loop
        loop = asyncio.get_event_loop()
    except RuntimeError:
        # If no event loop exists, create a new one
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop

# Name
NAME = "BashInit"
DISPLAY_NAME = "Initialize bash session"

# Tool description
DESCRIPTION = "Initialize a bash session with a given name and start directory. Use this before running any commands in the session."

# Input schema
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "session_name": {
            "type": "string",
            "description": "The name of the session to initialize."
        },
        "start_directory": {
            "type": "string",
            "description": "The absolute path to a directory to start the session in. If not provided, the session will start in the workspace directory."
        }
    },
    "required": ["session_name"]
}

class BrowserTool(BaseTool):
    name = 'BrowserTool'
    display_name = 'BrowserTool'
    description = None
    input_schema = None
    read_only = False
    def __init__(self, browser: Browser):
        self.browser = browser

