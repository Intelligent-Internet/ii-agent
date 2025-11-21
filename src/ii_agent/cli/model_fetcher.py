"""Dynamic model fetching and caching for REPL tab completion."""
import os
import json
import time
from pathlib import Path
from typing import Dict, List, Optional
import httpx
from ii_agent.core.logger import logger


class ModelCache:
    """Cache for dynamically fetched models."""

    CACHE_TTL = 3600  # 1 hour cache

    def __init__(self):
        self.cache_dir = Path.home() / ".ii_agent" / "model_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory_cache: Dict[str, Dict] = {}

    def get_cache_file(self, provider: str) -> Path:
        """Get cache file path for provider."""
        return self.cache_dir / f"{provider}_models.json"

    def is_cache_valid(self, provider: str) -> bool:
        """Check if cache is still valid."""
        cache_file = self.get_cache_file(provider)
        if not cache_file.exists():
            return False

        # Check memory cache first
        if provider in self._memory_cache:
            cached_time = self._memory_cache[provider].get("cached_at", 0)
            if time.time() - cached_time < self.CACHE_TTL:
                return True

        # Check file cache
        try:
            with open(cache_file, 'r') as f:
                data = json.load(f)
                cached_time = data.get("cached_at", 0)
                if time.time() - cached_time < self.CACHE_TTL:
                    self._memory_cache[provider] = data
                    return True
        except Exception:
            pass

        return False

    def get_cached_models(self, provider: str) -> Optional[List[str]]:
        """Get cached models for provider."""
        if provider in self._memory_cache:
            return self._memory_cache[provider].get("models")

        cache_file = self.get_cache_file(provider)
        if cache_file.exists():
            try:
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                    self._memory_cache[provider] = data
                    return data.get("models")
            except Exception:
                pass

        return None

    def save_models(self, provider: str, models: List[str]):
        """Save models to cache."""
        data = {
            "cached_at": time.time(),
            "models": models
        }

        self._memory_cache[provider] = data

        cache_file = self.get_cache_file(provider)
        try:
            with open(cache_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.debug(f"Failed to write model cache for {provider}: {e}")


class ModelFetcher:
    """Fetch and cache models from various providers."""

    def __init__(self):
        self.cache = ModelCache()
        self._fetchers = {
            "nvidia": self._fetch_nvidia_models,
            "openai": self._fetch_openai_models,
            "anthropic": self._fetch_anthropic_models,
            "gemini": self._fetch_gemini_models,
        }

    def get_models(self, provider: str, force_refresh: bool = False) -> List[str]:
        """Get models for provider, fetching if necessary."""
        # Check cache first
        if not force_refresh and self.cache.is_cache_valid(provider):
            cached = self.cache.get_cached_models(provider)
            if cached:
                return cached

        # Fetch from provider
        fetcher = self._fetchers.get(provider)
        if not fetcher:
            logger.debug(f"No fetcher for provider: {provider}")
            return []

        try:
            models = fetcher()
            self.cache.save_models(provider, models)
            return models
        except Exception as e:
            logger.debug(f"Failed to fetch models for {provider}: {e}")
            # Fall back to cache even if stale
            cached = self.cache.get_cached_models(provider)
            return cached if cached else []

    def _fetch_nvidia_models(self) -> List[str]:
        """Fetch models from NVIDIA API."""
        api_key = os.getenv("NVIDIA_API_KEY")
        if not api_key:
            return []

        url = "https://integrate.api.nvidia.com/v1/models"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json"
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()

                # Extract model IDs in the format: provider/model-name
                models = []
                for model in data.get("data", []):
                    model_id = model.get("id", "")
                    if model_id:
                        models.append(model_id)

                return sorted(models)
        except Exception as e:
            logger.debug(f"Error fetching NVIDIA models: {e}")
            return []

    def _fetch_openai_models(self) -> List[str]:
        """Fetch models from OpenAI API."""
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return []

        url = "https://api.openai.com/v1/models"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json"
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()

                # Extract model IDs
                models = []
                for model in data.get("data", []):
                    model_id = model.get("id", "")
                    if model_id and ("gpt" in model_id or "o1" in model_id or "o3" in model_id):
                        models.append(model_id)

                return sorted(models)
        except Exception as e:
            logger.debug(f"Error fetching OpenAI models: {e}")
            return []

    def _fetch_anthropic_models(self) -> List[str]:
        """Return known Anthropic models (no public list endpoint)."""
        return [
            "claude-sonnet-4-20250514",
            "claude-opus-4-20250514",
            "claude-sonnet-3-5-20241022",
            "claude-sonnet-3-5-20240620",
            "claude-3-5-haiku-20241022",
            "claude-opus-3-20240229",
            "claude-3-haiku-20240307",
        ]

    def _fetch_gemini_models(self) -> List[str]:
        """Return known Gemini models."""
        return [
            "gemini/gemini-2.0-flash-exp",
            "gemini/gemini-2.0-flash-thinking-exp-01-21",
            "gemini/gemini-exp-1206",
            "gemini/gemini-1.5-pro",
            "gemini/gemini-1.5-pro-002",
            "gemini/gemini-1.5-flash",
            "gemini/gemini-1.5-flash-002",
            "gemini/gemini-1.5-flash-8b",
        ]


# Singleton instance
_model_fetcher: Optional[ModelFetcher] = None


def get_model_fetcher() -> ModelFetcher:
    """Get or create singleton model fetcher."""
    global _model_fetcher
    if _model_fetcher is None:
        _model_fetcher = ModelFetcher()
    return _model_fetcher
