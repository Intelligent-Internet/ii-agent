#!/usr/bin/env python3
"""Upload slide image assets from sandbox containers to MinIO.

Reads the slide_contents table to find all image references with the old
/files/slides/assets/{hash}.{ext} URL pattern, identifies the matching files
inside sandbox Docker volumes (by MD5 content hash), and uploads them to
MinIO at content/slides/{hash}.{ext}.

Usage:
    python3 scripts/local/upload_slide_assets.py
"""

import hashlib
import subprocess
import tempfile

import boto3
import psycopg2
from botocore.config import Config

# ── Config ────────────────────────────────────────────────────────────────

DB_HOST = "localhost"
DB_PORT = 5433
DB_USER = "iiagent"
DB_PASS = "iiagent"
DB_NAME = "iiagentdev"

MINIO_ENDPOINT = "http://localhost:9000"
MINIO_ACCESS_KEY = "minioadmin"
MINIO_SECRET_KEY = "minioadmin"
MINIO_BUCKET = "ii-agent"

# ── Helpers ───────────────────────────────────────────────────────────────


def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )


def object_exists(s3, bucket: str, key: str) -> bool:
    try:
        s3.head_object(Bucket=bucket, Key=key)
        return True
    except s3.exceptions.ClientError:
        return False


def docker_cp_file(container_name: str, container_path: str, local_path: str) -> bool:
    """Copy a file from a Docker container to local filesystem."""
    result = subprocess.run(
        ["docker", "cp", f"{container_name}:{container_path}", local_path],
        capture_output=True,
    )
    return result.returncode == 0


def md5_of_file(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


# ── Main ──────────────────────────────────────────────────────────────────


def main():
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASS, dbname=DB_NAME
    )
    s3 = get_s3_client()

    # 1. Find sandbox container mappings
    cur = conn.cursor()
    cur.execute("""
        SELECT s.session_id, s.provider_sandbox_id
        FROM agent_sandboxes s
    """)
    sandbox_map = {}  # session_id -> container_id
    for session_id, container_id in cur.fetchall():
        sandbox_map[str(session_id)] = container_id
    print(f"Found {len(sandbox_map)} sandbox mappings")

    # 2. Get container name from container ID
    container_names = {}
    for session_id, container_id in sandbox_map.items():
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.Name}}", container_id[:12]],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            name = result.stdout.strip().lstrip("/")
            container_names[session_id] = name
            # Also check if container is running
            status_result = subprocess.run(
                ["docker", "inspect", "--format", "{{.State.Status}}", container_id[:12]],
                capture_output=True,
                text=True,
            )
            status = status_result.stdout.strip() if status_result.returncode == 0 else "unknown"
            print(f"  Session {session_id[:8]}: container={name}, status={status}")
    print()

    # 3. Find all image hashes referenced in slide_contents
    cur.execute("""
        SELECT DISTINCT
            sc.session_id,
            (regexp_matches(sc.slide_content, '/files/slides/assets/([a-f0-9]+)\\.([a-zA-Z]+)', 'g'))[1] as hash,
            (regexp_matches(sc.slide_content, '/files/slides/assets/([a-f0-9]+)\\.([a-zA-Z]+)', 'g'))[2] as ext
        FROM slide_contents sc
        WHERE sc.slide_content LIKE '%/files/slides/assets/%'
    """)
    needed = []
    for session_id, content_hash, ext in cur.fetchall():
        needed.append((str(session_id), content_hash, ext))
    print(f"Found {len(needed)} image hash references in slide_contents")

    # Deduplicate by hash
    unique_hashes = {}
    for session_id, content_hash, ext in needed:
        key = f"{content_hash}.{ext}"
        if key not in unique_hashes:
            unique_hashes[key] = session_id
    print(f"  Unique hashes: {len(unique_hashes)}")

    # 4. For each hash, find matching file in sandbox and upload to MinIO
    uploaded = 0
    skipped = 0
    failed = 0

    for filename, session_id in unique_hashes.items():
        content_hash = filename.rsplit(".", 1)[0]
        storage_key = f"content/slides/{filename}"

        # Check if already in MinIO
        if object_exists(s3, MINIO_BUCKET, storage_key):
            print(f"  SKIP {filename} (already in MinIO)")
            skipped += 1
            continue

        container_name = container_names.get(session_id)
        if not container_name:
            print(f"  FAIL {filename} (no container for session {session_id[:8]})")
            failed += 1
            continue

        # List all image files in the sandbox and find the one with matching MD5
        result = subprocess.run(
            [
                "docker",
                "exec",
                container_name,
                "sh",
                "-c",
                "find /workspace -type f \\( -name '*.png' -o -name '*.jpg' -o -name '*.jpeg' -o -name '*.gif' -o -name '*.webp' -o -name '*.PNG' -o -name '*.JPG' \\) 2>/dev/null",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"  FAIL {filename} (cannot list files in {container_name})")
            failed += 1
            continue

        image_files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]

        found = False
        for img_path in image_files:
            # Get MD5 of file inside container
            md5_result = subprocess.run(
                ["docker", "exec", container_name, "md5sum", img_path],
                capture_output=True,
                text=True,
            )
            if md5_result.returncode != 0:
                continue
            file_hash = md5_result.stdout.strip().split()[0]

            if file_hash == content_hash:
                # Found the matching file — copy out and upload
                with tempfile.NamedTemporaryFile(suffix=f".{filename.rsplit('.', 1)[1]}") as tmp:
                    if docker_cp_file(container_name, img_path, tmp.name):
                        # Verify MD5
                        local_hash = md5_of_file(tmp.name)
                        if local_hash != content_hash:
                            print(f"  FAIL {filename} (MD5 mismatch after copy)")
                            failed += 1
                            found = True
                            break

                        # Determine content type
                        ext = filename.rsplit(".", 1)[1].lower()
                        content_type = {
                            "png": "image/png",
                            "jpg": "image/jpeg",
                            "jpeg": "image/jpeg",
                            "gif": "image/gif",
                            "webp": "image/webp",
                        }.get(ext, "application/octet-stream")

                        # Upload to MinIO
                        s3.upload_file(
                            tmp.name,
                            MINIO_BUCKET,
                            storage_key,
                            ExtraArgs={"ContentType": content_type},
                        )
                        print(f"  OK   {filename} <- {img_path}")
                        uploaded += 1
                        found = True
                        break
                    else:
                        print(f"  FAIL {filename} (docker cp failed for {img_path})")

        if not found:
            print(f"  FAIL {filename} (no matching file found in sandbox)")
            failed += 1

    print(f"\nDone: {uploaded} uploaded, {skipped} skipped, {failed} failed")
    conn.close()


if __name__ == "__main__":
    main()
