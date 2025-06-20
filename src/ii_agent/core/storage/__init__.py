from ii_agent.core.storage.files import FileStore
from ii_agent.core.storage.local import LocalFileStore
from ii_agent.core.storage.memory import InMemoryFileStore


def get_file_store(
    file_store_type: str,
    file_store_path: str | None = None,
) -> FileStore:
    """Get a file store instance based on the type."""
    store: FileStore
    if file_store_type == "local":
        if file_store_path is None:
            raise ValueError("File store path is required for local file store")
        store = LocalFileStore(file_store_path)
    else:
        store = InMemoryFileStore()
    return store
