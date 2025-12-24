"""Main FastAPI application for the sandbox server."""

import httpx
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, status, File, UploadFile, Form
from fastapi.responses import StreamingResponse, Response

from ii_sandbox_server.config import SandboxConfig, SandboxServerConfig
from ii_sandbox_server.lifecycle.sandbox_controller import SandboxController
from ii_sandbox_server.sandboxes.port_manager import PortPoolManager
from ii_sandbox_server.models import (
    CreateSandboxRequest,
    CreateSandboxResponse,
    ConnectSandboxRequest,
    ConnectSandboxResponse,
    ScheduleTimeoutRequest,
    SandboxStatusResponse,
    ExposePortRequest,
    ExposePortResponse,
    FileOperationRequest,
    FileOperationResponse,
    UploadFileFromUrlRequest,
    DownloadToPresignedUrlRequest,
    RunCommandRequest,
    RunCommandResponse,
    SandboxInfo,
)
from ii_sandbox_server.models.exceptions import (
    SandboxAuthenticationError,
    SandboxNotFoundException,
    SandboxTimeoutException,
    SandboxNotInitializedError,
)

from ii_sandbox_server.db.model import Base
from ii_sandbox_server.db.manager import engine

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Global sandbox manager instance
sandbox_controller: Optional[SandboxController] = None


async def init_database():
    """Initialize the database."""
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Error creating database tables: {e}")
        raise


def handle_sandbox_exception(e: Exception):
    """Handle sandbox exceptions and return appropriate HTTP status code."""
    if isinstance(e, SandboxAuthenticationError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    elif isinstance(e, SandboxNotFoundException) or isinstance(e, FileNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    elif isinstance(e, SandboxTimeoutException):
        raise HTTPException(status_code=status.HTTP_408_REQUEST_TIMEOUT, detail=str(e))
    elif isinstance(e, SandboxNotInitializedError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        )
    else:
        # Generic server error for other exceptions
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    global sandbox_controller

    # Startup
    await init_database()
    config = SandboxServerConfig()
    sandbox_config = SandboxConfig()

    sandbox_controller = SandboxController(sandbox_config)
    await sandbox_controller.start()
    logger.info(f"Sandbox server started on {config.host}:{config.port}")

    yield

    # Shutdown
    if sandbox_controller:
        await sandbox_controller.shutdown()
    logger.info("Sandbox server stopped")


# Create FastAPI app
app = FastAPI(
    title="II Sandbox Server",
    description="Standalone server for managing sandbox lifecycle",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/ports/stats")
async def get_port_stats():
    """Get port pool statistics.
    
    Returns information about allocated and available ports in the sandbox port pool.
    """
    port_manager = PortPoolManager.get_instance()
    return port_manager.get_stats()


@app.get("/ports/allocations")
async def list_port_allocations():
    """List all current port allocations.
    
    Returns details of which ports are allocated to which sandboxes.
    """
    port_manager = PortPoolManager.get_instance()
    return {"allocations": port_manager.list_allocations()}


@app.post("/ports/cleanup")
async def cleanup_orphaned_ports():
    """Clean up port allocations for containers that no longer exist.
    
    This removes port reservations for crashed or manually removed containers.
    """
    import docker
    port_manager = PortPoolManager.get_instance()
    try:
        client = docker.from_env()
        cleaned = port_manager.cleanup_orphaned_allocations(client)
        return {"cleaned": cleaned, "message": f"Cleaned up {cleaned} orphaned allocations"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/sandboxes/create", response_model=CreateSandboxResponse)
async def create_sandbox(request: CreateSandboxRequest):
    """Create a new sandbox."""
    if not sandbox_controller:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sandbox manager not initialized",
        )

    try:
        sandbox = await sandbox_controller.create_sandbox(
            user_id=request.user_id,
            sandbox_template_id=request.sandbox_template_id,
        )

        return CreateSandboxResponse(
            success=True,
            sandbox_id=sandbox.sandbox_id,
            provider_sandbox_id=sandbox.provider_sandbox_id,
            status="running",
            message="Sandbox created successfully",
        )

    except Exception as e:
        logger.error(f"Failed to create sandbox: {e}")
        handle_sandbox_exception(e)


@app.post("/sandboxes/connect", response_model=ConnectSandboxResponse)
async def connect_sandbox(request: ConnectSandboxRequest):
    """Connect to or resume a sandbox."""
    if not sandbox_controller:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sandbox manager not initialized",
        )
    try:
        sandbox = await sandbox_controller.connect(sandbox_id=request.sandbox_id)
        return ConnectSandboxResponse(
            success=True,
            sandbox_id=sandbox.sandbox_id,
            provider_sandbox_id=sandbox.provider_sandbox_id,
            status=await sandbox_controller.get_sandbox_status(request.sandbox_id),
            message="Successfully connected to sandbox",
        )

    except Exception as e:
        logger.error(f"Failed to connect to sandbox: {e}")
        handle_sandbox_exception(e)


@app.post("/sandboxes/schedule-timeout")
async def schedule_timeout(request: ScheduleTimeoutRequest):
    """Schedule a timeout for a sandbox."""
    if not sandbox_controller:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sandbox manager not initialized",
        )

    try:
        await sandbox_controller.schedule_timeout(
            sandbox_id=request.sandbox_id, timeout_seconds=request.timeout_seconds
        )

        return {"success": True, "message": "Timeout scheduled successfully"}

    except Exception as e:
        logger.error(f"Failed to schedule timeout: {e}")
        handle_sandbox_exception(e)


@app.get("/sandboxes/{sandbox_id}/status", response_model=SandboxStatusResponse)
async def get_sandbox_status(sandbox_id: str):
    """Get the status of a sandbox."""
    if not sandbox_controller:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sandbox manager not initialized",
        )

    try:
        sandbox_status = await sandbox_controller.get_sandbox_status(sandbox_id)
        info = await sandbox_controller.get_sandbox_info(sandbox_id)

        return SandboxStatusResponse(
            success=True,
            sandbox_id=sandbox_id,
            status=sandbox_status,
            provider_sandbox_id=info.provider_sandbox_id if info else None,
            message="Status retrieved successfully",
        )
    except Exception as e:
        logger.error(f"Failed to get sandbox status: {e}")
        handle_sandbox_exception(e)


