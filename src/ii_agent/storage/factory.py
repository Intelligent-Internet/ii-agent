from ii_agent.storage import BaseStorage
from ii_agent.storage.hashtable import HashtableStorage
from ii_agent.core.logger import logger


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
        - hashtable: Legacy name for dictionary storage (alias)
        - dictionary: Dictionary storage (fused hashtable + memvid)
        - memvid: QR video storage (dense, persistent)
        - cached_memvid: LRU cache + video backing store (fast + dense)
    """
    if storage_provider == "gcs":
        from ii_agent.storage.gcs import GCS
        return GCS(
            project_id,
            bucket_name,
            custom_domain,
        )
    elif storage_provider in ("hashtable", "dictionary"):
        if storage_provider == "hashtable":
            logger.warning("Storage provider 'hashtable' is deprecated - use 'dictionary' instead")
        # Treat 'hashtable' and 'dictionary' as the same fused storage backend.
        from ii_agent.storage.dictionary import DictionaryStorage
        return DictionaryStorage(
            project_id,
            bucket_name,
            custom_domain,
        )
    elif storage_provider == "memvid":
        from ii_agent.storage.memvid import MemvidStorage
        return MemvidStorage(
            project_id,
            bucket_name,
            custom_domain,
        )
    elif storage_provider == "cached_memvid":
        from ii_agent.storage.cached_memvid import CachedMemvidStorage
        return CachedMemvidStorage(
            project_id,
            bucket_name,
            custom_domain,
        )
    raise ValueError(f"Storage provider {storage_provider} not supported")
