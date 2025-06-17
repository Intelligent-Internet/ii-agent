import os

from typing import Optional
from openai import OpenAI
from ii_agent.tools.base import (
    LLMTool,
)
from ii_agent.utils import WorkspaceManager


DEFAULT_MODEL = "google/gemini-2.0-flash-exp"


class GeminiTool(LLMTool):
    def __init__(
        self, workspace_manager: WorkspaceManager, model: Optional[str] = None, site_url: str = None, site_name: str = None
    ):
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set.")
        if not model:
            model = DEFAULT_MODEL

        self.workspace_manager = workspace_manager
        self.model = model
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
        
        # Optional headers for OpenRouter rankings
        self.extra_headers = {}
        if site_url:
            self.extra_headers["HTTP-Referer"] = site_url
        if site_name:
            self.extra_headers["X-Title"] = site_name