@app.get("/sandboxes/{sandbox_id}/info", response_model=Optional[SandboxInfo])
async def get_sandbox_info(sandbox_id: str):
    """Get detailed information about a sandbox."""
    if not sandbox_controller:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sandbox manager not initialized",
        )

    try:
        info = await sandbox_controller.get_sandbox_info(sandbox_id)
        if not info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Sandbox {sandbox_id} not found",
            )

        # Add success field to info if not present
        info_dict = info.model_dump() if hasattr(info, "model_dump") else info.__dict__
        info_dict["success"] = True
        info_dict["message"] = "Sandbox info retrieved successfully"
        return SandboxInfo(**info_dict)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get sandbox info: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get sandbox info: {str(e)}",
        )


@app.post("/sandboxes/{sandbox_id}/pause")
async def pause_sandbox(sandbox_id: str, reason: str = "manual"):
    """Pause a sandbox."""
    if not sandbox_controller:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sandbox manager not initialized",
        )

    try:
        await sandbox_controller.pause_sandbox(sandbox_id, reason)
        return {
            "success": True,
            "message": f"Sandbox paused successfully (reason: {reason})",
        }

    except Exception as e:
        logger.error(f"Failed to pause sandbox: {e}")
        handle_sandbox_exception(e)


@app.delete("/sandboxes/{sandbox_id}")
async def delete_sandbox(sandbox_id: str):
    """Delete a sandbox."""
    if not sandbox_controller:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sandbox manager not initialized",
        )

    try:
        await sandbox_controller.delete_sandbox(sandbox_id)
        return {"success": True, "message": "Sandbox deleted successfully"}

    except Exception as e:
        logger.error(f"Failed to delete sandbox: {e}")
        handle_sandbox_exception(e)


