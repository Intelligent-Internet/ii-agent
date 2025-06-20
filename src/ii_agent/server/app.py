import logging
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
import os
from fastapi.staticfiles import StaticFiles

from .api import upload_router, sessions_router, settings_router
from ii_agent.server import shared

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        args: Configuration arguments

    Returns:
        FastAPI: Configured FastAPI application instance
    """
    app = FastAPI(title="Agent WebSocket API")

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Allows all origins
        allow_credentials=True,
        allow_methods=["*"],  # Allows all methods
        allow_headers=["*"],  # Allows all headers
    )

    # Store global args in app state for access in endpoints
    app.state.workspace = shared.config.workspace_root

    

    # Include API routers
    app.include_router(upload_router)
    app.include_router(sessions_router)
    app.include_router(settings_router)

    # Setup workspace static files
    setup_workspace(app, shared.config.workspace_root)

    # WebSocket endpoint
    @app.websocket("/ws")
    async def websocket_handler(websocket: WebSocket):
        session = await shared.connection_manager.connect(websocket)
        await session.start_chat_loop()

    return app


def setup_workspace(app: FastAPI, workspace_path: str):
    """Setup workspace static files mounting for the FastAPI app.

    Args:
        app: FastAPI application instance
        workspace_path: Path to the workspace directory
    """
    try:
        app.mount(
            "/workspace",
            StaticFiles(directory=workspace_path, html=True),
            name="workspace",
        )
    except RuntimeError:
        # Directory might not exist yet
        os.makedirs(workspace_path, exist_ok=True)
        app.mount(
            "/workspace",
            StaticFiles(directory=workspace_path, html=True),
            name="workspace",
        )
