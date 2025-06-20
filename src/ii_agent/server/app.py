import logging
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
import os
from fastapi.staticfiles import StaticFiles

from ii_agent.core.storage import get_file_store
from .api import upload_router, sessions_router
from ii_agent.server.websocket import ConnectionManager
from ii_agent.server.factories import AgentFactory, AgentConfig, ClientFactory
from ii_agent.core.config.utils import load_ii_agent_config

logger = logging.getLogger(__name__)


def create_app(args) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        args: Configuration arguments

    Returns:
        FastAPI: Configured FastAPI application instance
    """
    app = FastAPI(title="Agent WebSocket API")
    ii_agent_config = load_ii_agent_config()

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Allows all origins
        allow_credentials=True,
        allow_methods=["*"],  # Allows all methods
        allow_headers=["*"],  # Allows all headers
    )

    # Store global args in app state for access in endpoints
    app.state.workspace = args.workspace

    # Create factory instances
    client_factory = ClientFactory(project_id=args.project_id, region=args.region)

    agent_config = AgentConfig(
        logs_path=args.logs_path,
        minimize_stdout_logs=args.minimize_stdout_logs,
        docker_container_id=args.docker_container_id,
        needs_permission=args.needs_permission,
    )
    agent_factory = AgentFactory(agent_config)

    # Create connection manager with injected dependencies
    connection_manager = ConnectionManager(
        workspace_root=args.workspace,
        use_container_workspace=args.use_container_workspace,
        client_factory=client_factory,
        agent_factory=agent_factory,
        file_store=get_file_store(
            ii_agent_config.file_store, ii_agent_config.file_store_path
        ),
    )

    # Include API routers
    app.include_router(upload_router)
    app.include_router(sessions_router)

    # Setup workspace static files
    setup_workspace(app, args.workspace)

    # WebSocket endpoint
    @app.websocket("/ws")
    async def websocket_handler(websocket: WebSocket):
        session = await connection_manager.connect(websocket)
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