@app.post("/sandboxes/expose-port", response_model=ExposePortResponse)
async def expose_port(request: ExposePortRequest):
    """Expose a port from a sandbox."""
    if not sandbox_controller:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sandbox manager not initialized",
        )

    try:
        url = await sandbox_controller.expose_port(request.sandbox_id, request.port)

        return ExposePortResponse(
            success=True, url=url, message=f"Port {request.port} exposed successfully"
        )

    except Exception as e:
        logger.error(f"Failed to expose port: {e}")
        handle_sandbox_exception(e)


@app.post("/sandboxes/write-file", response_model=FileOperationResponse)
async def write_file(request: FileOperationRequest):
    """Write a file to a sandbox."""
    if not sandbox_controller:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sandbox manager not initialized",
        )

    if not request.content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Content is required for write operation",
        )

    try:
        success = await sandbox_controller.write_file(
            request.sandbox_id, request.file_path, request.content
        )

        return FileOperationResponse(
            success=success, message=f"File written to {request.file_path}"
        )

    except Exception as e:
        logger.error(f"Failed to write file: {e}")
        handle_sandbox_exception(e)


@app.post("/sandboxes/upload-file", response_model=FileOperationResponse)
async def upload_file(
    sandbox_id: str = Form(...),
    file_path: str = Form(...),
    file: UploadFile = File(...)
):
    """Upload a file to a sandbox."""
    if not sandbox_controller:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sandbox manager not initialized",
        )

    try:
        # Read file content
        content = await file.read()
        
        success = await sandbox_controller.write_file(
            sandbox_id, file_path, content
        )

        return FileOperationResponse(
            success=success, message=f"File uploaded to {file_path}"
        )

    except Exception as e:
        logger.error(f"Failed to upload file: {e}")
        handle_sandbox_exception(e)


@app.post("/sandboxes/upload-file-from-url", response_model=FileOperationResponse)
async def upload_file_from_url(request: UploadFileFromUrlRequest):
    """Upload a file to a sandbox by downloading it from a URL."""
    if not sandbox_controller:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sandbox manager not initialized",
        )

    try:
        # Download file from URL
        async with httpx.AsyncClient() as client:
            response = await client.get(request.url)
            response.raise_for_status()
            content = response.content
        
        # Write file to sandbox
        success = await sandbox_controller.write_file(
            request.sandbox_id, request.file_path, content
        )

        return FileOperationResponse(
            success=success, message=f"File downloaded from URL and uploaded to {request.file_path}"
        )

    except Exception as e:
        logger.error(f"Failed to upload file from URL: {e}")
        handle_sandbox_exception(e)


@app.post("/sandboxes/download-to-presigned-url", response_model=FileOperationResponse)
async def download_to_presigned_url(request: DownloadToPresignedUrlRequest):
    """Download a file from sandbox to a presigned URL."""
    if not sandbox_controller:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sandbox manager not initialized",
        )

    try:
        content = await sandbox_controller.download_file(
            request.sandbox_id, request.sandbox_path, request.format
        )
        
        # Determine content type based on format and file extension
        content_type = "application/octet-stream"  # default
        if request.format == "text":
            content_type = "text/plain"  # default for text files
        elif request.format == "bytes":
            content_type = "application/octet-stream"  # default for binary files
        
        async with httpx.AsyncClient() as client:
            response = await client.put(
                request.presigned_url,
                content=content,
                headers={"Content-Type":content_type}
            )
            response.raise_for_status()

        return FileOperationResponse(
            success=True, message=f"File downloaded from {request.sandbox_path} and uploaded to presigned URL"
        )

    except Exception as e:
        logger.error(f"Failed to download file to presigned URL: {e}")
        handle_sandbox_exception(e)


