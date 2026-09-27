"""TTL-bounded in-memory task store for the A2A adapter.

Replaces the unbounded ``_TASK_STORE: dict`` in ``adapter_server.py`` with a
store that:

* Automatically evicts entries older than *ttl_seconds* (default 3 600 s / 1 h).
* Caps total capacity at *maxsize* entries (default 10 000), evicting the
  oldest entries first when the cap is reached.
* Is thread-safe via a plain ``threading.Lock`` (the adapter runs in a single
  asyncio event-loop thread; the lock prevents issues if a background thread
  ever touches the store).

The store is intentionally minimal — a thin wrapper over an ``OrderedDict`` so
insertion-order is preserved and oldest-first eviction is O(1).

Persistence to Redis / PostgreSQL is deferred; this class provides the same
dict-compatible interface (``__getitem__``, ``__setitem__``, ``get``,
``pop``, ``__contains__``, ``items``) so the adapter can swap in a real
backend later without touching endpoint code.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any, Dict, Iterator, Optional, Tuple


class TaskStore:
    """LRU task store with per-entry TTL expiry.

    Parameters
    ----------
    ttl_seconds:
        Seconds before an entry is considered expired and silently dropped on
        next read.  Pass ``0`` to disable expiry (entries live until evicted
        by capacity).
    maxsize:
        Maximum number of live entries.  When the store is full the oldest
        entry (by insertion time) is removed to make room.
    """

    def __init__(self, ttl_seconds: float = 3600.0, maxsize: int = 10_000) -> None:
        if ttl_seconds < 0:
            raise ValueError("ttl_seconds must be >= 0")
        if maxsize < 1:
            raise ValueError("maxsize must be >= 1")
        self._ttl = ttl_seconds
        self._maxsize = maxsize
        # Each entry: (task_dict, inserted_at_monotonic)
        self._data: OrderedDict[str, Tuple[Dict[str, Any], float]] = OrderedDict()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Core dict-compatible interface
    # ------------------------------------------------------------------

    def __setitem__(self, key: str, value: Dict[str, Any]) -> None:
        now = time.monotonic()
        with self._lock:
            # If already present, remove so we can re-insert at tail (latest).
            self._data.pop(key, None)
            self._data[key] = (value, now)
            # Enforce capacity — drop the oldest entry.
            while len(self._data) > self._maxsize:
                self._data.popitem(last=False)

    def __getitem__(self, key: str) -> Dict[str, Any]:
        with self._lock:
            entry = self._data.get(key)
        if entry is None:
            raise KeyError(key)
        task, inserted_at = entry
        if self._is_expired(inserted_at):
            self._remove(key)
            raise KeyError(key)
        return task

    def __contains__(self, key: object) -> bool:
        with self._lock:
            entry = self._data.get(key)  # type: ignore[arg-type]
        if entry is None:
            return False
        _, inserted_at = entry
        if self._is_expired(inserted_at):
            self._remove(key)  # type: ignore[arg-type]
            return False
        return True

    def get(self, key: str, default: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        try:
            return self[key]
        except KeyError:
            return default

    def pop(self, key: str, *args: Any) -> Any:
        with self._lock:
            entry = self._data.pop(key, None)
        if entry is None:
            if args:
                return args[0]
            raise KeyError(key)
        task, inserted_at = entry
        if self._is_expired(inserted_at):
            if args:
                return args[0]
            raise KeyError(key)
        return task

    def items(self) -> Iterator[Tuple[str, Dict[str, Any]]]:
        """Yield (key, task) pairs for all non-expired entries."""
        now = time.monotonic()
        with self._lock:
            snapshot = list(self._data.items())
        for key, (task, inserted_at) in snapshot:
            if not self._is_expired(inserted_at, now=now):
                yield key, task

    def __len__(self) -> int:
        """Return the number of stored entries (may include some expired ones)."""
        return len(self._data)

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def evict_expired(self) -> int:
        """Remove all expired entries.  Returns the number of entries removed."""
        now = time.monotonic()
        with self._lock:
            expired = [k for k, (_, ts) in self._data.items() if self._is_expired(ts, now=now)]
            for k in expired:
                self._data.pop(k, None)
        return len(expired)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _is_expired(self, inserted_at: float, *, now: Optional[float] = None) -> bool:
        if self._ttl == 0:
            return False
        t = now if now is not None else time.monotonic()
        return (t - inserted_at) > self._ttl

    def _remove(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)
