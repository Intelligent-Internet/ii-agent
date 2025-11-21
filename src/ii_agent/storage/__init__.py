from .base import BaseStorage
from .hashtable import HashtableStorage
from .factory import create_storage_client
from .context_modes import ContextModeManager, ContextMode, ContextState

# Lazy imports for optional cloud dependencies
def __getattr__(name):
    if name == "GCS":
        from .gcs import GCS
        return GCS
    elif name == "MemvidStorage":
        from .memvid import MemvidStorage
        return MemvidStorage
    elif name == "CachedMemvidStorage":
        from .cached_memvid import CachedMemvidStorage
        return CachedMemvidStorage
    elif name == "DictionaryStorage":
        from .dictionary import DictionaryStorage
        return DictionaryStorage
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "BaseStorage",
    "GCS",
    "HashtableStorage",
    "DictionaryStorage",
    "MemvidStorage",
    "CachedMemvidStorage",
    "create_storage_client",
    "ContextModeManager",
    "ContextMode",
    "ContextState",
]
