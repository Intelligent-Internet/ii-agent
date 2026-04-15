"""Standalone media uploader for sandbox environments.

Downloads files and images from URLs and batch-uploads them to a sandbox.
This is an orchestration utility used by handlers *before* ``agent.arun()``
so the Agent class stays infrastructure-free.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, List, Optional, Sequence, Tuple

import httpx

from ii_agent.files.media import File, Image
from ii_agent.agents.sandboxes.schemas import FileUpload
from ii_agent.core.logger import logger

if TYPE_CHECKING:
    from ii_agent.agents.sandboxes.base import Sandbox


async def upload_media_to_sandbox(
    *,
    sandbox: "Sandbox",
    files: Sequence[File],
    images: Sequence[Image],
    upload_path: str,
) -> Tuple[List[File], List[Image]]:
    """Download files/images from URLs and upload them to a sandbox.

    Args:
        sandbox: Target sandbox instance.
        files: Files with ``url`` fields to download.
        images: Images with ``url`` fields to download.
        upload_path: Destination directory inside the sandbox.

    Returns:
        Tuple of (sandbox_files, sandbox_images) with paths rewritten
        to sandbox locations.  On write failure, returns ``([], images)``
        so the original image references are preserved.
    """
    if not files and not images:
        return [], []

    # ------------------------------------------------------------------
    # 1. Download all media concurrently
    # ------------------------------------------------------------------
    async def _download_file(
        client: httpx.AsyncClient, file: File
    ) -> Optional[Tuple[str, str, bytes, str]]:
        if not file.url:
            return None
        try:
            response = await client.get(file.url)
            response.raise_for_status()
            filename = file.filename or f"file_{file.id}"
            return (file.id or "", f"{upload_path}/{filename}", response.content, "file")
        except Exception as exc:
            logger.warning("Failed to download file %s: %s", file.filename, exc)
            return None

    async def _download_image(
        client: httpx.AsyncClient, image: Image, index: int
    ) -> Optional[Tuple[Image, str, bytes, str]]:
        if not image.url:
            return None
        try:
            response = await client.get(image.url)
            response.raise_for_status()
            ext = "png"
            if image.mime_type:
                ext = image.mime_type.split("/")[-1]
            elif image.format:
                ext = image.format
            filename = f"image_{index}.{ext}"
            filepath = f"{upload_path}/{filename}"
            return (image, filepath, response.content, "image")
        except Exception as exc:
            logger.warning("Failed to download image: %s", exc)
            return None

    async with httpx.AsyncClient() as client:
        file_tasks = [_download_file(client, f) for f in files]
        image_tasks = [_download_image(client, img, i) for i, img in enumerate(images)]
        results = await asyncio.gather(*file_tasks, *image_tasks)

    # ------------------------------------------------------------------
    # 2. Collect successful downloads into FileUpload batch
    # ------------------------------------------------------------------
    file_uploads: List[FileUpload] = []
    sandbox_files: List[File] = []
    sandbox_images: List[Image] = []

    for result in results:
        if not result:
            continue

        if result[3] == "file":
            file_id, file_path, content, _ = result
            file_uploads.append(FileUpload(path=file_path, content=content))
            sandbox_files.append(File(id=file_id, filepath=file_path))
        elif result[3] == "image":
            image, filepath, content, _ = result
            file_uploads.append(FileUpload(path=filepath, content=content))
            sandbox_images.append(
                Image(
                    id=image.id,
                    filepath=filepath,
                    mime_type=image.mime_type,
                    format=image.format,
                )
            )

    # ------------------------------------------------------------------
    # 3. Batch upload to sandbox
    # ------------------------------------------------------------------
    if file_uploads:
        try:
            await sandbox.write_files(file_uploads)
            logger.info(
                "Uploaded %d files and %d images to sandbox",
                len(sandbox_files),
                len(sandbox_images),
            )
        except Exception as exc:
            logger.error("Failed to batch upload files to sandbox: %s", exc)
            return [], list(images)

    return sandbox_files, sandbox_images
