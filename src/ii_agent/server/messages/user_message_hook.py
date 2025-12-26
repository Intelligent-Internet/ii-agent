"""Event hook that processes message tool attachments."""

from __future__ import annotations

import logging
import anyio
import mimetypes
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
from uuid import uuid4

from ii_agent.core.event import EventType, RealtimeEvent
from ii_agent.core.event_hooks import EventHook
from ii_agent.db.manager import Files
from ii_agent.sandbox import IISandbox
from ii_agent.storage import BaseStorage


logger = logging.getLogger(__name__)


class UserMessageHook(EventHook):
    """Upload message tool attachments to object storage and replace paths with URLs."""

    def __init__(self, storage: BaseStorage, sandbox: IISandbox):
        self.storage = storage
        self.sandbox = sandbox

    def should_process(self, event: RealtimeEvent) -> bool:
        if event.type != EventType.TOOL_RESULT:
            return False

        if not self.sandbox:
            return False

        content = event.content or {}
        if content.get("tool_name") != "message_user":
            return False

        action = self._get_message_action(content.get("result"))
        if not action:
            return False

        attachments = action.get("attachments")
        return bool(attachments)

    async def process_event(self, event: RealtimeEvent) -> Optional[RealtimeEvent]:
        try:
            processed_event = RealtimeEvent(
                type=event.type,
                session_id=event.session_id,
                content=deepcopy(event.content),
            )

            action = self._get_message_action(processed_event.content.get("result"))
            if not action:
                return processed_event

            attachments = action.get("attachments")
            if not isinstance(attachments, list):
                return processed_event

            updated_attachments: list[dict[str, str]] = []
            for attachment in attachments:
                meta = await self._process_attachment(
                    attachment,
                    session_id=processed_event.session_id,
                    run_id=processed_event.run_id,
                )
                if meta:
                    updated_attachments.append(meta)

            action["attachments"] = updated_attachments
            # Persist changes back into event content
            processed_event.content["result"]["action"] = action

            return processed_event

        except Exception as exc:  # pragma: no cover - safeguard against hook failure
            logger.error("Failed to process user message hook: %s", exc, exc_info=True)
            return event

    def _get_message_action(self, result: object) -> Optional[dict]:
        if isinstance(result, dict):
            action = result.get("action")
            if isinstance(action, dict):
                return action
        return None

    async def _process_attachment(
        self,
        attachment: object,
        *,
        session_id,
        run_id,
    ) -> Optional[dict[str, str]]:
        if isinstance(attachment, dict):
            name = attachment.get("name")
            url = attachment.get("url")
            file_type = attachment.get("file_type")
            if isinstance(url, str) and url:
                resolved_name = (
                    name
                    if isinstance(name, str) and name
                    else self._guess_name_from_path(url)
                )
                determined_type = (
                    file_type
                    if isinstance(file_type, str)
                    else self._determine_file_type(resolved_name)
                )
                return {
                    "name": resolved_name,
                    "file_type": determined_type,
                    "url": url,
                }
            return None

        if not isinstance(attachment, str) or not attachment.strip():
            return None

        if self._is_remote_url(attachment):
            url = attachment
            name = self._guess_name_from_path(url)
            return {
                "name": name,
                "file_type": self._determine_file_type(name),
                "url": url,
            }

        try:
            file_bytes = await self.sandbox.download_file(
                attachment, format="bytes"
            )
        except Exception as exc:
            logger.warning(
                "Unable to fetch attachment %s from sandbox: %s",
                attachment,
                exc,
            )
            return None

        if not file_bytes:
            logger.warning("Attachment %s could not be read from sandbox", attachment)
            return None

        if not isinstance(file_bytes, (bytes, bytearray)):
            logger.warning(
                "Attachment %s returned unexpected type %s",
                attachment,
                type(file_bytes).__name__,
            )
            return None

        data = bytes(file_bytes)
        buffer = BytesIO(data)

        filename = Path(attachment).name or "attachment"
        file_id = uuid4().hex
        storage_path = self._generate_storage_path_with_id(filename, session_id, file_id)
        content_type = (
            mimetypes.guess_type(filename)[0] or "application/octet-stream"
        )

        try:
            permanent_url = await anyio.to_thread.run_sync(
                self.storage.upload_and_get_permanent_url,
                buffer,
                storage_path,
                content_type
            )
            logger.info(
                "Uploaded attachment %s to %s", attachment, storage_path
            )

            # Register file in database so it appears in "All files" tab
            if session_id:
                try:
                    await Files.create_file(
                        file_id=file_id,
                        file_name=filename,
                        file_size=len(data),
                        storage_path=storage_path,
                        content_type=content_type,
                        session_id=str(session_id),
                    )
                    logger.info(
                        "Registered attachment %s in database with id %s",
                        filename, file_id
                    )
                except Exception as db_exc:
                    # Log but don't fail - file is still accessible via URL
                    logger.warning(
                        "Failed to register attachment %s in database: %s",
                        filename, db_exc
                    )

            return {
                "name": filename,
                "file_type": self._determine_file_type(filename),
                "url": permanent_url,
            }
        except Exception as exc:
            logger.error(
                "Failed to upload attachment %s to storage: %s",
                attachment,
                exc,
            )
            return None

    def _generate_storage_path_with_id(self, filename: str, session_id, file_id: str) -> str:
        """Generate storage path using provided file_id for consistency with database."""
        safe_name = filename or "attachment"
        session_part = str(session_id) if session_id else "unknown-session"
        return (
            f"sessions/{session_part}/attachments/"
            f"{file_id}-{safe_name}"
        )

    def _generate_storage_path(self, filename: str, session_id, run_id) -> str:
        safe_name = filename or "attachment"
        identifier = uuid4().hex
        session_part = str(session_id) if session_id else "unknown-session"
        return (
            f"sessions/{session_part}/attachments/"
            f"{identifier}-{safe_name}"
        )

    def _is_remote_url(self, value: str) -> bool:
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"}

    def _guess_name_from_path(self, path: str) -> str:
        parsed = urlparse(path)
        candidate = parsed.path or path
        name = Path(candidate).name
        if name:
            return name
        return "attachment"

    def _determine_file_type(self, filename: str) -> str:
        extension = Path(filename).suffix.lower()

        code_extensions = {
            ".py",
            ".js",
            ".ts",
            ".tsx",
            ".jsx",
            ".java",
            ".rb",
            ".go",
            ".rs",
            ".c",
            ".cpp",
            ".cs",
            ".swift",
            ".kt",
            ".php",
            ".html",
            ".css",
            ".json",
            ".yaml",
            ".yml",
            ".toml",
            ".sh",
            ".md",
        }
        spreadsheet_extensions = {
            ".xls",
            ".xlsx",
            ".csv",
            ".tsv",
        }
        archive_extensions = {
            ".zip",
            ".tar",
            ".gz",
            ".tgz",
            ".bz2",
            ".xz",
            ".rar",
            ".7z",
        }

        if extension in code_extensions:
            return "code"
        if extension in spreadsheet_extensions:
            return "xlsx"
        if extension in archive_extensions:
            return "archive"

        document_extensions = {
            ".pdf",
            ".doc",
            ".docx",
            ".txt",
            ".rtf",
            ".ppt",
            ".pptx",
        }
        if extension in document_extensions:
            return "documents"

        return "documents"
