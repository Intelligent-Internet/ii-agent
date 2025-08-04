"""Sandbox manager for handling sandbox lifecycle and operations."""

import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from ii_agent.db.models import Sandbox, User
from ii_agent.server.sandbox.e2b_provider import E2BSandboxProvider
from ii_agent.server.sandbox.models import (
    SandboxInfo,
    SandboxCommandResult,
    SandboxFileInfo,
    SandboxTemplate,
)


class SandboxManager:
    """Manager class for handling sandbox operations."""

    def __init__(self, db: Session):
        self.db = db
        self.e2b_provider = E2BSandboxProvider()

    async def create_sandbox(
        self,
        user: User,
        template: str = "base",
        cpu_limit: int = 1000,
        memory_limit: int = 512,
        disk_limit: int = 1024,
        network_enabled: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SandboxInfo:
        """Create a new sandbox for a user.

        Args:
            user: User who owns the sandbox
            template: Sandbox template
            cpu_limit: CPU limit in millicores
            memory_limit: Memory limit in MB
            disk_limit: Disk limit in MB
            network_enabled: Whether to enable network access
            metadata: Additional metadata

        Returns:
            Created sandbox information
        """
        # Create sandbox with E2B provider
        e2b_sandbox_id = await self.e2b_provider.create_sandbox(
            template=template,
            cpu_limit=cpu_limit,
            memory_limit=memory_limit,
            disk_limit=disk_limit,
            network_enabled=network_enabled,
            metadata=metadata,
        )

        # Create database record
        sandbox = Sandbox(
            id=str(uuid.uuid4()),
            provider="e2b",
            sandbox_id=e2b_sandbox_id,
            user_id=user.id,
            template=template,
            status="initializing",
            cpu_limit=cpu_limit,
            memory_limit=memory_limit,
            disk_limit=disk_limit,
            network_enabled=network_enabled,
            metadata=metadata,
            created_at=datetime.now(timezone.utc),
        )

        self.db.add(sandbox)
        self.db.commit()
        self.db.refresh(sandbox)

        # Start the sandbox
        await self.start_sandbox(sandbox.id)

        return self._convert_to_sandbox_info(sandbox)

    async def start_sandbox(self, sandbox_id: str) -> bool:
        """Start a sandbox.

        Args:
            sandbox_id: Internal sandbox ID

        Returns:
            True if started successfully
        """
        sandbox = self.db.query(Sandbox).filter(Sandbox.id == sandbox_id).first()
        if not sandbox:
            return False

        success = await self.e2b_provider.start_sandbox(sandbox.sandbox_id)

        if success:
            sandbox.status = "running"
            sandbox.started_at = datetime.now(timezone.utc)
            sandbox.last_activity_at = datetime.now(timezone.utc)
            self.db.commit()

        return success

    async def stop_sandbox(self, sandbox_id: str) -> bool:
        """Stop a sandbox.

        Args:
            sandbox_id: Internal sandbox ID

        Returns:
            True if stopped successfully
        """
        sandbox = self.db.query(Sandbox).filter(Sandbox.id == sandbox_id).first()
        if not sandbox:
            return False

        success = await self.e2b_provider.stop_sandbox(sandbox.sandbox_id)

        if success:
            sandbox.status = "stopped"
            sandbox.stopped_at = datetime.now(timezone.utc)
            self.db.commit()

        return success

    async def delete_sandbox(self, sandbox_id: str) -> bool:
        """Delete a sandbox.

        Args:
            sandbox_id: Internal sandbox ID

        Returns:
            True if deleted successfully
        """
        sandbox = self.db.query(Sandbox).filter(Sandbox.id == sandbox_id).first()
        if not sandbox:
            return False

        # Delete from E2B
        success = await self.e2b_provider.delete_sandbox(sandbox.sandbox_id)

        if success:
            # Delete from database
            self.db.delete(sandbox)
            self.db.commit()

        return success

    async def get_sandbox(self, sandbox_id: str) -> Optional[SandboxInfo]:
        """Get sandbox information.

        Args:
            sandbox_id: Internal sandbox ID

        Returns:
            Sandbox information or None if not found
        """
        sandbox = self.db.query(Sandbox).filter(Sandbox.id == sandbox_id).first()
        if not sandbox:
            return None

        # Update status from provider
        try:
            current_status = await self.e2b_provider.get_sandbox_status(
                sandbox.sandbox_id
            )
            if current_status != sandbox.status:
                sandbox.status = current_status
                self.db.commit()
        except Exception:
            # If we can't get status from provider, keep database status
            pass

        return self._convert_to_sandbox_info(sandbox)

    async def list_user_sandboxes(
        self, user_id: str, status: Optional[str] = None
    ) -> List[SandboxInfo]:
        """List sandboxes for a user.

        Args:
            user_id: User ID
            status: Optional status filter

        Returns:
            List of sandbox information
        """
        query = self.db.query(Sandbox).filter(Sandbox.user_id == user_id)

        if status:
            query = query.filter(Sandbox.status == status)

        sandboxes = query.order_by(Sandbox.created_at.desc()).all()

        return [self._convert_to_sandbox_info(sandbox) for sandbox in sandboxes]

    async def execute_command(
        self,
        sandbox_id: str,
        command: str,
        timeout: int = 30,
        working_directory: Optional[str] = None,
    ) -> Optional[SandboxCommandResult]:
        """Execute a command in a sandbox.

        Args:
            sandbox_id: Internal sandbox ID
            command: Command to execute
            timeout: Timeout in seconds
            working_directory: Working directory

        Returns:
            Command execution result or None if sandbox not found
        """
        sandbox = self.db.query(Sandbox).filter(Sandbox.id == sandbox_id).first()
        if not sandbox:
            return None

        # Update last activity
        sandbox.last_activity_at = datetime.now(timezone.utc)
        self.db.commit()

        return await self.e2b_provider.execute_command(
            sandbox.sandbox_id, command, timeout, working_directory
        )

    async def read_file(self, sandbox_id: str, file_path: str) -> Optional[str]:
        """Read a file from a sandbox.

        Args:
            sandbox_id: Internal sandbox ID
            file_path: File path in sandbox

        Returns:
            File content or None if sandbox not found
        """
        sandbox = self.db.query(Sandbox).filter(Sandbox.id == sandbox_id).first()
        if not sandbox:
            return None

        # Update last activity
        sandbox.last_activity_at = datetime.now(timezone.utc)
        self.db.commit()

        return await self.e2b_provider.read_file(sandbox.sandbox_id, file_path)

    async def write_file(
        self, sandbox_id: str, file_path: str, content: str, encoding: str = "utf-8"
    ) -> bool:
        """Write content to a file in a sandbox.

        Args:
            sandbox_id: Internal sandbox ID
            file_path: File path in sandbox
            content: Content to write
            encoding: File encoding

        Returns:
            True if successful, False if sandbox not found
        """
        sandbox = self.db.query(Sandbox).filter(Sandbox.id == sandbox_id).first()
        if not sandbox:
            return False

        # Update last activity
        sandbox.last_activity_at = datetime.now(timezone.utc)
        self.db.commit()

        return await self.e2b_provider.write_file(
            sandbox.sandbox_id, file_path, content, encoding
        )

    async def list_files(
        self, sandbox_id: str, directory_path: str = "/"
    ) -> Optional[List[SandboxFileInfo]]:
        """List files in a sandbox directory.

        Args:
            sandbox_id: Internal sandbox ID
            directory_path: Directory path to list

        Returns:
            List of file information or None if sandbox not found
        """
        sandbox = self.db.query(Sandbox).filter(Sandbox.id == sandbox_id).first()
        if not sandbox:
            return None

        # Update last activity
        sandbox.last_activity_at = datetime.now(timezone.utc)
        self.db.commit()

        return await self.e2b_provider.list_files(sandbox.sandbox_id, directory_path)

    async def get_available_templates(self) -> List[SandboxTemplate]:
        """Get available sandbox templates.

        Returns:
            List of available templates
        """
        return await self.e2b_provider.get_available_templates()

    def _convert_to_sandbox_info(self, sandbox: Sandbox) -> SandboxInfo:
        """Convert database model to API response model.

        Args:
            sandbox: Database sandbox model

        Returns:
            Sandbox information for API response
        """
        return SandboxInfo(
            id=sandbox.id,
            provider=sandbox.provider,
            sandbox_id=sandbox.sandbox_id,
            user_id=sandbox.user_id,
            template=sandbox.template,
            status=sandbox.status,
            cpu_limit=sandbox.cpu_limit,
            memory_limit=sandbox.memory_limit,
            disk_limit=sandbox.disk_limit,
            network_enabled=sandbox.network_enabled,
            metadata=sandbox.metadata,
            created_at=sandbox.created_at.isoformat() if sandbox.created_at else "",
            started_at=sandbox.started_at.isoformat() if sandbox.started_at else None,
            stopped_at=sandbox.stopped_at.isoformat() if sandbox.stopped_at else None,
            last_activity_at=sandbox.last_activity_at.isoformat()
            if sandbox.last_activity_at
            else None,
        )
