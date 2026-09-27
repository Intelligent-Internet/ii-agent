"""Handler for publishing a project to Google Cloud Run."""

from __future__ import annotations

import hashlib
import os
import re
import uuid
from typing import Any

from ii_agent.realtime.pubsub import AsyncIOPubSub
from ii_agent.realtime.events.app_events import (
    AgentStatusUpdateEvent,
    ErrorCode,
    SystemNotificationEvent,
)
from ii_agent.core.logger import logger
from ii_agent.core.container import ApplicationContainer
from ii_agent.core.db import get_db_session_local
from ii_agent.sessions.schemas import SessionInfo
from ii_agent.projects.cloud_run.schemas import (
    CloudRunConfig,
    DeploymentResult,
    DeploymentStatus,
)
from ii_agent.projects.cloud_run.service import CloudRunPublisher
from ii_agent.realtime.handlers.base import (
    BaseCommandHandler,
    CommandType,
)
from ii_agent.realtime.schemas import CloudRunPublishContent
from ii_agent.agents.sandboxes.base import Sandbox


class CloudRunPublishHandler(BaseCommandHandler[CloudRunPublishContent]):
    """Handler for publishing a project to Cloud Run."""

    _content_type = CloudRunPublishContent

    def __init__(self, pubsub: AsyncIOPubSub, container: ApplicationContainer) -> None:
        super().__init__(pubsub=pubsub, container=container)
        self._publisher: CloudRunPublisher | None = None

    def get_command_type(self) -> CommandType:
        return CommandType.PUBLISH_CLOUD_RUN

    @property
    def publisher(self) -> CloudRunPublisher:
        """Lazy-loaded Cloud Run publisher."""
        if self._publisher is None:
            config = CloudRunConfig.from_env()
            self._publisher = CloudRunPublisher(
                config=config,
                on_status_update=None,  # We handle status updates ourselves
            )
        return self._publisher

    async def handle(self, content: CloudRunPublishContent, session_info: SessionInfo) -> None:
        """Handle project deployment to Cloud Run.

        Args:
            content: Command content with project details
            session_info: Session information
        """
        import time

        container = self._container
        session_id = session_info.id
        deployment_id: uuid.UUID | None = None

        # Resolve project path
        project_path = self._resolve_project_path(content.project_path, session_info)
        if not project_path:
            await self._send_error_event(
                session_id,
                error_code=ErrorCode.MISSING_PROJECT_PATH,
            )
            return

        # Resolve project name and generate service name
        project_name = self._resolve_project_name(content.project_name, project_path)
        session_id_hash = hashlib.sha256(str(session_id).encode()).hexdigest()[:8]
        service_name = f"{project_name}-{session_id_hash}"

        result: DeploymentResult | None = None

        try:
            # Get or create project record
            async with get_db_session_local() as db:
                project = await container.project_service.get_session_project_or_none(
                    db,
                    session_id=session_id,
                    user_id=session_info.user_id,
                )

            project_id = project.id if project else None

            # Create deployment record if we have a project
            if project_id:
                try:
                    async with get_db_session_local() as db:
                        deployment_record = await container.deployments_service.create_deployment(
                            db,
                            project_id=project_id,
                            user_id=session_info.user_id,
                            provider="cloud_run",
                            environment="production",
                            source_path=project_path,
                        )
                    deployment_id = deployment_record.id
                    logger.info(
                        f"Created deployment record {deployment_id} for project {project_id} (v{deployment_record.version})"
                    )
                except Exception as exc:
                    logger.warning(f"Failed to create deployment record: {exc}")

            # Get sandbox for the session
            await self.send_event(
                AgentStatusUpdateEvent(
                    session_id=session_id,
                    message="Connecting to sandbox...",
                    status="connecting",
                    content={"message": "Connecting to sandbox..."},
                )
            )

            try:
                sandbox = await self._get_sandbox(session_info, container)
            except Exception as exc:
                logger.warning(
                    f"Failed to connect to sandbox for Cloud Run publish session {session_id}: {exc}"
                )
                if deployment_id:
                    async with get_db_session_local() as db:
                        await container.deployments_service.update_deployment_status(
                            db,
                            deployment_id=deployment_id,
                            status="failed",
                            error_message=f"Failed to connect to sandbox: {exc}",
                            error_phase="upload",
                            error_details={
                                "code": "SANDBOX_CONNECTION_FAILED",
                                "message": str(exc),
                            },
                        )
                await self._send_error_event(
                    session_id,
                    error_code=ErrorCode.SANDBOX_CONNECTION_FAILED,
                    message=f"Failed to connect to the sandbox environment.\nDetails: {exc}",
                )
                return

            if not sandbox:
                if deployment_id:
                    async with get_db_session_local() as db:
                        await container.deployments_service.update_deployment_status(
                            db,
                            deployment_id=deployment_id,
                            status="failed",
                            error_message="Failed to connect to sandbox.",
                            error_phase="upload",
                            error_details={"code": "SANDBOX_CONNECTION_FAILED"},
                        )
                await self._send_error_event(
                    session_id,
                    error_code=ErrorCode.SANDBOX_CONNECTION_FAILED,
                    message="No active sandbox is available for this session.",
                )
                return

            # Download source from sandbox
            await self.send_event(
                AgentStatusUpdateEvent(
                    session_id=session_id,
                    message="Downloading source code from sandbox...",
                    status="downloading",
                    content={"message": "Downloading source code from sandbox..."},
                )
            )

            upload_start = time.time()
            source_bytes = await self._download_source_from_sandbox(
                sandbox, project_path, project_name
            )
            if not source_bytes:
                if deployment_id:
                    async with get_db_session_local() as db:
                        await container.deployments_service.update_deployment_status(
                            db,
                            deployment_id=deployment_id,
                            status="failed",
                            error_message="Failed to download source code from sandbox.",
                            error_phase="upload",
                            error_details={"code": "SOURCE_DOWNLOAD_FAILED"},
                        )
                await self._send_error_event(
                    session_id,
                    error_code=ErrorCode.SOURCE_DOWNLOAD_FAILED,
                )
                return

            # Extract environment variables if provided
            env_vars = self._extract_env_vars(content)

            # Deploy to Cloud Run
            await self.send_event(
                AgentStatusUpdateEvent(
                    session_id=session_id,
                    message="Uploading source code...",
                    status="uploading",
                    content={"message": "Uploading source code..."},
                )
            )

            # Update deployment status to building
            if deployment_id:
                async with get_db_session_local() as db:
                    await container.deployments_service.update_deployment_status(
                        db,
                        deployment_id=deployment_id,
                        status="building",
                    )

            # Create status callback
            async def on_status(status: DeploymentStatus, message: str):
                await self.send_event(
                    AgentStatusUpdateEvent(
                        session_id=session_id,
                        message=message,
                        status=status.value if hasattr(status, "value") else str(status),
                        content={"message": message},
                    )
                )

            # Set up status callback (synchronous wrapper)
            def status_callback(status: DeploymentStatus, message: str):
                import asyncio

                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.create_task(on_status(status, message))
                    else:
                        loop.run_until_complete(on_status(status, message))
                except Exception:
                    pass  # Best effort status updates

            self.publisher.on_status_update = status_callback

            # Execute deployment
            result = await self.publisher.publish(
                source_bytes=source_bytes,
                service_name=service_name,
                env_vars=env_vars,
            )

            upload_duration_ms = int((time.time() - upload_start) * 1000)

            # Always persist available metadata regardless of success/failure
            if deployment_id:
                metadata = self._build_metadata(service_name, result)
                async with get_db_session_local() as db:
                    await container.deployments_service.update_deployment_metadata(
                        db,
                        deployment_id=deployment_id,
                        metadata=metadata,
                        upload_duration_ms=upload_duration_ms,
                        build_duration_ms=result.build_duration_ms,
                    )

            if not result.success:
                # Update deployment with failure details
                if deployment_id:
                    error_phase = "deploy"
                    if result.error and "build" in result.error.lower():
                        error_phase = "build"
                    elif result.error and "push" in result.error.lower():
                        error_phase = "push"

                    async with get_db_session_local() as db:
                        await container.deployments_service.update_deployment_status(
                            db,
                            deployment_id=deployment_id,
                            status="failed",
                            error_message=result.error,
                            error_phase=error_phase,
                            error_details={
                                "code": "DEPLOYMENT_FAILED",
                                "message": result.error,
                            },
                        )

                await self._send_error_event(
                    session_id,
                    error_code=ErrorCode.DEPLOY_FAILED,
                    message=f"Deployment failed: {result.error}",
                )
                return

            deployment_url = result.url

            # Update deployment record with success status
            if deployment_id:
                async with get_db_session_local() as db:
                    await container.deployments_service.update_deployment_status(
                        db,
                        deployment_id=deployment_id,
                        status="deployed",
                        deployment_url=deployment_url,
                    )

                    # Set as active deployment
                    if project_id:
                        await container.deployments_service.set_active_deployment(
                            db,
                            project_id=project_id,
                            deployment_id=deployment_id,
                        )

            # Save deployment URL to project table
            # User can claim a custom subdomain later via the frontend
            try:
                async with get_db_session_local() as db:
                    await container.project_service.update_session_project_production_url(
                        db,
                        session_id=session_id,
                        user_id=session_info.user_id,
                        production_url=deployment_url,
                    )
            except Exception as exc:
                logger.warning(f"Failed to persist deployment URL for session {session_id}: {exc}")

            # Send success event
            await self.send_event(
                SystemNotificationEvent(
                    session_id=session_id,
                    message=f"Deployment live at {deployment_url}",
                    content={
                        "message": f"Deployment live at {deployment_url}",
                        "deployment_url": deployment_url,
                        "project_id": service_name,
                        "project_name": project_name,
                        "deployment": {
                            "url": deployment_url,
                            "cloud_run_url": deployment_url,
                            "project_id": service_name,
                            "project_name": project_name,
                            "provider": "cloud_run",
                            "deployment_id": str(deployment_id) if deployment_id else None,
                            "version": 1,
                        },
                    },
                )
            )

        except Exception as exc:
            logger.exception("Failed to deploy to Cloud Run")
            # Update deployment with failure and persist available metadata
            if deployment_id:
                # Save config metadata even on unexpected failure
                try:
                    metadata = self._build_metadata(service_name, result=None)
                    async with get_db_session_local() as db:
                        await container.deployments_service.update_deployment_metadata(
                            db,
                            deployment_id=deployment_id,
                            metadata=metadata,
                        )
                except Exception:
                    pass  # Best effort metadata save

                async with get_db_session_local() as db:
                    await container.deployments_service.update_deployment_status(
                        db,
                        deployment_id=deployment_id,
                        status="failed",
                        error_message=str(exc),
                        error_phase="deploy",
                        error_details={
                            "code": "UNEXPECTED_ERROR",
                            "message": str(exc),
                        },
                    )
            await self._send_error_event(
                session_id,
                error_code=ErrorCode.DEPLOY_FAILED,
                message=f"Deployment failed: {str(exc)}",
            )

    async def _get_sandbox(self, session_info: SessionInfo, container: Any) -> Sandbox | None:
        """Get sandbox instance for the session.

        Args:
            session_info: Session information
            container: ApplicationContainer instance

        Returns:
            Sandbox instance or None if not found
        """
        async with get_db_session_local() as db:
            return await container.sandbox_service.get_sandbox_for_session(
                db,
                session_id=session_info.id,
            )

    async def _download_source_from_sandbox(
        self,
        sandbox: Sandbox,
        project_path: str,
        project_name: str,
    ) -> bytes | None:
        """Download source code from sandbox as a tar.gz archive.

        Args:
            sandbox: Sandbox instance
            project_path: Path to the project in the sandbox
            project_name: Name of the project

        Returns:
            Tar.gz bytes or None if failed
        """
        try:
            # Normalize the project path
            if not project_path.startswith("/"):
                project_path = f"/workspace/{project_path}"

            # Create a tar.gz of the source directory, excluding node_modules etc.
            tar_path = f"/tmp/{project_name}-source.tar.gz"

            # Build exclusion patterns
            excludes = [
                "node_modules",
                ".git",
                ".next",
                "__pycache__",
                ".venv",
                "venv",
                "dist",
                "build",
                ".cache",
                "coverage",
                ".nyc_output",
                "*.pyc",
                ".DS_Store",
            ]
            exclude_args = " ".join(f"--exclude='{e}'" for e in excludes)

            # Create tar archive in sandbox
            tar_command = f"cd {project_path} && tar {exclude_args} -czf {tar_path} ."

            result = await sandbox.run_command(tar_command)
            logger.info(f"Tar command result: {result}")

            # Download the tar file
            tar_content = await sandbox.download_file(tar_path, format="bytes")

            # Cleanup tar file in sandbox
            clean_up_cmd = f"rm -f {tar_path}"
            result = await sandbox.run_command(clean_up_cmd)

            if isinstance(tar_content, bytes):
                return tar_content
            elif hasattr(tar_content, "__aiter__"):
                # Handle async iterator
                chunks = []
                async for chunk in tar_content:
                    chunks.append(chunk)
                return b"".join(chunks)
            else:
                logger.error(f"Unexpected tar content type: {type(tar_content)}")
                return None

        except Exception:
            logger.exception("Failed to download source from sandbox")
            return None

    def _resolve_project_path(
        self, project_path: str | None, session_info: SessionInfo
    ) -> str | None:
        """Resolve the project path from input or session info.

        Args:
            project_path: Provided project path
            session_info: Session information

        Returns:
            Resolved project path or None
        """
        if isinstance(project_path, str) and project_path.strip():
            project_path = project_path.strip()
        else:
            project_path = session_info.workspace_dir

        if not isinstance(project_path, str) or not project_path:
            return None

        if project_path.startswith("./"):
            project_path = project_path[2:]

        if not os.path.isabs(project_path):
            project_path = os.path.join(session_info.workspace_dir, project_path)

        return project_path.rstrip()

    def _resolve_project_name(self, provided_name: Any, project_path: str) -> str:
        """Resolve project name from input or path.

        Args:
            provided_name: User-provided project name
            project_path: Project path

        Returns:
            Sanitized project name
        """
        if isinstance(provided_name, str) and provided_name.strip():
            candidate = provided_name.strip()
        else:
            candidate = os.path.basename(project_path.rstrip(os.sep)) or "project"

        # Sanitize for Cloud Run service name requirements
        sanitized = re.sub(r"[^a-zA-Z0-9-]+", "-", candidate)
        sanitized = sanitized.strip("-").lower()

        # Ensure it starts with a letter
        if sanitized and not sanitized[0].isalpha():
            sanitized = "app-" + sanitized

        return sanitized[:50] or "project"  # Leave room for session hash

    def _build_metadata(
        self,
        service_name: str,
        result: DeploymentResult | None = None,
    ) -> dict[str, Any]:
        """Build deployment metadata from available data.

        Always includes config data. Adds result data when available,
        allowing partial metadata to be persisted even on failure.

        Args:
            service_name: The Cloud Run service name
            result: Optional publish result (may have partial data on failure)

        Returns:
            Metadata dict with available information
        """
        config = self.publisher.config

        metadata: dict[str, Any] = {
            "config": {
                "memory": config.memory if config else None,
                "cpu": config.cpu if config else None,
                "min_instances": config.min_instances if config else None,
                "max_instances": config.max_instances if config else None,
            },
            "cloud_run": {
                "service_name": service_name,
                "region": config.region if config else None,
                "project_id": config.project_id if config else None,
            },
        }

        # Add result data if available (may be partial on failure)
        if result:
            if result.source_bucket or result.source_object:
                metadata["source"] = {
                    "bucket": result.source_bucket,
                    "object": result.source_object,
                }
            if result.image_url or result.image_digest:
                metadata["image"] = {
                    "url": result.image_url,
                    "digest": result.image_digest,
                }
            if result.build_id:
                metadata["cloud_run"]["build_id"] = result.build_id

        return metadata

    def _extract_env_vars(self, content: CloudRunPublishContent) -> dict[str, str] | None:
        """Extract environment variables from content.

        Args:
            content: Command content

        Returns:
            Environment variables dict or None
        """
        env_vars: dict[str, str] = {}

        # Check for direct env_vars
        if content.env_vars is not None:
            for key, value in content.env_vars.items():
                if isinstance(key, str) and key:
                    env_vars[key] = str(value) if value is not None else ""

        # Check for environment in credentials
        if content.credentials is not None:
            env = content.credentials.get("environment")
            if isinstance(env, dict):
                for key, value in env.items():
                    if isinstance(key, str) and key:
                        env_vars[key] = str(value) if value is not None else ""

        return env_vars if env_vars else None
