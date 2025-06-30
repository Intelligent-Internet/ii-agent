"""FastAPI server that combines terminal and string replacement operations."""

import logging
from typing import Optional, List

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from .server.str_replace_server import create_app as create_str_replace_app
from .server.terminal_server import create_app as create_terminal_app

logger = logging.getLogger(__name__)


class CombinedSandboxServer:
    """Combined FastAPI server for both terminal and string replacement operations."""

    def __init__(
        self,
        # String replace parameters
        ignore_indentation_for_str_replace: bool = False,
        expand_tabs: bool = False,
        # Terminal parameters
        default_shell: str = "/bin/bash",
        default_timeout: int = 10,
        container_id: Optional[str] = None,
        cwd: Optional[str] = None,
        # Common parameters
        allowed_origins: Optional[List[str]] = None,
    ):
        self.app = FastAPI(
            title="Combined Sandbox Server",
            description="HTTP API for both terminal operations and file editing operations",
            version="1.0.0",
        )

        # Add CORS middleware
        if allowed_origins is None:
            allowed_origins = ["*"]

        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Create the sub-applications
        str_replace_app = create_str_replace_app(
            ignore_indentation_for_str_replace=ignore_indentation_for_str_replace,
            expand_tabs=expand_tabs,
            allowed_origins=allowed_origins,
            cwd=cwd,
        )

        terminal_app = create_terminal_app(
            default_shell=default_shell,
            default_timeout=default_timeout,
            container_id=container_id,
            cwd=cwd,
            allowed_origins=allowed_origins,
        )

        # Mount the sub-applications
        self.app.mount("/api/str_replace", str_replace_app)
        self.app.mount("/api/terminal", terminal_app)

        # Setup main routes
        self._setup_routes()

        # Setup exception handlers
        self._setup_exception_handlers()

    def _setup_routes(self):
        """Setup main API routes."""

        @self.app.get("/health")
        async def health_check():
            """Health check endpoint."""
            return {
                "status": "ok",
                "message": "Combined Sandbox Server is running",
                "services": {
                    "str_replace": "available at /api/str_replace/",
                    "terminal": "available at /api/terminal/",
                },
            }

        @self.app.get("/")
        async def root():
            """Root endpoint with service information."""
            return {
                "title": "Combined Sandbox Server",
                "description": "HTTP API for both terminal operations and file editing operations",
                "version": "1.0.0",
                "services": {
                    "str_replace": {
                        "description": "File editing operations",
                        "base_path": "/api/str_replace",
                        "endpoints": [
                            "/api/str_replace/health",
                            "/api/str_replace/validate_path",
                            "/api/str_replace/view",
                            "/api/str_replace/str_replace",
                            "/api/str_replace/insert",
                            "/api/str_replace/undo_edit",
                            "/api/str_replace/read_file",
                            "/api/str_replace/write_file",
                            "/api/str_replace/is_path_in_directory",
                        ],
                    },
                    "terminal": {
                        "description": "Terminal operations",
                        "base_path": "/api/terminal",
                        "endpoints": [
                            "/api/terminal/health",
                            "/api/terminal/create_session",
                            "/api/terminal/shell_exec",
                            "/api/terminal/shell_view",
                            "/api/terminal/shell_wait",
                            "/api/terminal/shell_write_to_process",
                            "/api/terminal/shell_kill_process",
                        ],
                    },
                },
            }

    def _setup_exception_handlers(self):
        """Setup global exception handlers."""

        @self.app.exception_handler(Exception)
        async def global_exception_handler(request: Request, exc: Exception):
            logger.error(f"Unhandled exception: {exc}")
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "message": f"Internal server error: {str(exc)}",
                },
            )

    def run(self, host: str = "0.0.0.0", port: int = 8001, **kwargs):
        """Run the FastAPI server."""
        uvicorn.run(self.app, host=host, port=port, **kwargs)


def create_combined_app(
    # String replace parameters
    ignore_indentation_for_str_replace: bool = False,
    expand_tabs: bool = False,
    # Terminal parameters
    default_shell: str = "/bin/bash",
    default_timeout: int = 10,
    container_id: Optional[str] = None,
    cwd: Optional[str] = None,
    # Common parameters
    allowed_origins: Optional[List[str]] = None,
) -> FastAPI:
    """Factory function to create the combined FastAPI app."""
    server = CombinedSandboxServer(
        ignore_indentation_for_str_replace=ignore_indentation_for_str_replace,
        expand_tabs=expand_tabs,
        default_shell=default_shell,
        default_timeout=default_timeout,
        container_id=container_id,
        cwd=cwd,
        allowed_origins=allowed_origins,
    )
    return server.app


def main():
    """Main entry point for running the combined server."""
    import argparse

    parser = argparse.ArgumentParser(description="Combined Sandbox Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8001, help="Port to bind to")

    # String replace options
    parser.add_argument(
        "--ignore-indentation",
        action="store_true",
        help="Ignore indentation for string replacement",
    )
    parser.add_argument(
        "--expand-tabs", action="store_true", help="Expand tabs in file content"
    )

    # Terminal options
    parser.add_argument("--shell", default="/bin/bash", help="Default shell to use")
    parser.add_argument("--timeout", type=int, default=10, help="Default timeout")
    parser.add_argument(
        "--container-id", help="Docker container ID for containerized execution"
    )
    parser.add_argument("--cwd", default="/workspace", help="Default working directory")

    # Common options
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Create and run server
    server = CombinedSandboxServer(
        ignore_indentation_for_str_replace=args.ignore_indentation,
        expand_tabs=args.expand_tabs,
        default_shell=args.shell,
        default_timeout=args.timeout,
        container_id=args.container_id,
        cwd=args.cwd,
    )

    logger.info(f"Starting Combined Sandbox Server on {args.host}:{args.port}")
    logger.info("String replace operations available at /api/str_replace/")
    logger.info("Terminal operations available at /api/terminal/")
    server.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
