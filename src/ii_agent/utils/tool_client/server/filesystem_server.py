"""FastAPI server for file system operations using FileSystemManager."""

import logging
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

from ..manager.filesystem_manager import FileSystemManager

logger = logging.getLogger(__name__)


# Pydantic models for request/response validation
class FileSystemServerResponse(BaseModel):
    success: bool = Field(..., description="Whether the operation was successful")
    file_content: str = Field(..., description="File content or error message")


class ReadFileRequest(BaseModel):
    file_path: str = Field(..., description="The absolute path to the file to read")
    limit: Optional[int] = Field(None, description="The number of lines to read")
    offset: Optional[int] = Field(None, description="The line number to start reading from")


class EditFileRequest(BaseModel):
    file_path: str = Field(..., description="The absolute path to the file to modify")
    old_string: str = Field(..., description="The text to replace")
    new_string: str = Field(..., description="The text to replace it with")
    replace_all: bool = Field(False, description="Replace all occurrences of old_string")


class WriteFileRequest(BaseModel):
    file_path: str = Field(..., description="The absolute path to the file to write")
    content: str = Field(..., description="The content to write to the file")


class MultiEditRequest(BaseModel):
    file_path: str = Field(..., description="The absolute path to the file to modify")
    edits: List[Dict[str, Any]] = Field(..., description="Array of edit operations")


class LSRequest(BaseModel):
    path: str = Field(..., description="The absolute path to the directory to list")
    ignore: Optional[List[str]] = Field(None, description="List of glob patterns to ignore")


class GlobRequest(BaseModel):
    pattern: str = Field(..., description="The glob pattern to match files against")
    path: Optional[str] = Field(None, description="The directory to search in")


class GrepRequest(BaseModel):
    pattern: str = Field(..., description="The regular expression pattern to search for")
    path: Optional[str] = Field(None, description="The directory to search in")
    include: Optional[str] = Field(None, description="File pattern to include in the search")


class FileSystemServer:
    """FastAPI server for file system operations."""

    def __init__(
        self,
        workspace_path: str = "/workspace",
        allowed_origins: Optional[List[str]] = None,
    ):
        self.app = FastAPI(
            title="File System Server",
            description="HTTP API for file system operations using FileSystemManager",
            version="1.0.0",
        )

        # Initialize filesystem manager
        self.filesystem_manager = FileSystemManager(workspace_path)

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
            return {"status": "ok", "message": "File System Server is running"}

        @self.app.post("/read_file", response_model=FileSystemServerResponse)
        async def read_file(request: ReadFileRequest):
            """Read file contents."""
            try:
                response = self.filesystem_manager.read_file(
                    request.file_path, request.limit, request.offset
                )
                return FileSystemServerResponse(
                    success=response.success, file_content=response.file_content
                )
            except Exception as e:
                logger.error(f"Error in read_file: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/edit_file", response_model=FileSystemServerResponse)
        async def edit_file(request: EditFileRequest):
            """Edit file contents."""
            try:
                response = self.filesystem_manager.edit_file(
                    request.file_path,
                    request.old_string,
                    request.new_string,
                    request.replace_all,
                )
                return FileSystemServerResponse(
                    success=response.success, file_content=response.file_content
                )
            except Exception as e:
                logger.error(f"Error in edit_file: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/write_file", response_model=FileSystemServerResponse)
        async def write_file(request: WriteFileRequest):
            """Write file contents."""
            try:
                response = self.filesystem_manager.write_file(
                    request.file_path, request.content
                )
                return FileSystemServerResponse(
                    success=response.success, file_content=response.file_content
                )
            except Exception as e:
                logger.error(f"Error in write_file: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/multi_edit", response_model=FileSystemServerResponse)
        async def multi_edit(request: MultiEditRequest):
            """Perform multiple edits on a file."""
            try:
                response = self.filesystem_manager.multi_edit(
                    request.file_path, request.edits
                )
                return FileSystemServerResponse(
                    success=response.success, file_content=response.file_content
                )
            except Exception as e:
                logger.error(f"Error in multi_edit: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/ls", response_model=FileSystemServerResponse)
        async def ls(request: LSRequest):
            """List directory contents."""
            try:
                response = self.filesystem_manager.ls(request.path, request.ignore)
                return FileSystemServerResponse(
                    success=response.success, file_content=response.file_content
                )
            except Exception as e:
                logger.error(f"Error in ls: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/glob", response_model=FileSystemServerResponse)
        async def glob(request: GlobRequest):
            """Search for files using glob patterns."""
            try:
                response = self.filesystem_manager.glob(request.pattern, request.path)
                return FileSystemServerResponse(
                    success=response.success, file_content=response.file_content
                )
            except Exception as e:
                logger.error(f"Error in glob: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/grep", response_model=FileSystemServerResponse)
        async def grep(request: GrepRequest):
            """Search for content using regex patterns."""
            try:
                response = self.filesystem_manager.grep(
                    request.pattern, request.path, request.include
                )
                return FileSystemServerResponse(
                    success=response.success, file_content=response.file_content
                )
            except Exception as e:
                logger.error(f"Error in grep: {e}")
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
                    "file_content": f"Internal server error: {str(exc)}",
                },
            )

    def run(self, host: str = "0.0.0.0", port: int = 8002, **kwargs):
        """Run the FastAPI server."""
        uvicorn.run(self.app, host=host, port=port, **kwargs)


def create_app(
    workspace_path: str = "/workspace",
    allowed_origins: Optional[List[str]] = None,
    cwd: Optional[str] = None,
) -> FastAPI:
    """Factory function to create the FastAPI app."""
    if cwd:
        workspace_path = cwd
    server = FileSystemServer(
        workspace_path=workspace_path,
        allowed_origins=allowed_origins,
    )
    return server.app


def main():
    """Main entry point for running the server."""
    import argparse

    parser = argparse.ArgumentParser(description="File System Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8002, help="Port to bind to")
    parser.add_argument("--workspace", default="/workspace", help="Workspace path")
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
    server = FileSystemServer(
        workspace_path=args.workspace,
    )

    logger.info(f"Starting File System Server on {args.host}:{args.port}")
    logger.info(f"Workspace path: {args.workspace}")
    server.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()