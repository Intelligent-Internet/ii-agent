"""GCS utilities for custom skill storage.

This module owns only the cloud-storage half of the skill pipeline:
  - zip/unzip helpers for GitHub-sourced skill files
  - upload / download / existence / deletion of skill zips in GCS

Sandbox-side activation (extract a skill into a running container) lives in
``ii_agent.agents.skills.storage``, which is the canonical implementation.
Functions for resolving builtin-skill paths and copying to sandbox were
previously duplicated here; they have been removed.  Import from
``ii_agent.agents.skills.storage`` instead.
"""

import io
import uuid
import zipfile
from typing import TYPE_CHECKING

from ii_agent.core.logger import logger
from ii_agent.core.storage.path_resolver import path_resolver

if TYPE_CHECKING:
    from ii_agent.core.storage.providers.base import StorageProvider
    from ii_agent.settings.skills.github import GitHubFile


# ============================================================
# GCS storage utilities for custom skills
# ============================================================


def create_skill_zip_from_files(files: list["GitHubFile"]) -> bytes:
    """Create a zip file from a list of GitHubFile objects.

    Args:
        files: List of GitHubFile objects (path, content)

    Returns:
        Zip file content as bytes
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in files:
            zf.writestr(file.path, file.content)

    buffer.seek(0)
    zip_bytes = buffer.read()
    logger.debug(f"Created zip from {len(files)} files: {len(zip_bytes)} bytes")
    return zip_bytes


async def upload_skill_to_gcs(
    storage: "StorageProvider",
    user_id: uuid.UUID,
    skill_name: str,
    files: list["GitHubFile"],
) -> str:
    """Upload skill files to GCS as a zip.

    Args:
        storage: GCS storage client
        user_id: User ID
        skill_name: Skill name (kebab-case)
        files: List of GitHubFile objects to upload

    Returns:
        Storage path where skill was uploaded (e.g., users/{user_id}/skills/{skill_name}.zip)
    """
    zip_path = path_resolver.user_skill(user_id, skill_name)

    # Create zip from files (CPU-bound, fast in memory)
    zip_content = create_skill_zip_from_files(files)

    try:
        await storage.write(zip_path, io.BytesIO(zip_content), "application/zip")
    except Exception as e:
        logger.error(f"Failed to upload skill to GCS: {e}")
        raise

    logger.info(f"Uploaded skill '{skill_name}' to GCS ({len(zip_content)} bytes)")

    return zip_path


async def download_skill_zip_from_gcs(
    storage: "StorageProvider",
    storage_uri: str,
) -> bytes:
    """Download skill zip from GCS.

    Args:
        storage: GCS storage client
        storage_uri: Full storage path (e.g., users/{user_id}/skills/{skill_name}.zip)

    Returns:
        Zip file content as bytes
    """
    try:
        data = await storage.read(storage_uri)
        return data.read()
    except Exception as e:
        logger.error(f"Failed to download skill from GCS: {e}")
        raise


async def skill_exists_in_gcs(
    storage: "StorageProvider",
    storage_uri: str,
) -> bool:
    """Check if skill zip exists in GCS.

    Args:
        storage: GCS storage client
        storage_uri: Full storage path (e.g., users/{user_id}/skills/{skill_name}.zip)

    Returns:
        True if skill zip exists
    """
    return await storage.exists(storage_uri)


async def delete_skill_from_gcs(
    storage: "StorageProvider",
    storage_uri: str,
) -> bool:
    """Delete skill zip from GCS.

    Args:
        storage: GCS storage client
        storage_uri: Full storage path (e.g., users/{user_id}/skills/{skill_name}.zip)

    Returns:
        True if deletion was successful
    """
    try:
        await storage.delete(storage_uri)
        logger.info(f"Deleted skill from GCS: {storage_uri}")
        return True
    except Exception as e:
        logger.error(f"Failed to delete skill from GCS: {e}")
        return False