@app.post("/sandboxes/read-file", response_model=FileOperationResponse)
async def read_file(request: FileOperationRequest):
    """Read a file from a sandbox."""
    if not sandbox_controller:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sandbox manager not initialized",
        )

    try:
        content = await sandbox_controller.read_file(
            request.sandbox_id, request.file_path
        )

        return FileOperationResponse(success=True, content=content)

    except Exception as e:
        logger.error(f"Failed to read file: {e}")
        handle_sandbox_exception(e)


@app.post("/sandboxes/download-file")
async def download_file(request: FileOperationRequest):
    """Download a file from a sandbox (non-streaming)."""
    if not sandbox_controller:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sandbox manager not initialized",
        )

    if request.format == "stream":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use /sandboxes/download-file-stream endpoint for streaming",
        )

    try:
        content = await sandbox_controller.download_file(
            request.sandbox_id, request.file_path, request.format
        )
        
        if request.format == "bytes":
            # Return raw bytes as response
            if isinstance(content, bytes):
                filename = request.file_path.split('/')[-1]
                return Response(
                    content=content,
                    media_type="application/octet-stream",
                    headers={
                        "Content-Disposition": f"attachment; filename={filename}"
                    }
                )
            else:
                # Convert to bytes if needed
                content_bytes = content.encode('utf-8') if isinstance(content, str) else bytes(content)
                filename = request.file_path.split('/')[-1]
                return Response(
                    content=content_bytes,
                    media_type="application/octet-stream",
                    headers={
                        "Content-Disposition": f"attachment; filename={filename}"
                    }
                )
        else:
            # Return JSON response for text format
            return FileOperationResponse(success=True, content=content)
    except Exception as e:
        logger.error(f"Failed to download file: {e}")
        handle_sandbox_exception(e)


@app.post("/sandboxes/download-file-stream")
async def download_file_stream(request: FileOperationRequest):
    """Download a file from a sandbox (streaming)."""
    if not sandbox_controller:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sandbox manager not initialized",
        )

    try:
        # Force stream format for this endpoint
        stream = await sandbox_controller.download_file_stream(
            request.sandbox_id, request.file_path
        )
        return StreamingResponse(
            stream,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f"attachment; filename={request.file_path.split('/')[-1]}"
            },
        )
    except Exception as e:
        logger.error(f"Failed to stream file: {e}")
        handle_sandbox_exception(e)

@app.post("/sandboxes/run-cmd", response_model=RunCommandResponse)
async def run_cmd(request: RunCommandRequest):
    """Run a command in a sandbox."""
    if not sandbox_controller:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sandbox manager not initialized",
        )

    try:
        output = await sandbox_controller.run_cmd(
            request.sandbox_id, request.command, request.background
        )
        return RunCommandResponse(
            success=True,
            output=output,
            message=f"Command executed successfully"
        )
    except Exception as e:
        logger.error(f"Failed to run command: {e}")
        handle_sandbox_exception(e)

@app.post("/sandboxes/create-directory", response_model=FileOperationResponse)
async def create_directory(
    sandbox_id: str, directory_path: str, exist_ok: bool = False
):
    """Create a directory in a sandbox."""
    if not sandbox_controller:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sandbox manager not initialized",
        )

    try:
        success = await sandbox_controller.create_directory(
            sandbox_id, directory_path, exist_ok
        )
        return FileOperationResponse(
            success=success, message=f"Directory created at {directory_path}"
        )
    except Exception as e:
        logger.error(f"Failed to create directory: {e}")
        handle_sandbox_exception(e)


if __name__ == "__main__":
    import uvicorn

    config = SandboxServerConfig()
    uvicorn.run(
        "ii_sandbox_server.main:app", host=config.host, port=config.port, reload=True
    )
