"""Tool for communicating with the end user."""

from __future__ import annotations

import json
import mimetypes
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional
from urllib.parse import urlparse
from uuid import uuid4

import httpx

from ii_agent.agents.tools.base import ToolResult
from ii_agent.agents.tools.sandbox.base import BaseSandboxTool
from ii_agent.core.logger import logger
from ii_agent.core.storage.client import get_storage
from ii_agent.core.storage.path_resolver import path_resolver

if TYPE_CHECKING:
    from ii_agent.agents.agent import IIAgent
    from ii_agent.agents.sandboxes.base import Sandbox
    from ii_agent.agents.tools.function import FunctionCall
    from ii_agent.core.storage.providers.base import StorageProvider

NAME = "send_user_files"
DISPLAY_NAME = "Sending file to user"
DESCRIPTION = "Send an attachment to the user with optional message. You must only call this tool after the files have been created, not in parallel."
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "message": {
            "type": "string",
            "description": "Short message to send to the user.",
        },
        "attachments": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "List of file paths to deliver with the message. This must be in absolute path or relative to sandbox working directory."
                "Directories must be zipped and archived before attaching."
            ),
            "default": [],
        },
    },
    "required": ["attachments"],
    "additionalProperties": False,
}


class SendUserFile(BaseSandboxTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = False

    async def execute(self, tool_input: dict[str, Any]) -> ToolResult:
        message_text = tool_input.get("message", "")
        if not isinstance(message_text, str):
            return self._error_result("`message` must be a string.")

        attachments_input = tool_input.get("attachments", [])
        if attachments_input is None:
            attachments_input = []
        if not isinstance(attachments_input, list):
            return self._error_result("`attachments` must be an array of file paths.")
        payload = {
            "tool_name": "message",
            "action": {
                "text": message_text,
                "attachments": attachments_input,
            },
        }
        payload_json = json.dumps(payload)

        return ToolResult(
            llm_content=payload_json,
            user_display_content=payload,
            is_error=False,
        )

    async def on_tool_start(self, agent: IIAgent, fc: FunctionCall) -> None:
        await super().on_tool_start(agent, fc)

    async def on_tool_end(self, agent: "IIAgent", fc: "FunctionCall") -> None:
        if fc.error:
            return

        tool_result = fc.result
        if not isinstance(tool_result, ToolResult):
            return
        if tool_result.is_error:
            return

        user_display = tool_result.user_display_content
        if not isinstance(user_display, dict):
            return

        action = user_display.get("action")
        if not isinstance(action, dict):
            return

        attachments = action.get("attachments")
        if not isinstance(attachments, list) or not attachments:
            return

        storage = _build_storage()
        if storage is None:
            return

        sandbox = getattr(agent, "sandbox", None)
        updated_attachments: list[dict[str, str]] = []
        for attachment in attachments:
            meta = await _process_attachment(
                attachment,
                session_id=getattr(agent, "session_id", None),
                sandbox=sandbox,
                storage=storage,
            )
            if meta:
                updated_attachments.append(meta)

        action["attachments"] = updated_attachments
        tool_result.user_display_content = user_display

    def _error_result(self, message: str) -> ToolResult:
        return ToolResult(
            llm_content=message,
            user_display_content=message,
            is_error=True,
        )


def _build_storage() -> Optional["StorageProvider"]:
    try:
        return get_storage()
    except Exception as exc:
        logger.warning(f"Message attachments skipped: {exc}")
        return None


async def _process_attachment(
    attachment: object,
    *,
    session_id: Optional[str],
    sandbox: Optional["Sandbox"],
    storage: "StorageProvider",
) -> Optional[dict[str, str]]:
    if isinstance(attachment, dict):
        name = attachment.get("name")
        url = attachment.get("url")
        file_type = attachment.get("file_type")
        if isinstance(url, str) and url:
            resolved_name = name if isinstance(name, str) and name else _guess_name_from_path(url)
            determined_type = (
                file_type if isinstance(file_type, str) else _determine_file_type(resolved_name)
            )
            return {
                "name": resolved_name,
                "file_type": determined_type,
                "url": url,
            }
        return None

    if not isinstance(attachment, str) or not attachment.strip():
        return None

    if _is_remote_url(attachment):
        name = _guess_name_from_path(attachment)
        return {
            "name": name,
            "file_type": _determine_file_type(name),
            "url": attachment,
        }

    if not sandbox:
        logger.warning(f"No sandbox available to fetch attachment {attachment}")
        return None

    filename = Path(attachment).name or "attachment"
    storage_path = _generate_storage_path(filename, session_id)
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

    try:
        upload_url = await storage.signed_upload_url(
            storage_path,
            content_type,
            expiry_seconds=3600,
        )
    except Exception as exc:
        logger.error(f"Failed to create signed upload URL for attachment {attachment}: {exc}")
        return None

    if not upload_url:
        logger.error(f"Failed to create signed upload URL for attachment {attachment}")
        return None

    try:
        file_bytes = await sandbox.download_file(attachment, format="bytes")
    except Exception as exc:
        logger.warning(f"Unable to download attachment {attachment} from sandbox: {exc}")
        return None

    if file_bytes is None or not isinstance(file_bytes, bytes):
        logger.warning(f"Attachment {attachment} could not be downloaded from sandbox")
        return None

    try:
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            response = await client.put(
                upload_url,
                content=file_bytes,
                headers={
                    "Content-Type": content_type,
                    "Content-Length": str(len(file_bytes)),
                },
            )
    except httpx.HTTPError as exc:
        logger.error(f"Failed to upload attachment {attachment} to signed URL: {exc}")
        return None

    if not response.is_success:
        logger.error(
            f"Failed to upload attachment {attachment} to signed URL: {response.status_code} {response.text}"
        )
        return None

    try:
        permanent_url = storage.public_url(storage_path)
        logger.info(f"Uploaded attachment {attachment} to {storage_path}")
        return {
            "name": filename,
            "file_type": _determine_file_type(filename),
            "url": permanent_url,
        }
    except Exception as exc:
        logger.error(f"Failed to finalize attachment {attachment} after upload: {exc}")
        return None


def _generate_storage_path(filename: str, session_id: Optional[str]) -> str:
    ext = os.path.splitext(filename or "attachment")[1].lstrip(".") or "bin"
    identifier = uuid4().hex
    return path_resolver.temp_file(identifier, "attachment", ext)


def _is_remote_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"}


def _guess_name_from_path(path: str) -> str:
    parsed = urlparse(path)
    candidate = parsed.path or path
    name = Path(candidate).name
    return name or "attachment"


def _determine_file_type(filename: str) -> str:
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
