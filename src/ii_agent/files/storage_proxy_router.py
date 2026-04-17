"""Storage proxy endpoints for local deployments.

When ``STORAGE_SERVE_BASE_URL`` is configured, file uploads and downloads
are routed through the backend instead of directly to the storage provider
(e.g. MinIO).  This keeps the object store internal to the Docker network
while the backend — already exposed on the LAN — acts as the single point
of access.

Download paths contain random UUIDs, providing path-obscurity auth
consistent with the ``slide_assets_router`` pattern.
"""

from __future__ import annotations

import io
import mimetypes
import re
import uuid

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from ii_agent.core.dependencies import DBSession
from ii_agent.core.storage.client import get_storage
from ii_agent.core.storage.exceptions import StorageObjectNotFoundError
from ii_agent.files.dependencies import FileRepositoryDep
from ii_agent.files.types import UploadStatus

router = APIRouter(prefix="/storage", tags=["Storage Proxy"])

# Only allow safe path characters (alnum, dashes, underscores, dots, slashes).
# Reject ".." segments to prevent path traversal.
_SAFE_PATH = re.compile(r"^(?!.*\.\.)[\w./-]+$")
_MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100 MB


@router.get("/d/{path:path}")
async def proxy_download(path: str) -> StreamingResponse:
    """Stream a file from internal storage to the browser.

    The storage path contains random UUIDs making it unguessable —
    no additional auth is required (same model as presigned URLs).
    """
    if not path or not _SAFE_PATH.match(path):
        raise HTTPException(status_code=400, detail="Invalid path")

    storage = get_storage()
    try:
        data = await storage.read(path)
    except StorageObjectNotFoundError:
        raise HTTPException(status_code=404, detail="Not found")

    # Determine content size so the response includes Content-Length
    # instead of chunked transfer encoding (fixes PDF/media rendering
    # in clients that require a known content length).
    data.seek(0, 2)
    size = data.tell()
    data.seek(0)

    content_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
    return StreamingResponse(
        content=data,
        media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=86400",
            "Content-Length": str(size),
        },
    )


@router.put("/upload/{asset_id}")
async def proxy_upload(
    asset_id: uuid.UUID,
    request: Request,
    file_repo: FileRepositoryDep,
    db: DBSession,
) -> Response:
    """Proxy a file upload from the browser to internal storage.

    The asset must already exist in PENDING state (created by
    ``POST /v1/assets/upload``).  The asset UUID acts as a single-use
    nonce — same security model as presigned upload URLs.
    """
    asset = await file_repo.get_by_id(db, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    if asset.upload_status != UploadStatus.PENDING:
        raise HTTPException(status_code=409, detail="Asset upload already completed or failed")

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            length = int(content_length)
            if length > _MAX_UPLOAD_SIZE:
                raise HTTPException(status_code=413, detail="File too large")
        except ValueError:
            pass  # Invalid content-length header, will check body size below

    content_type = request.headers.get("content-type", "application/octet-stream")
    body = await request.body()

    if len(body) > _MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="File too large")

    storage = get_storage()
    await storage.write(asset.storage_path, io.BytesIO(body), content_type)

    # Transition asset to COMPLETE state
    asset.upload_status = UploadStatus.COMPLETE
    await db.commit()

    return Response(status_code=200)
