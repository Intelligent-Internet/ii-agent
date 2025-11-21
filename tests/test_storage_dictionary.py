"""Tests for DictionaryStorage (fused hashtable + memvid) provider.

These tests validate the factory mapping and basic API presence to ensure
that the 'dictionary' provider behaves as a fused storage backend.
"""

import io
from ii_agent.storage.factory import create_storage_client


def test_factory_returns_dictionary_for_dictionary_provider():
    try:
        client = create_storage_client("dictionary", "proj-id", "bucket-name")
    except ModuleNotFoundError as e:
        # In minimal test environments memvid dependencies (qrcode, cv2, numpy) may be missing
        # We assert a meaningful message and skip the rest of the behavior tests
        assert any(dep in str(e) for dep in ("qrcode", "cv2", "numpy", "pyzbar"))
        return

    # Should provide read/write API
    assert hasattr(client, "write")
    assert hasattr(client, "read")
    assert hasattr(client, "get_permanent_url")


def test_factory_alias_hashtable_returns_dictionary():
    try:
        client_hashtable = create_storage_client("hashtable", "proj-id", "bucket-name")
        client_dictionary = create_storage_client("dictionary", "proj-id", "bucket-name")
    except ModuleNotFoundError as e:
        # Skip if memvid libs aren't present
        assert any(dep in str(e) for dep in ("qrcode", "cv2", "numpy", "pyzbar"))
        return

    # Sanity check: both should look like dictionary storage
    assert type(client_hashtable).__name__ == type(client_dictionary).__name__

def test_dictionary_get_permanent_url_scheme():
    try:
        client = create_storage_client("dictionary", "proj-id", "bucket-name")
    except ModuleNotFoundError as e:
        assert any(dep in str(e) for dep in ("qrcode", "cv2", "numpy", "pyzbar"))
        return

    url = client.get_permanent_url("/test/path/file.txt")
    # Should return memvid or dictionary scheme or a valid url string; we don't depend on specific scheme
    assert isinstance(url, str)
    assert len(url) > 0
