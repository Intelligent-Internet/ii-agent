import os
import openai
from typing import Optional, Any, Dict
from google import genai
from ii_agent.tools.base import LLMTool
from ii_agent.utils import WorkspaceManager
from ii_agent.llm.openrouter import map_model_name_to_openrouter


DEFAULT_MODEL = "gemini-2.5-pro-preview-05-06"


class GeminiTool(LLMTool):
    def __init__(
        self, workspace_manager: WorkspaceManager, model: Optional[str] = None
    ):
        self.workspace_manager = workspace_manager
        
        if not model:
            model = DEFAULT_MODEL
        self.model = model
        
        # Check if OpenRouter API key is available
        openrouter_api_key = os.environ.get("OPENROUTER_API_KEY")
        
        if openrouter_api_key:
            # Use OpenRouter for Gemini models
            self.use_openrouter = True
            self.client = openai.OpenAI(
                api_key=openrouter_api_key,
                base_url="https://openrouter.ai/api/v1",
            )
            # Map model name to OpenRouter format
            self.openrouter_model = map_model_name_to_openrouter(model)
            print(f"====== Using OpenRouter for Gemini tool with model: {self.openrouter_model} ======")
        else:
            # Use direct Gemini API
            self.use_openrouter = False
            gemini_api_key = os.environ.get("GEMINI_API_KEY", "")
            if not gemini_api_key:
                raise ValueError(
                    "Either OPENROUTER_API_KEY or GEMINI_API_KEY environment variable must be set."
                )
            self.client = genai.Client(api_key=gemini_api_key)
    
    def _generate_with_openrouter(self, prompt: str, **kwargs) -> str:
        """Generate text using OpenRouter API."""
        try:
            response = self.client.chat.completions.create(
                model=self.openrouter_model,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                max_tokens=kwargs.get("max_tokens", 4000),
                temperature=kwargs.get("temperature", 0.0),
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            print(f"OpenRouter API error: {e}")
            raise e
    
    def _generate_with_gemini_direct(self, prompt: str, **kwargs) -> str:
        """Generate text using direct Gemini API."""
        try:
            from google.genai import types
            response = self.client.models.generate_content(
                model=self.model,
                contents=types.Content(
                    parts=[types.Part(text=prompt)]
                ),
            )
            return response.text
        except Exception as e:
            print(f"Gemini API error: {e}")
            raise e
    
    def generate_text(self, prompt: str, **kwargs) -> str:
        """Generate text using either OpenRouter or direct Gemini API."""
        if self.use_openrouter:
            return self._generate_with_openrouter(prompt, **kwargs)
        else:
            return self._generate_with_gemini_direct(prompt, **kwargs)
