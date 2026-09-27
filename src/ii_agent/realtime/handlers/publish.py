"""Handler for publishing a project."""

from __future__ import annotations

import hashlib
import os
import re
import shlex
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
from ii_agent.realtime.handlers.base import (
    BaseCommandHandler,
    CommandType,
)
from ii_agent.realtime.schemas import PublishProjectContent


class PublishProjectHandler(BaseCommandHandler[PublishProjectContent]):
    """Handler for publishing a project"""

    _SUCCESS_MARKER = "__II_PUBLISH_SUCCESS__"
    _content_type = PublishProjectContent

    def __init__(self, pubsub: AsyncIOPubSub, container: ApplicationContainer) -> None:
        super().__init__(pubsub=pubsub, container=container)

    def get_command_type(self) -> CommandType:
        return CommandType.PUBLISH_PROJECT

    async def handle(self, content: PublishProjectContent, session_info: SessionInfo) -> None:
        """Handle project deployment to Vercel inside the sandbox."""
        import time

        container = self._container
        deployment_id: uuid.UUID | None = None
        db_project_id: uuid.UUID | None = None

        project_path = self._resolve_project_path(content.project_path, session_info)
        if not project_path:
            await self._send_error_event(
                session_info.id,
                error_code=ErrorCode.MISSING_PROJECT_PATH,
            )
            return

        project_name = self._resolve_project_name(content.project_name, project_path)
        vercel_api_key = self._extract_api_key(content)
        if not vercel_api_key:
            await self._send_error_event(
                session_info.id,
                error_code=ErrorCode.MISSING_CREDENTIALS,
                message="Vercel API key is required for deployment.",
            )
            return

        session_id = session_info.id
        session_id_hash = hashlib.sha256(str(session_id).encode()).hexdigest()[:8]
        vercel_project_id = f"{project_name}-ii-{session_id_hash}"
        shell_session_name = f"deploy-{session_id_hash}"
        workspace_project_path = f"/workspace/{project_name}"

        # Get or create project record and deployment
        try:
            async with get_db_session_local() as db:
                project = await container.project_service.get_session_project_or_none(
                    db,
                    session_id=session_id,
                    user_id=session_info.user_id,
                )
                db_project_id = project.id if project else None

                if db_project_id:
                    deployment_record = await container.deployments_service.create_deployment(
                        db,
                        project_id=db_project_id,
                        user_id=session_info.user_id,
                        provider="vercel",
                        environment="production",
                        source_path=project_path,
                    )
                    deployment_id = deployment_record.id
                    logger.info(
                        f"Created Vercel deployment record {deployment_id} for project {db_project_id} (v{deployment_record.version})"
                    )
        except Exception as exc:
            logger.warning(f"Failed to create deployment record: {exc}")

        deploy_start = time.time()

        try:
            async with get_db_session_local() as db:
                sandbox = await container.sandbox_service.get_sandbox_for_session(
                    db,
                    session_id=session_id,
                )
        except Exception as exc:
            logger.warning(f"Failed to connect to sandbox for publish session {session_id}: {exc}")
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

        if sandbox is None:
            if deployment_id:
                async with get_db_session_local() as db:
                    await container.deployments_service.update_deployment_status(
                        db,
                        deployment_id=deployment_id,
                        status="failed",
                        error_message="No sandbox found for session",
                        error_phase="upload",
                        error_details={"code": "SANDBOX_NOT_FOUND"},
                    )
            await self._send_error_event(
                session_id,
                error_code=ErrorCode.SANDBOX_CONNECTION_FAILED,
                message="No active sandbox is available for this session.",
            )
            return

        await self._ensure_shell_session(
            session_id,
            shell_session_name,
            workspace_project_path,
        )

        await self.send_event(
            AgentStatusUpdateEvent(
                session_id=session_id,
                message=f"Linking {vercel_project_id} with Vercel...",
                status="linking",
                content={"message": f"Linking {vercel_project_id} with Vercel..."},
            )
        )

        # Update status to building
        if deployment_id:
            async with get_db_session_local() as db:
                await container.deployments_service.update_deployment_status(
                    db,
                    deployment_id=deployment_id,
                    status="building",
                )

        link_command = self._append_success_marker(
            f"cd {self._shell_quote(workspace_project_path)} && "
            "rm -rf .vercel && "
            f"vercel link --yes --project {self._shell_quote(vercel_project_id)} --token {self._shell_quote(vercel_api_key)}"
        )

        try:
            link_output = await self._run_shell_command(
                session_id,
                shell_session_name,
                link_command,
                description="Link Vercel project",
                timeout=179,
            )
        except Exception as exc:  # noqa: BLE001
            if deployment_id:
                async with get_db_session_local() as db:
                    await container.deployments_service.update_deployment_status(
                        db,
                        deployment_id=deployment_id,
                        status="failed",
                        error_message=f"Failed to link project with Vercel: {exc}",
                        error_phase="deploy",
                        error_details={
                            "code": "VERCEL_LINK_FAILED",
                            "message": str(exc),
                        },
                    )
            await self._send_error_event(
                session_id,
                error_code=ErrorCode.DEPLOY_LINK_FAILED,
                message=f"Failed to link project with Vercel.\nDetails: {exc}",
            )
            return

        if not self._command_succeeded(link_output):
            if deployment_id:
                async with get_db_session_local() as db:
                    await container.deployments_service.update_deployment_status(
                        db,
                        deployment_id=deployment_id,
                        status="failed",
                        error_message="Failed to link project with Vercel",
                        error_phase="deploy",
                        error_details={
                            "code": "VERCEL_LINK_FAILED",
                            "output": self._cleanup_output_for_display(link_output),
                        },
                    )
            await self._send_error_event(
                session_id,
                error_code=ErrorCode.DEPLOY_LINK_FAILED,
                message=(
                    "Failed to link project with Vercel.\n"
                    f"Output: {self._cleanup_output_for_display(link_output) or 'No output returned.'}"
                ),
            )
            return

        await self.send_event(
            AgentStatusUpdateEvent(
                session_id=session_id,
                message="Project linked successfully.",
                status="linked",
                content={"message": "Project linked successfully."},
            )
        )

        await self.send_event(
            AgentStatusUpdateEvent(
                session_id=session_id,
                message="Running production deployment...",
                status="deploying",
                content={"message": "Running production deployment..."},
            )
        )

        # Update status to deploying
        if deployment_id:
            async with get_db_session_local() as db:
                await container.deployments_service.update_deployment_status(
                    db,
                    deployment_id=deployment_id,
                    status="deploying",
                )

        deploy_command = (
            f"cd {self._shell_quote(workspace_project_path)} && "
            f"vercel --prod --token {self._shell_quote(vercel_api_key)} -y"
        )
        deploy_command = self._append_success_marker(deploy_command)

        try:
            deploy_output = await self._run_shell_command(
                session_id,
                shell_session_name,
                deploy_command,
                description="Deploy project to Vercel",
                timeout=179,
            )
        except Exception as exc:  # noqa: BLE001
            if deployment_id:
                async with get_db_session_local() as db:
                    await container.deployments_service.update_deployment_status(
                        db,
                        deployment_id=deployment_id,
                        status="failed",
                        error_message=f"Vercel deployment failed: {exc}",
                        error_phase="deploy",
                        error_details={
                            "code": "VERCEL_DEPLOY_FAILED",
                            "message": str(exc),
                        },
                    )
            await self._send_error_event(
                session_id,
                error_code=ErrorCode.DEPLOY_FAILED,
                message=f"Vercel deployment failed.\nDetails: {exc}",
            )
            return

        if not self._command_succeeded(deploy_output):
            if deployment_id:
                async with get_db_session_local() as db:
                    await container.deployments_service.update_deployment_status(
                        db,
                        deployment_id=deployment_id,
                        status="failed",
                        error_message="Vercel deployment failed",
                        error_phase="deploy",
                        error_details={
                            "code": "VERCEL_DEPLOY_FAILED",
                            "output": self._cleanup_output_for_display(deploy_output),
                        },
                    )
            await self._send_error_event(
                session_id,
                error_code=ErrorCode.DEPLOY_FAILED,
                message=(
                    "Vercel deployment failed.\n"
                    f"Output: {self._cleanup_output_for_display(deploy_output) or 'No output returned.'}"
                ),
            )
            return

        cleaned_output = self._cleanup_output(deploy_output)
        deployment_url = self._extract_deployment_url(cleaned_output, vercel_project_id)

        deploy_duration_ms = int((time.time() - deploy_start) * 1000)

        # Update deployment record with success
        if deployment_id:
            # Build Vercel-specific metadata
            metadata = {
                "vercel": {
                    "project_id": vercel_project_id,
                    "deployment_output": self._cleanup_output_for_display(cleaned_output)[
                        :1000
                    ],  # Truncate
                },
            }

            async with get_db_session_local() as db:
                await container.deployments_service.update_deployment_status(
                    db,
                    deployment_id=deployment_id,
                    status="deployed",
                    deployment_url=deployment_url,
                )
                await container.deployments_service.update_deployment_metadata(
                    db,
                    deployment_id=deployment_id,
                    metadata=metadata,
                    build_duration_ms=deploy_duration_ms,
                )

                # Set as active deployment
                if db_project_id:
                    await container.deployments_service.set_active_deployment(
                        db,
                        project_id=db_project_id,
                        deployment_id=deployment_id,
                    )

        try:
            async with get_db_session_local() as db:
                await container.project_service.update_session_project_production_url(
                    db,
                    session_id=session_id,
                    user_id=session_info.user_id,
                    production_url=deployment_url,
                )
        except Exception as exc:  # noqa: BLE001 - best effort and log only
            logger.warning(f"Failed to persist deployment URL for session {session_id}: {exc}")

        await self.send_event(
            SystemNotificationEvent(
                session_id=session_id,
                message=f"Deployment live at {deployment_url}",
                content={
                    "message": f"Deployment live at {deployment_url}",
                    "deployment_url": deployment_url,
                    "project_id": vercel_project_id,
                    "project_name": project_name,
                    "deployment": {
                        "url": deployment_url,
                        "project_id": vercel_project_id,
                        "project_name": project_name,
                        "provider": "vercel",
                        "deployment_id": str(deployment_id) if deployment_id else None,
                        "version": 1,
                    },
                },
            )
        )

    def _resolve_project_path(
        self, project_path: str | None, session_info: SessionInfo
    ) -> str | None:
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

    def _extract_api_key(self, content: PublishProjectContent) -> str | None:
        if content.vercel_api_key and content.vercel_api_key.strip():
            return content.vercel_api_key.strip()

        if content.credentials:
            key_candidate = content.credentials.get("vercel_api_key")
            if isinstance(key_candidate, str) and key_candidate.strip():
                return key_candidate.strip()

        if content.token and content.token.strip():
            return content.token.strip()

        return None

    async def _collect_env_from_files(
        self,
        session_id: uuid.UUID,
        session_name: str,
        project_path: str,
    ) -> dict[str, str]:
        env_vars: dict[str, str] = {}
        base_command = f"cd {self._shell_quote(project_path)} && "
        for filename in (".env", ".env.local"):
            command = f"{base_command}if [ -f {filename} ]; then cat {filename}; fi"
            command = self._append_success_marker(command)
            try:
                output = await self._run_shell_command(
                    session_id,
                    session_name,
                    command,
                    description=f"Read {filename} environment file",
                    timeout=179,
                )
            except Exception:  # noqa: BLE001
                continue
            env_vars.update(self._parse_env_file(self._cleanup_output(output)))
        return env_vars

    def _parse_env_file(self, content: str) -> dict[str, str]:
        env_vars: dict[str, str] = {}
        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.lower().startswith("export "):
                line = line[7:].strip()
            if "=" not in line:
                continue
            name, value = line.split("=", 1)
            name = name.strip()
            if not name:
                continue
            value = value.strip()
            if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
                value = value[1:-1]
            env_vars[name] = value
        return env_vars

    def _parse_env_payload(self, env_payload: Any) -> dict[str, str]:
        env_vars: dict[str, str] = {}
        if isinstance(env_payload, dict):
            for name, value in env_payload.items():
                if isinstance(name, str) and name:
                    env_vars[name] = "" if value is None else str(value)
        elif isinstance(env_payload, list):
            for item in env_payload:
                if not isinstance(item, dict):
                    continue
                name = item.get("name")
                value = item.get("value")
                if isinstance(name, str) and name:
                    env_vars[name] = "" if value is None else str(value)
        return env_vars

    def _format_env_flags(self, env_vars: dict[str, str]) -> str:
        flags: list[str] = []
        for name, value in env_vars.items():
            combined = f"{name}={value}"
            flags.append(f"--env {self._shell_quote(combined)}")
        return " ".join(flags)

    async def _ensure_shell_session(
        self,
        session_id: uuid.UUID,
        session_name: str,
        start_directory: str,
    ) -> None:
        current_sessions = await self._container.sandbox_service.list_shell_sessions(session_id)
        if session_name in current_sessions:
            return
        await self._container.sandbox_service.create_shell_session(
            session_id,
            session_name,
            start_directory,
        )

    async def _run_shell_command(
        self,
        session_id: uuid.UUID,
        session_name: str,
        command: str,
        *,
        description: str,
        timeout: int = 600,
        wait_for_output: bool = True,
    ) -> str:
        del description
        result = await self._container.sandbox_service.run_shell_command(
            session_id,
            session_name,
            command,
            timeout=timeout,
            wait_for_output=wait_for_output,
        )
        return result.clean_output

    def _append_success_marker(self, command: str) -> str:
        return f"{command} && echo {self._SUCCESS_MARKER}"

    def _command_succeeded(self, output: str) -> bool:
        return bool(output and self._SUCCESS_MARKER in output)

    def _cleanup_output(self, output: str) -> str:
        if not output:
            return ""
        return output.replace(self._SUCCESS_MARKER, "").strip()

    def _cleanup_output_for_display(self, output: str) -> str:
        return self._redact_secrets(self._cleanup_output(output))

    def _redact_secrets(self, output: str) -> str:
        if not output:
            return ""
        output = re.sub(r"(--token\s+)(\S+)", r"\1[REDACTED]", output)
        output = re.sub(r"(--token=)(\S+)", r"\1[REDACTED]", output)
        output = re.sub(r"(VERCEL_(?:ACCESS_)?TOKEN=)(\S+)", r"\1[REDACTED]", output)
        return output

    def _extract_deployment_url(self, output: str, project_id: str) -> str:
        if output:
            production_match = re.search(r"Production:\s*(https://[^\s\]]+)", output, re.IGNORECASE)
            if production_match:
                return production_match.group(1)
            vercel_match = re.search(r"https://[^\s\]]+vercel\.app", output, re.IGNORECASE)
            if vercel_match:
                return vercel_match.group(0)
            generic_match = re.search(r"https://[^\s\]]+", output)
            if generic_match:
                return generic_match.group(0)
        return f"https://{project_id}.vercel.app"

    def _shell_quote(self, value: str) -> str:
        return shlex.quote(value)

    def _resolve_project_name(self, provided_name: Any, project_path: str) -> str:
        if isinstance(provided_name, str) and provided_name.strip():
            candidate = provided_name.strip()
        else:
            candidate = os.path.basename(project_path.rstrip(os.sep)) or "project"

        sanitized = re.sub(r"[^a-zA-Z0-9-]+", "-", candidate)
        sanitized = sanitized.strip("-")
        return sanitized.lower() or "project"
