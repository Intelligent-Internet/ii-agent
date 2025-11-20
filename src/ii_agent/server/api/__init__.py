"""
REST API endpoints.
"""

from .sessions import router as sessions_router
from ii_agent.server.llm_settings.views import router as llm_settings_router
from ii_agent.server.mcp_settings.views import router as mcp_settings_router
from .auth import router as auth_router
from .files import router as files_router
from .enhance_prompt import router as enhance_prompt_router
from ii_agent.server.wishlist.views import router as wishlist_router
from ii_agent.server.billing import router as billing_router
from ii_agent.server.chat.router import router as chat_router
from .connectors import router as connectors_router
from .nvidia_models import router as nvidia_models_router

__all__ = [
    "sessions_router",
    "llm_settings_router",
    "mcp_settings_router",
    "auth_router",
    "files_router",
    "enhance_prompt_router",
    "wishlist_router",
    "billing_router",
    "chat_router",
    "connectors_router",
    "nvidia_models_router",
]
