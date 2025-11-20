"""
Cached Memvid storage - LRU hashtable cache in front of video memory.

Combines the speed of in-memory hashtable with the density of video storage.
Hot data served from RAM, cold data from compressed QR video files.
"""

from typing import BinaryIO, Optional, Dict, List, Any
from datetime import datetime
import io

from .base import BaseStorage
from .hashtable import LRUHashtable, HashtableEntry
from .memvid import MemvidStorage


class CachedMemvidStorage(BaseStorage):
    """
    Two-tier storage: LRU cache + video backing store.

    - Hot tier: In-memory LRU hashtable for fast access
    - Cold tier: Memvid QR video storage for density
    - Automatic promotion/demotion based on access patterns
    """

    def __init__(
        self,
        project_id: str,
        bucket_name: str,
        custom_domain: Optional[str] = None,
        cache_max_size: int = 10000,  # Max number of entries in cache
    ):
        # Store basic info
        self.project_id = project_id
        self.bucket_name = bucket_name
        self.custom_domain = custom_domain

        # Hot tier: LRU cache
        self.cache = LRUHashtable(max_size=cache_max_size)

        # Cold tier: Video storage
        self.memvid = MemvidStorage(project_id, bucket_name, custom_domain)

        # Cache metrics
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    def upload_file(
        self,
        file: BinaryIO,
        destination: str,
        content_type: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> str:
        """Upload to both cache and backing store."""
        # Read file content
        content = file.read()
        file.seek(0)  # Reset for memvid upload

        # Store in cold tier (memvid)
        url = self.memvid.upload_file(file, destination, content_type, metadata)

        # Cache in hot tier
        entry = HashtableEntry(
            content=content,
            content_type=content_type,
            created_at=datetime.now()
        )
        self.cache.put(destination, entry)

        return url

    def download_file(self, source: str) -> Optional[bytes]:
        """Download from cache if available, otherwise from memvid."""
        # Try hot tier first
        entry = self.cache.get(source)
        if entry:
            self.hits += 1
            return entry.content

        # Cache miss - fetch from cold tier
        self.misses += 1
        content = self.memvid.download_file(source)

        if content:
            # Promote to cache
            entry = HashtableEntry(
                content=content,
                content_type=None,  # Could extract from memvid metadata
                created_at=datetime.now()
            )
            evicted = self.cache.put(source, entry)
            if evicted:
                self.evictions += 1

        return content

    def delete_file(self, path: str) -> bool:
        """Delete from both tiers."""
        # Remove from cache
        self.cache.delete(path)

        # Remove from backing store
        return self.memvid.delete_file(path)

    def file_exists(self, path: str) -> bool:
        """Check cache first, then backing store."""
        if self.cache.get(path):
            return True
        return self.memvid.file_exists(path)

    def list_files(self, prefix: str = "") -> List[str]:
        """List files from backing store (source of truth)."""
        return self.memvid.list_files(prefix)

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        cache_stats = self.cache.get_stats()

        hit_rate = 0.0
        total_requests = self.hits + self.misses
        if total_requests > 0:
            hit_rate = (self.hits / total_requests) * 100

        return {
            'cache': cache_stats,
            'hits': self.hits,
            'misses': self.misses,
            'evictions': self.evictions,
            'hit_rate_percent': round(hit_rate, 2),
            'total_requests': total_requests,
        }

    def clear_cache(self):
        """Clear hot tier cache, keeping cold tier intact."""
        self.cache.clear()
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    # Delegate abstract methods to backing store
    def write(self, content: BinaryIO, path: str, content_type: str | None = None):
        """Write to backing store and cache."""
        result = self.memvid.write(content, path, content_type)

        # Cache the content
        content.seek(0)
        data = content.read()
        entry = HashtableEntry(
            content=data,
            content_type=content_type,
            created_at=datetime.now()
        )
        self.cache.put(path, entry)

        return result

    def read(self, path: str) -> BinaryIO:
        """Read from cache or backing store."""
        # Try cache first
        entry = self.cache.get(path)
        if entry:
            self.hits += 1
            return io.BytesIO(entry.content)

        # Cache miss
        self.misses += 1
        result = self.memvid.read(path)

        # Cache the result
        if result:
            result.seek(0)
            data = result.read()
            entry = HashtableEntry(
                content=data,
                content_type=None,
                created_at=datetime.now()
            )
            evicted = self.cache.put(path, entry)
            if evicted:
                self.evictions += 1
            result.seek(0)

        return result

    def get_download_signed_url(self, path: str, expiration_seconds: int = 3600) -> str | None:
        """Delegate to backing store."""
        return self.memvid.get_download_signed_url(path, expiration_seconds)

    def get_upload_signed_url(self, path: str, content_type: str | None = None, expiration_seconds: int = 3600) -> str | None:
        """Delegate to backing store."""
        return self.memvid.get_upload_signed_url(path, content_type, expiration_seconds)

    def is_exists(self, path: str) -> bool:
        """Check cache first, then backing store."""
        if self.cache.get(path):
            return True
        return self.memvid.is_exists(path)

    def get_file_size(self, path: str) -> int:
        """Get size from cache or backing store."""
        entry = self.cache.get(path)
        if entry:
            return entry.size
        return self.memvid.get_file_size(path)

    def get_public_url(self, path: str) -> str:
        """Delegate to backing store."""
        return self.memvid.get_public_url(path)

    def get_permanent_url(self, path: str) -> str:
        """Delegate to backing store."""
        return self.memvid.get_permanent_url(path)

    def upload_and_get_permanent_url(self, content: BinaryIO, path: str, content_type: str | None = None) -> str:
        """Upload to backing store and cache."""
        # Upload to memvid
        url = self.memvid.upload_and_get_permanent_url(content, path, content_type)

        # Cache the content
        content.seek(0)
        data = content.read()
        entry = HashtableEntry(
            content=data,
            content_type=content_type,
            created_at=datetime.now()
        )
        self.cache.put(path, entry)

        return url

    def write_from_url(self, source_url: str, destination_path: str) -> str:
        """Delegate to backing store."""
        return self.memvid.write_from_url(source_url, destination_path)
