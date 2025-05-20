import os

from typing import Optional
from google import genai
from ii_agent.tools.base import (
    LLMTool,
)
from ii_agent.utils import WorkspaceManager


DEFAULT_MODEL = "gemini-2.5-pro-preview-05-06"


class GeminiTool(LLMTool):
    def __init__(
        self, workspace_manager: WorkspaceManager, model: Optional[str] = None
    ):
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set.")
        if not model:
            model = DEFAULT_MODEL

        self.workspace_manager = workspace_manager
        self.model = model
        self.client = genai.Client(api_key=api_key)
