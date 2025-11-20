from ii_agent.storage import BaseStorage, GCS
from ii_agent.storage.hashtable import HashtableStorage
from ii_agent.storage.memvid import MemvidStorage
from ii_agent.storage.cached_memvid import CachedMemvidStorage


def create_storage_client(
    storage_provider: str,
    project_id: str,
    bucket_name: str,
    custom_domain: str | None = None,
) -> BaseStorage:
    """
    Create a storage client based on the provider type.

    Supported providers:
        - gcs: Google Cloud Storage (persistent, networked)
        - hashtable: Pure LRU in-memory cache (fast, volatile)
        - memvid: QR video storage (dense, persistent)
        - cached_memvid: LRU cache + video backing store (fast + dense)
    """
    if storage_provider == "gcs":
        return GCS(
            project_id,
            bucket_name,
            custom_domain,
        )
    elif storage_provider == "hashtable":
        return HashtableStorage(
            project_id,
            bucket_name,
            custom_domain,
        )
    elif storage_provider == "memvid":
        return MemvidStorage(
            project_id,
            bucket_name,
            custom_domain,
        )
    elif storage_provider == "cached_memvid":
        return CachedMemvidStorage(
            project_id,
            bucket_name,
            custom_domain,
        )
    raise ValueError(f"Storage provider {storage_provider} not supported")
