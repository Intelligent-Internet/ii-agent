import os
from ii_agent.storage import BaseStorage, GCS, LocalStorage


def create_storage_client(
    storage_provider: str,
    project_id: str | None = None,
    bucket_name: str | None = None,
    custom_domain: str | None = None,
) -> BaseStorage:
    if storage_provider == "local":
        base_path = os.environ.get("LOCAL_STORAGE_PATH", "/.ii_agent/storage")
        serve_url_base = os.environ.get("LOCAL_STORAGE_URL_BASE", "/files")
        internal_url_base = os.environ.get("LOCAL_STORAGE_INTERNAL_URL_BASE")
        return LocalStorage(
            base_path=base_path,
            custom_domain=custom_domain,
            serve_url_base=serve_url_base,
            internal_url_base=internal_url_base,
        )
    elif storage_provider == "gcs":
        if not project_id or not bucket_name:
            raise ValueError("GCS storage requires project_id and bucket_name")
        return GCS(
            project_id,
            bucket_name,
            custom_domain,
        )
    raise ValueError(f"Storage provider {storage_provider} not supported")
