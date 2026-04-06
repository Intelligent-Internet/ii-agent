"""Router registration for the main application."""

from __future__ import annotations

from fastapi import APIRouter, FastAPI

from .health import health_router


def include_routers(app: FastAPI) -> None:
    """Attach all HTTP routers to the application."""
    # Import concrete router objects to avoid package/submodule name collisions.
    from ii_agent.auth.router import router as auth_router
    from ii_agent.users.router import router as users_router
    from ii_agent.billing.router import router as billing_router
    from ii_agent.credits.router import router as credits_router
    from ii_agent.chat.api.router import router as chat_router
    from ii_agent.chat.api.router import public_router as chat_public_router
    from ii_agent.content.media.router import router as media_router
    from ii_agent.content.slides.router import router as slides_router
    from ii_agent.content.slides.router import public_router as slides_public_router
    from ii_agent.content.storybook.router import router as storybook_router
    from ii_agent.content.storybook.router import public_router as storybook_public_router
    from ii_agent.files.router import router as files_router
    from ii_agent.files.router import public_router as files_public_router
    from ii_agent.integrations.connectors.router import router as connectors_router
    from ii_agent.integrations.enhance_prompt.router import router as enhance_prompt_router
    from ii_agent.projects.router import router as project_router
    from ii_agent.sessions.router import router as sessions_router
    from ii_agent.sessions.router import public_router as sessions_public_router
    from ii_agent.settings.router import router as settings_router
    from ii_agent.memory.router import router as memory_router

    # ── Root-level routes (no /v1 prefix) ────────────────────────────────
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(billing_router)

    # ── Versioned API routes (/v1) ───────────────────────────────────────
    v1_router = APIRouter(prefix="/v1")

    v1_router.include_router(sessions_router)  # /v1/sessions (includes /pins, /wishlist)
    v1_router.include_router(credits_router)  # /v1/credits
    v1_router.include_router(chat_router)  # /v1/chat
    v1_router.include_router(files_router)  # /v1/assets/*
    v1_router.include_router(
        slides_router
    )  # /v1/slides (includes /templates, /design, /nano-banana)
    v1_router.include_router(storybook_router)  # /v1/storybooks
    v1_router.include_router(
        project_router
    )  # /v1/project (includes /design, /subdomains, /database, /secrets, /deployment)
    v1_router.include_router(connectors_router)  # /v1/connectors/*
    v1_router.include_router(enhance_prompt_router)  # /v1/enhance-prompt
    v1_router.include_router(settings_router)  # /v1/user-settings (includes /models, /mcp, /skills)
    v1_router.include_router(media_router)  # /v1/media, /v1/media-templates, /v1/media-tools
    v1_router.include_router(memory_router)  # /v1/memories

    app.include_router(v1_router)

    # ── Public API routes (/v1/public) ───────────────────────────────────
    v1_public_router = APIRouter(prefix="/v1/public")

    v1_public_router.include_router(sessions_public_router)  # /v1/public/sessions
    v1_public_router.include_router(files_public_router)  # /v1/public/sessions (assets)
    v1_public_router.include_router(chat_public_router)  # /v1/public/chat/conversations
    v1_public_router.include_router(storybook_public_router)  # /v1/public/storybooks
    v1_public_router.include_router(slides_public_router)  # /v1/public/slides

    app.include_router(v1_public_router)
