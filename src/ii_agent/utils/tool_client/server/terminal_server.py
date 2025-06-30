"""FastAPI server for terminal operations using PexpectSessionManager."""

import logging
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

from ..manager import TmuxSessionManager

logger = logging.getLogger(__name__)


# Pydantic models for request/response validation
class CreateSessionRequest(BaseModel):
    session_id: str = Field(..., description="Session identifier")


class ShellExecRequest(BaseModel):
    session_id: str = Field(..., description="Session identifier")
    command: str = Field(..., description="Command to execute")
    exec_dir: Optional[str] = Field(None, description="Directory to execute command in")
    timeout: int = Field(30, description="Command timeout in seconds")


class ShellViewRequest(BaseModel):
    session_id: str = Field(..., description="Session identifier")


class ShellWaitRequest(BaseModel):
    session_id: str = Field(..., description="Session identifier")
    seconds: int = Field(30, description="Seconds to wait")


class ShellWriteToProcessRequest(BaseModel):
    session_id: str = Field(..., description="Session identifier")
    input_text: str = Field(..., description="Text to write to process")
    press_enter: bool = Field(False, description="Whether to press enter after writing")


class ShellKillProcessRequest(BaseModel):
    session_id: str = Field(..., description="Session identifier")


class TerminalServerResponse(BaseModel):
    success: bool = Field(..., description="Whether the operation was successful")
    output: str = Field(..., description="Output or error message")


class TerminalServer:
    """FastAPI server for terminal operations."""

    def __init__(
        self,
        default_shell: str = "/bin/bash",
        default_timeout: int = 10,
        container_id: Optional[str] = None,
        cwd: Optional[str] = None,
        allowed_origins: Optional[List[str]] = None,
    ):
        self.app = FastAPI(
            title="Terminal Server",
            description="HTTP API for terminal operations using PexpectSessionManager",
            version="1.0.0",
        )

        # Initialize the PexpectSessionManager
        self.session_manager = TmuxSessionManager(
            default_shell=default_shell,
            default_timeout=default_timeout,
            container_id=container_id,
            cwd=cwd,
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

        # Setup routes
        self._setup_routes()

        # Setup exception handlers
        self._setup_exception_handlers()

    def _setup_routes(self):
        """Setup all API routes."""

        @self.app.get("/health")
        async def health_check():
            """Health check endpoint."""
            return {"status": "ok", "message": "Terminal Server is running"}

        @self.app.post("/create_session", response_model=TerminalServerResponse)
        async def create_session(request: CreateSessionRequest):
            """Create a new terminal session."""
            try:
                session = self.session_manager.create_session(request.session_id)
                if session.state.value == "error":
                    return TerminalServerResponse(
                        success=False,
                        output=f"Failed to create session {request.session_id}",
                    )
                return TerminalServerResponse(
                    success=True,
                    output=f"Session {request.session_id} created successfully",
                )
            except Exception as e:
                logger.error(f"Error in create_session: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/shell_exec", response_model=TerminalServerResponse)
        async def shell_exec(request: ShellExecRequest):
            """Execute a shell command in a session."""
            try:
                result = self.session_manager.shell_exec(
                    request.session_id,
                    request.command,
                    request.exec_dir,
                    request.timeout,
                )
                return TerminalServerResponse(
                    success=result.success, output=result.output
                )
            except Exception as e:
                logger.error(f"Error in shell_exec: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/shell_view", response_model=TerminalServerResponse)
        async def shell_view(request: ShellViewRequest):
            """Get current view of a shell session."""
            try:
                result = self.session_manager.shell_view(request.session_id)
                return TerminalServerResponse(
                    success=result.success, output=result.output
                )
            except Exception as e:
                logger.error(f"Error in shell_view: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/shell_wait", response_model=TerminalServerResponse)
        async def shell_wait(request: ShellWaitRequest):
            """Wait for a shell session to complete current command."""
            try:
                result = self.session_manager.shell_wait(
                    request.session_id, request.seconds
                )
                # shell_wait returns a string, convert to SessionResult format
                if isinstance(result, str):
                    return TerminalServerResponse(success=True, output=result)
                else:
                    return TerminalServerResponse(
                        success=result.success, output=result.output
                    )
            except Exception as e:
                logger.error(f"Error in shell_wait: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/shell_write_to_process", response_model=TerminalServerResponse)
        async def shell_write_to_process(request: ShellWriteToProcessRequest):
            """Write text to a running process in a shell session."""
            try:
                result = self.session_manager.shell_write_to_process(
                    request.session_id, request.input_text, request.press_enter
                )
                return TerminalServerResponse(
                    success=result.success, output=result.output
                )
            except Exception as e:
                logger.error(f"Error in shell_write_to_process: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/shell_kill_process", response_model=TerminalServerResponse)
        async def shell_kill_process(request: ShellKillProcessRequest):
            """Kill the process in a shell session."""
            try:
                result = self.session_manager.shell_kill_process(request.session_id)
                return TerminalServerResponse(
                    success=result.success, output=result.output
                )
            except Exception as e:
                logger.error(f"Error in shell_kill_process: {e}")
                raise HTTPException(status_code=500, detail=str(e))

    def _setup_exception_handlers(self):
        """Setup global exception handlers."""

        @self.app.exception_handler(Exception)
        async def global_exception_handler(request: Request, exc: Exception):
            logger.error(f"Unhandled exception: {exc}")
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "output": f"Internal server error: {str(exc)}",
                },
            )

    def run(self, host: str = "0.0.0.0", port: int = 8002, **kwargs):
        """Run the FastAPI server."""
        uvicorn.run(self.app, host=host, port=port, **kwargs)


def create_app(
    default_shell: str = "/bin/bash",
    default_timeout: int = 10,
    container_id: Optional[str] = None,
    cwd: Optional[str] = None,
    allowed_origins: Optional[List[str]] = None,
) -> FastAPI:
    """Factory function to create the terminal FastAPI app."""
    server = TerminalServer(
        default_shell=default_shell,
        default_timeout=default_timeout,
        container_id=container_id,
        cwd=cwd,
        allowed_origins=allowed_origins,
    )
    return server.app


def main():
    """Main entry point for running the terminal server."""
    import argparse

    parser = argparse.ArgumentParser(description="Terminal Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8002, help="Port to bind to")
    parser.add_argument("--shell", default="/bin/bash", help="Default shell to use")
    parser.add_argument("--timeout", type=int, default=10, help="Default timeout")
    parser.add_argument(
        "--container-id", help="Docker container ID for containerized execution"
    )
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
    server = TerminalServer(
        default_shell=args.shell,
        default_timeout=args.timeout,
        container_id=args.container_id,
        cwd=args.cwd,
    )

    logger.info(f"Starting Terminal Server on {args.host}:{args.port}")
    server.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
