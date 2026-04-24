"""Skill storage - zip and upload to e2b sandbox.

All skills are zipped before uploading to sandbox because e2b
file uploads are slow for many small files. Flow:
1. Read skill directory (local path from storage_uri)
2. Zip in memory
3. Upload single zip file to sandbox
4. Extract using unzip command in sandbox

For custom skills from GitHub:
1. Files downloaded from GitHub are zipped and uploaded to GCS
2. When activating, skill is downloaded from GCS and extracted to sandbox
"""

import io
import uuid
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from ii_agent.core.logger import logger
from ii_agent.core.storage.path_resolver import path_resolver
from ii_agent.agents.skills.builtin import BUILTIN_SKILLS_DIR

if TYPE_CHECKING:
    from ii_agent.core.storage.providers.base import StorageProvider
    from ii_agent.agents.skills.github import GitHubFile


def resolve_storage_uri(storage_uri: str) -> Path:
    """Resolve a storage URI to a local path.

    Handles:
    - builtin:{skill_name} -> resolves to BUILTIN_SKILLS_DIR/{skill_name}
    - Absolute paths -> returns as-is (for custom skills with local storage)

    Args:
        storage_uri: Storage URI (e.g., "builtin:pdf" or "/path/to/skill")

    Returns:
        Resolved local Path
    """
    if storage_uri.startswith("builtin:"):
        skill_name = storage_uri.split(":", 1)[1]
        return BUILTIN_SKILLS_DIR / skill_name
    return Path(storage_uri)


def create_skill_zip_from_dir(skill_dir: Path) -> bytes:
    """Create a zip file from a local skill directory.

    Args:
        skill_dir: Path to skill directory (must contain SKILL.md)

    Returns:
        Zip file content as bytes
    """
    if not (skill_dir / "SKILL.md").exists():
        raise ValueError(f"SKILL.md not found in {skill_dir}")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in skill_dir.rglob("*"):
            if file_path.is_file():
                arcname = file_path.relative_to(skill_dir)
                zf.write(file_path, arcname)

    buffer.seek(0)
    zip_bytes = buffer.read()
    logger.debug(f"Created zip for {skill_dir.name}: {len(zip_bytes)} bytes")
    return zip_bytes


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


async def skill_exists(
    storage_uri: str,
    storage: Optional["StorageProvider"] = None,
) -> bool:
    """Check if skill exists at storage URI.

    Handles three types of storage URIs:
    - "builtin:{name}" -> Check local codebase
    - "users/{user_id}/skills/{name}.zip" -> Check GCS (requires storage param)
    - "/absolute/path" -> Check local path (legacy)

    Args:
        storage_uri: Storage URI (e.g., "builtin:pdf", "users/user-123/skills/my-skill.zip")
        storage: GCS storage client (required for GCS-based skills)

    Returns:
        True if skill exists
    """
    if path_resolver.is_user_content(storage_uri):
        # GCS-based skill
        if storage is None:
            return False
        return await skill_exists_in_gcs(storage, storage_uri)
    else:
        # Local skill (builtin or absolute path)
        path = resolve_storage_uri(storage_uri)
        return path.exists() and path.is_dir()


async def copy_skill_to_sandbox(
    storage_uri: str,
    skill_name: str,
    sandbox,
    sandbox_base_path: str = "/workspace/.skills",
    storage: Optional["StorageProvider"] = None,
) -> str:
    """Zip skill directory and upload to sandbox, then extract.

    This is optimized for e2b - uploads single zip file instead of
    many small files, then extracts in sandbox.

    Handles three types of storage URIs:
    - "builtin:{name}" -> Load from local codebase
    - "users/{user_id}/skills/{name}.zip" -> Download from GCS (requires storage param)
    - "/absolute/path" -> Load from local path (legacy)

    Args:
        storage_uri: Storage URI (e.g., "builtin:pdf", "users/user-123/skills/my-skill.zip")
        skill_name: Name of the skill (used for sandbox directory)
        sandbox: Sandbox instance
        sandbox_base_path: Base path in sandbox for skills
        storage: GCS storage client (required for GCS-based skills)

    Returns:
        Sandbox skill directory path where skill was extracted
    """
    sandbox_skill_dir = f"{sandbox_base_path}/{skill_name}"
    # Stage the upload zip under the writable /workspace bind volume.
    # Docker put_archive() rejects writes to /tmp on hardened sandboxes
    # (read_only=True rootfs) with "container rootfs is marked read-only",
    # even though /tmp is a tmpfs mount.
    zip_path_in_sandbox = f"{sandbox_base_path}/.{skill_name}.zip"

    # Determine source and get zip content
    if storage_uri.startswith("builtin:"):
        # Built-in skill from local codebase
        skill_dir = resolve_storage_uri(storage_uri)
        zip_content = create_skill_zip_from_dir(skill_dir)
    elif path_resolver.is_user_content(storage_uri):
        # Custom skill from GCS
        if storage is None:
            raise ValueError(f"Storage client required for GCS-based skill: {storage_uri}")
        zip_content = await download_skill_zip_from_gcs(storage, storage_uri)
    else:
        # Legacy: absolute local path
        skill_dir = Path(storage_uri)
        zip_content = create_skill_zip_from_dir(skill_dir)

    # Ensure the staging directory exists before uploading the zip.
    await sandbox.run_command(f"mkdir -p {sandbox_base_path}", user="root")

    # Upload zip to sandbox
    await sandbox.write_file(zip_path_in_sandbox, zip_content)

    # Create target directory and extract
    await sandbox.run_command(f"mkdir -p {sandbox_skill_dir}", user="root")
    await sandbox.run_command(f"unzip -o {zip_path_in_sandbox} -d {sandbox_skill_dir}", user="root")

    # Fix permissions so the sandbox user can read the files
    await sandbox.run_command(f"chown -R user:user {sandbox_skill_dir}", user="root")
    await sandbox.run_command(f"chmod -R 755 {sandbox_skill_dir}", user="root")

    # Clean up zip file (owned by sandbox user via _put_file, no root needed)
    await sandbox.run_command(f"rm -f {zip_path_in_sandbox}")

    logger.debug(f"Extracted skill '{skill_name}' to {sandbox_skill_dir}")
    return sandbox_skill_dir


# ============================================================
# GCS storage utilities for custom skills
# ============================================================


async def upload_skill_to_gcs(
    storage: "StorageProvider",
    user_id: uuid.UUID,
    skill_name: str,
    files: list["GitHubFile"],
) -> str:
    """Upload skill files to GCS as a zip.

    Args:
        storage: GCS storage provider (async)
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
        storage: GCS storage provider (async)
        storage_uri: Full path in GCS (e.g., users/{user_id}/skills/{skill_name}.zip)

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
        storage: GCS storage provider (async)
        storage_uri: Full path in GCS (e.g., users/{user_id}/skills/{skill_name}.zip)

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
        storage: GCS storage provider (async)
        storage_uri: Full path in GCS (e.g., users/{user_id}/skills/{skill_name}.zip)

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
