"""
Dictionary storage backend - fused dictionary (hashtable) and memvid storage.

This module exposes a `DictionaryStorage` class which combines a LRU
Hashtable in-memory cache with a Memvid QR-video backing store. This
is intended as the canonical "dictionary" storage provider - a dense,
searchable, and fast key-value storage for compact context data.
"""

from typing import Optional
from .cached_memvid import CachedMemvidStorage


class DictionaryStorage(CachedMemvidStorage):
    """Dictionary storage combining hot in-memory LRU cache and cold memvid.

    This is an alias/wrapper around `CachedMemvidStorage` to make the
    semantic name "dictionary" available in the codebase and factory.
    """

    def __init__(
        self,
        project_id: Optional[str] = None,
        bucket_name: Optional[str] = None,
        custom_domain: Optional[str] = None,
        cache_max_size: int = 10000,
    ):
        # Just delegate to CachedMemvidStorage constructor
        super().__init__(
            project_id=project_id,
            bucket_name=bucket_name,
            custom_domain=custom_domain,
            cache_max_size=cache_max_size,
        )

    # Optionally, provide a more dictionary-like URL scheme
    def get_permanent_url(self, path: str) -> str:
        """Return a permanent URL; keep memvid URL semantics.

        We keep memvid:// semantics for persisted items while exposing the
        dictionary type via the factory and module-level names.
        """
        url = super().get_permanent_url(path)
        # Provide dictionary:// alias scheme when backing store returns memvid://
        if url.startswith("memvid://"):
            return url.replace("memvid://", "dictionary://", 1)
        return url
