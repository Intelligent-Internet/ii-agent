"""FastAPI server for string replacement operations using StrReplaceManager."""

import logging
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

from ..manager.str_replace_manager import StrReplaceManager

logger = logging.getLogger(__name__)


# Pydantic models for request/response validation
class ValidatePathRequest(BaseModel):
    command: str = Field(..., description="The command to validate")
    path_str: str = Field(..., description="Path to validate")
    display_path: Optional[str] = Field(
        None, description="Display path for error messages"
    )


class ViewRequest(BaseModel):
    path_str: str = Field(..., description="Path to view")
    view_range: Optional[List[int]] = Field(None, description="Range of lines to view")
    display_path: Optional[str] = Field(
        None, description="Display path for error messages"
    )


class StrReplaceRequest(BaseModel):
    path_str: str = Field(..., description="Path to the file")
    old_str: str = Field(..., description="String to replace")
    new_str: Optional[str] = Field(None, description="Replacement string")
    display_path: Optional[str] = Field(
        None, description="Display path for error messages"
    )


class InsertRequest(BaseModel):
    path_str: str = Field(..., description="Path to the file")
    insert_line: int = Field(..., description="Line number to insert after")
    new_str: str = Field(..., description="String to insert")
    display_path: Optional[str] = Field(
        None, description="Display path for error messages"
    )


class UndoEditRequest(BaseModel):
    path_str: str = Field(..., description="Path to the file")
    display_path: Optional[str] = Field(
        None, description="Display path for error messages"
    )


class ReadFileRequest(BaseModel):
    path_str: str = Field(..., description="Path to the file")
    display_path: Optional[str] = Field(
        None, description="Display path for error messages"
    )


class WriteFileRequest(BaseModel):
    path_str: str = Field(..., description="Path to the file")
    file: str = Field(..., description="File content to write")
    display_path: Optional[str] = Field(
        None, description="Display path for error messages"
    )


class IsPathInDirectoryRequest(BaseModel):
    directory_str: str = Field(..., description="Directory path")
    path_str: str = Field(..., description="Path to check")


class StrReplaceServerResponse(BaseModel):
    success: bool = Field(..., description="Whether the operation was successful")
    file_content: str = Field(..., description="File content or error message")


class StrReplaceServer:
    """FastAPI server for string replacement operations."""

    def __init__(
        self,
        ignore_indentation_for_str_replace: bool = False,
        expand_tabs: bool = False,
        allowed_origins: Optional[List[str]] = None,
    ):
        self.app = FastAPI(
            title="String Replace Server",
            description="HTTP API for file editing operations using StrReplaceManager",
            version="1.0.0",
        )

        # Initialize the StrReplaceManager
        self.str_replace_manager = StrReplaceManager(
            ignore_indentation_for_str_replace=ignore_indentation_for_str_replace,
            expand_tabs=expand_tabs,
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
            return {"status": "ok", "message": "String Replace Server is running"}

        @self.app.post("/validate_path", response_model=StrReplaceServerResponse)
        async def validate_path(request: ValidatePathRequest):
            """Validate that the path/command combination is valid."""
            try:
                response = self.str_replace_manager.validate_path(
                    request.command, request.path_str, request.display_path
                )
                return StrReplaceServerResponse(
                    success=response.success, file_content=response.file_content
                )
            except Exception as e:
                logger.error(f"Error in validate_path: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/view", response_model=StrReplaceServerResponse)
        async def view(request: ViewRequest):
            """View file or directory contents."""
            try:
                response = self.str_replace_manager.view(
                    request.path_str, request.view_range, request.display_path
                )
                return StrReplaceServerResponse(
                    success=response.success, file_content=response.file_content
                )
            except Exception as e:
                logger.error(f"Error in view: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/str_replace", response_model=StrReplaceServerResponse)
        async def str_replace(request: StrReplaceRequest):
            """Replace old_str with new_str in the file."""
            try:
                logger.info(f"StrReplaceRequest: {request}")
                response = self.str_replace_manager.str_replace(
                    request.path_str,
                    request.old_str,
                    request.new_str,
                    request.display_path,
                )
                return StrReplaceServerResponse(
                    success=response.success, file_content=response.file_content
                )
            except Exception as e:
                logger.error(f"Error in str_replace: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/insert", response_model=StrReplaceServerResponse)
        async def insert(request: InsertRequest):
            """Insert new_str after the specified line."""
            try:
                response = self.str_replace_manager.insert(
                    request.path_str,
                    request.insert_line,
                    request.new_str,
                    request.display_path,
                )
                return StrReplaceServerResponse(
                    success=response.success, file_content=response.file_content
                )
            except Exception as e:
                logger.error(f"Error in insert: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/undo_edit", response_model=StrReplaceServerResponse)
        async def undo_edit(request: UndoEditRequest):
            """Undo the last edit to the file."""
            try:
                response = self.str_replace_manager.undo_edit(
                    request.path_str, request.display_path
                )
                return StrReplaceServerResponse(
                    success=response.success, file_content=response.file_content
                )
            except Exception as e:
                logger.error(f"Error in undo_edit: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/read_file", response_model=StrReplaceServerResponse)
        async def read_file(request: ReadFileRequest):
            """Read the contents of a file."""
            try:
                response = self.str_replace_manager.read_file(
                    request.path_str, request.display_path
                )
                return StrReplaceServerResponse(
                    success=response.success, file_content=response.file_content
                )
            except Exception as e:
                logger.error(f"Error in read_file: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/write_file", response_model=StrReplaceServerResponse)
        async def write_file(request: WriteFileRequest):
            """Write content to a file."""
            try:
                response = self.str_replace_manager.write_file(
                    request.path_str, request.file, request.display_path
                )
                return StrReplaceServerResponse(
                    success=response.success, file_content=response.file_content
                )
            except Exception as e:
                logger.error(f"Error in write_file: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/is_path_in_directory")
        async def is_path_in_directory(request: IsPathInDirectoryRequest):
            """Check if path is within the specified directory."""
            try:
                result = self.str_replace_manager.is_path_in_directory(
                    request.directory_str, request.path_str
                )
                return {"success": True, "file_content": str(result).lower()}
            except Exception as e:
                logger.error(f"Error in is_path_in_directory: {e}")
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

    def run(self, host: str = "0.0.0.0", port: int = 8001, **kwargs):
        """Run the FastAPI server."""
        uvicorn.run(self.app, host=host, port=port, **kwargs)


def create_app(
    ignore_indentation_for_str_replace: bool = False,
    expand_tabs: bool = False,
    allowed_origins: Optional[List[str]] = None,
    cwd: Optional[str] = None,
) -> FastAPI:
    """Factory function to create the FastAPI app."""
    server = StrReplaceServer(
        ignore_indentation_for_str_replace=ignore_indentation_for_str_replace,
        expand_tabs=expand_tabs,
        allowed_origins=allowed_origins,
    )
    return server.app


def main():
    """Main entry point for running the server."""
    import argparse

    parser = argparse.ArgumentParser(description="String Replace Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8001, help="Port to bind to")
    parser.add_argument(
        "--ignore-indentation",
        action="store_true",
        help="Ignore indentation for string replacement",
    )
    parser.add_argument(
        "--expand-tabs", action="store_true", help="Expand tabs in file content"
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
    server = StrReplaceServer(
        ignore_indentation_for_str_replace=args.ignore_indentation,
        expand_tabs=args.expand_tabs,
    )

    logger.info(f"Starting String Replace Server on {args.host}:{args.port}")
    server.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
