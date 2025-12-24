import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
import socketio
from fastapi.middleware.gzip import GZipMiddleware
from ii_agent.core.exceptions import NotFoundException, PermissionException
from ii_agent.cron.tasks import shutdown_scheduler, start_scheduler
from ii_agent.core.middleware import exception_logging_middleware, not_found_exception_handler, permission_exception_handler

from .api import (
    sessions_router,
    llm_settings_router,
    auth_router,
    files_router,
    mcp_settings_router,
    enhance_prompt_router,
    wishlist_router,
    billing_router,
    chat_router,
    connectors_router,
)
from .slides.views import router as slides_router
from .slides.template_views import router as slide_templates_router
from .credits import credits_router
from ii_agent.server import shared
from ii_agent.core.config.ii_agent_config import config
from ii_agent.server.socket.socketio import SocketIOManager
logger = logging.getLogger(__name__)


health_router = APIRouter()


@health_router.get("/health")
async def health_check():
    return {"status": "ok"}


def setup_socketio_server(sio: socketio.AsyncServer):
    """Setup Socket.IO event handlers."""
    
    sio_manager = SocketIOManager(sio)
    sio_manager.init()
        
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan events."""
    # Startup: Initialize admin LLM settings
    from ii_agent.db.manager import ensure_admin_llm_settings_seeded
    try:
        await ensure_admin_llm_settings_seeded()
        start_scheduler()
        logger.info("Admin LLM settings initialized during startup")
    except Exception as e:
        logger.error(f"Failed to initialize admin LLM settings during startup: {e}")

    yield
    
    # Redis cleanup is handled by AsyncRedisManager (session_manager)
    # await shared.redis_client.aclose()  # This attribute doesn't exist
    shutdown_scheduler()

def create_app():
    """Create and configure the FastAPI application with Socket.IO integration.

    Returns:
        socketio.ASGIApp: Configured Socket.IO application instance
    """

    docs_enabled = config.environment != "production"

    # Create FastAPI app
    app = FastAPI(
        title="Agent Socket.IO API",
        lifespan=lifespan,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Allows all origins
        allow_credentials=True,
        allow_methods=["*"],  # Allows all methods
        allow_headers=["*"],  # Allows all headers
    )

    # Add session middleware for OAuth state and PKCE storage
    app.add_middleware(
        SessionMiddleware,
        secret_key=shared.config.session_secret_key,
        same_site="lax",
        https_only=False,
    )
    app.middleware("http")(exception_logging_middleware)
    app.add_middleware(GZipMiddleware)
    # Register exception handlers
    app.exception_handler(PermissionException)(permission_exception_handler)
    app.exception_handler(NotFoundException)(not_found_exception_handler)
    # Store global args in app state for access in endpoints
    app.state.workspace = shared.config.workspace_path


    # Include API routers (organized by domain)
    app.include_router(auth_router)  # /auth/*
    app.include_router(sessions_router)  # /sessions/*
    app.include_router(credits_router)  # /credits/*
    app.include_router(llm_settings_router)  # /user-settings/llm/*
    app.include_router(mcp_settings_router)  # /user-settings/mcp/*
    app.include_router(files_router)  # /files/*
    app.include_router(slides_router)  # /slides/*
    app.include_router(slide_templates_router)  # /slide-templates/*
    app.include_router(wishlist_router)  # /wishlist/*
    app.include_router(enhance_prompt_router)  # /enhance-prompt/*
    app.include_router(billing_router)  # /billing/*
    app.include_router(chat_router)  # /chat/*
    app.include_router(connectors_router)  # /connectors/*
    app.include_router(health_router)

    # Create Socket.IO server with increased timeout settings
    sio = socketio.AsyncServer(
        async_mode="asgi",
        cors_allowed_origins="*",
        ping_timeout=300,  # 120 seconds before considering connection dead (default is 20s)
        ping_interval=30,  # Send ping every 30 seconds (default is 25s)
        max_http_buffer_size=10 * 1024 * 1024,  # 10MB max message size
        client_manager=shared.session_manager
    )

    setup_socketio_server(sio=sio)

    # Create Socket.IO ASGI app that wraps FastAPI
    socket_app = socketio.ASGIApp(sio, app)

    return socket_app
