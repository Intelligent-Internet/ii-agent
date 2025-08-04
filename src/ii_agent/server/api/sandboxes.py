"""Sandbox management API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from ii_agent.db.manager import get_db
from ii_agent.db.models import User
from ii_agent.server.auth.middleware import get_current_user
from ii_agent.server.sandbox.manager import SandboxManager
from ii_agent.server.sandbox.models import (
    SandboxCreate,
    SandboxInfo,
    SandboxCommand,
    SandboxCommandResult,
    SandboxFile,
    SandboxFileInfo,
    SandboxTemplate,
)


router = APIRouter(prefix="/sandboxes", tags=["Sandbox Management"])


async def get_sandbox_manager(db: Session = Depends(get_db)) -> SandboxManager:
    """Dependency to get sandbox manager instance."""
    return SandboxManager(db)


@router.post("/", response_model=SandboxInfo, status_code=status.HTTP_201_CREATED)
async def create_sandbox(
    sandbox_data: SandboxCreate,
    current_user: User = Depends(get_current_user),
    sandbox_manager: SandboxManager = Depends(get_sandbox_manager),
):
    """Create a new sandbox."""

    return await sandbox_manager.create_sandbox(
        user=current_user,
        template=sandbox_data.template,
        cpu_limit=sandbox_data.cpu_limit,
        memory_limit=sandbox_data.memory_limit,
        disk_limit=sandbox_data.disk_limit,
        network_enabled=sandbox_data.network_enabled,
        metadata=sandbox_data.metadata,
    )


@router.get("/", response_model=List[SandboxInfo])
async def list_sandboxes(
    status: Optional[str] = Query(None, description="Filter by status"),
    current_user: User = Depends(get_current_user),
    sandbox_manager: SandboxManager = Depends(get_sandbox_manager),
):
    """List user's sandboxes."""

    return await sandbox_manager.list_user_sandboxes(
        user_id=current_user.id, status=status
    )


@router.get("/templates", response_model=List[SandboxTemplate])
async def get_sandbox_templates(
    sandbox_manager: SandboxManager = Depends(get_sandbox_manager),
):
    """Get available sandbox templates."""

    return await sandbox_manager.get_available_templates()


@router.get("/{sandbox_id}", response_model=SandboxInfo)
async def get_sandbox(
    sandbox_id: str,
    current_user: User = Depends(get_current_user),
    sandbox_manager: SandboxManager = Depends(get_sandbox_manager),
):
    """Get a specific sandbox."""

    sandbox = await sandbox_manager.get_sandbox(sandbox_id)

    if not sandbox:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Sandbox not found"
        )

    # Check if user owns the sandbox
    if sandbox.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
        )

    return sandbox


@router.post("/{sandbox_id}/start")
async def start_sandbox(
    sandbox_id: str,
    current_user: User = Depends(get_current_user),
    sandbox_manager: SandboxManager = Depends(get_sandbox_manager),
):
    """Start a sandbox."""

    # Verify ownership
    sandbox = await sandbox_manager.get_sandbox(sandbox_id)
    if not sandbox or sandbox.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Sandbox not found"
        )

    success = await sandbox_manager.start_sandbox(sandbox_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start sandbox",
        )

    return {"message": "Sandbox started successfully"}


@router.post("/{sandbox_id}/stop")
async def stop_sandbox(
    sandbox_id: str,
    current_user: User = Depends(get_current_user),
    sandbox_manager: SandboxManager = Depends(get_sandbox_manager),
):
    """Stop a sandbox."""

    # Verify ownership
    sandbox = await sandbox_manager.get_sandbox(sandbox_id)
    if not sandbox or sandbox.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Sandbox not found"
        )

    success = await sandbox_manager.stop_sandbox(sandbox_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to stop sandbox",
        )

    return {"message": "Sandbox stopped successfully"}


@router.delete("/{sandbox_id}")
async def delete_sandbox(
    sandbox_id: str,
    current_user: User = Depends(get_current_user),
    sandbox_manager: SandboxManager = Depends(get_sandbox_manager),
):
    """Delete a sandbox."""

    # Verify ownership
    sandbox = await sandbox_manager.get_sandbox(sandbox_id)
    if not sandbox or sandbox.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Sandbox not found"
        )

    success = await sandbox_manager.delete_sandbox(sandbox_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete sandbox",
        )

    return {"message": "Sandbox deleted successfully"}


@router.post("/{sandbox_id}/execute", response_model=SandboxCommandResult)
async def execute_command(
    sandbox_id: str,
    command_data: SandboxCommand,
    current_user: User = Depends(get_current_user),
    sandbox_manager: SandboxManager = Depends(get_sandbox_manager),
):
    """Execute a command in the sandbox."""

    # Verify ownership
    sandbox = await sandbox_manager.get_sandbox(sandbox_id)
    if not sandbox or sandbox.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Sandbox not found"
        )

    if sandbox.status != "running":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sandbox must be running to execute commands",
        )

    result = await sandbox_manager.execute_command(
        sandbox_id=sandbox_id,
        command=command_data.command,
        timeout=command_data.timeout,
        working_directory=command_data.working_directory,
    )

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to execute command",
        )

    return result


@router.get("/{sandbox_id}/files", response_model=List[SandboxFileInfo])
async def list_files(
    sandbox_id: str,
    path: str = Query("/", description="Directory path to list"),
    current_user: User = Depends(get_current_user),
    sandbox_manager: SandboxManager = Depends(get_sandbox_manager),
):
    """List files in a sandbox directory."""

    # Verify ownership
    sandbox = await sandbox_manager.get_sandbox(sandbox_id)
    if not sandbox or sandbox.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Sandbox not found"
        )

    files = await sandbox_manager.list_files(sandbox_id, path)

    if files is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list files",
        )

    return files


@router.get("/{sandbox_id}/files/read")
async def read_file(
    sandbox_id: str,
    path: str = Query(..., description="File path to read"),
    current_user: User = Depends(get_current_user),
    sandbox_manager: SandboxManager = Depends(get_sandbox_manager),
):
    """Read a file from the sandbox."""

    # Verify ownership
    sandbox = await sandbox_manager.get_sandbox(sandbox_id)
    if not sandbox or sandbox.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Sandbox not found"
        )

    content = await sandbox_manager.read_file(sandbox_id, path)

    if content is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to read file",
        )

    return {"path": path, "content": content}


@router.post("/{sandbox_id}/files/write")
async def write_file(
    sandbox_id: str,
    file_data: SandboxFile,
    current_user: User = Depends(get_current_user),
    sandbox_manager: SandboxManager = Depends(get_sandbox_manager),
):
    """Write content to a file in the sandbox."""

    # Verify ownership
    sandbox = await sandbox_manager.get_sandbox(sandbox_id)
    if not sandbox or sandbox.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Sandbox not found"
        )

    if file_data.content is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="File content is required"
        )

    success = await sandbox_manager.write_file(
        sandbox_id=sandbox_id,
        file_path=file_data.path,
        content=file_data.content,
        encoding=file_data.encoding,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to write file",
        )

    return {"message": "File written successfully", "path": file_data.path}
