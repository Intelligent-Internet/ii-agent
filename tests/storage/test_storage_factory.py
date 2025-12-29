"""Unit tests for the storage factory functions.

This module contains tests for storage provider factory functions,
ensuring correct provider instantiation based on configuration.
"""

import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock

from ii_agent.storage.factory import create_storage_client
from ii_agent.storage.local import LocalStorage
from ii_agent.storage.gcs import GCS


class TestStorageFactory:
    """Tests for create_storage_client factory function."""

    def test_create_local_storage(self):
        """Test that local provider creates LocalStorage instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {
                "LOCAL_STORAGE_PATH": tmpdir,
                "LOCAL_STORAGE_URL_BASE": "/files",
            }):
                storage = create_storage_client("local")

                assert isinstance(storage, LocalStorage)
                assert storage.base_path == os.path.abspath(tmpdir)

    def test_create_local_storage_with_internal_url(self):
        """Test local storage with internal URL configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {
                "LOCAL_STORAGE_PATH": tmpdir,
                "LOCAL_STORAGE_URL_BASE": "http://localhost:8000/files",
                "LOCAL_STORAGE_INTERNAL_URL_BASE": "http://backend:8000/files",
            }):
                storage = create_storage_client("local")

                assert isinstance(storage, LocalStorage)
                assert storage.internal_url_base == "http://backend:8000/files"

    def test_create_gcs_storage(self):
        """Test that gcs provider creates GCS instance."""
        with patch("ii_agent.storage.gcs.storage") as mock_storage:
            mock_client = MagicMock()
            mock_storage.Client.return_value = mock_client

            storage = create_storage_client(
                "gcs",
                project_id="test-project",
                bucket_name="test-bucket",
            )

            assert isinstance(storage, GCS)

    def test_create_gcs_without_project_id_raises(self):
        """Test that GCS without project_id raises ValueError."""
        with pytest.raises(ValueError, match="GCS storage requires project_id"):
            create_storage_client(
                "gcs",
                bucket_name="test-bucket",
            )

    def test_create_gcs_without_bucket_name_raises(self):
        """Test that GCS without bucket_name raises ValueError."""
        with pytest.raises(ValueError, match="GCS storage requires project_id"):
            create_storage_client(
                "gcs",
                project_id="test-project",
            )

    def test_unsupported_provider_raises(self):
        """Test that unsupported provider raises ValueError."""
        with pytest.raises(ValueError, match="not supported"):
            create_storage_client("unsupported_provider")

    def test_local_storage_uses_default_path(self):
        """Test that local storage uses default path when env not set."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            default_path = os.path.join(tmpdir, ".ii_agent")
            url_base = "http://localhost:8000/files"
            with patch.dict(os.environ, {
                "LOCAL_STORAGE_PATH": default_path,
                "LOCAL_STORAGE_URL_BASE": url_base,
            }, clear=False):
                storage = create_storage_client("local")

            assert isinstance(storage, LocalStorage)
            assert storage.serve_url_base == url_base
