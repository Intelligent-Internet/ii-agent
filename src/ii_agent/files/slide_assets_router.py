"""Slide asset serving endpoint.

Serves slide images that were uploaded to object storage by the
``SlideContentProcessor``.  The old system stored these at
``/files/slides/assets/{hash}.{ext}`` and the HTML in ``slide_contents``
still references those URLs.

This router re-creates that endpoint so existing slides render correctly.
"""

from __future__ import annotations

import re

from fastapi import APIRouter
from fastapi.responses import Response

from ii_agent.core.storage.dependencies import StorageServiceDep

router = APIRouter(prefix="/files/slides/assets", tags=["Slide Assets"])

# Only allow content-hash filenames (hex + extension) to prevent path traversal
_SAFE_FILENAME = re.compile(r"^[a-fA-F0-9]+\.[a-zA-Z]{3,4}$")

_CONTENT_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "svg": "image/svg+xml",
}


@router.get("/{filename}")
async def serve_slide_asset(
    filename: str,
    storage: StorageServiceDep,
):
    """Serve a slide image asset from object storage.

    Ignores ``token`` / ``expires`` query params (legacy signed-URL compat).
    """
    if not _SAFE_FILENAME.match(filename):
        return Response(status_code=404, content="Not found")

    storage_path = f"content/slides/{filename}"

    try:
        data = await storage.read(storage_path)
    except Exception:
        return Response(status_code=404, content="Not found")

    ext = filename.rsplit(".", 1)[-1].lower()
    content_type = _CONTENT_TYPES.get(ext, "application/octet-stream")

    return Response(
        content=data.read(),
        media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
        },
    )
