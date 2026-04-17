"""Health-check routes."""

from fastapi import APIRouter

from ii_agent.core.config.settings import get_settings

health_router = APIRouter()


@health_router.get("/health")
async def health_check():
    settings = get_settings()
    response = {"status": "ok"}

    # Only expose internal configuration details in local mode
    if settings.sandbox.local_mode:
        response.update({
            "agent_inner_loop_mode": settings.agent.inner_loop_mode,
            "chat_inner_loop_mode": settings.agent.chat_inner_loop_mode,
            "a2a_backend": settings.agent.a2a_backend,
        })

    return response
