"""Minimal FastAPI app exposing Scribe HTTP endpoints."""

from fastapi import FastAPI

from scribe_core.provider_router import ProviderRouter

app = FastAPI(title="Scribe API")

# Instantiate router eagerly so the runtime banner is printed during startup.
router = ProviderRouter.lazy_default()

_DEFAULT_MODELS = [
    "claude-3.7-sonnet",
    "claude-3-haiku",
    "gpt-4.1-mini",
]


@app.get("/api/models")
def list_models() -> dict[str, list[str]]:
    """Return the currently exposed model identifiers."""

    # Future iterations will hydrate from config/models.yml.
    _ = router  # placate linters until the router is used for dispatch.
    return {"models": _DEFAULT_MODELS}
