"""Unit tests for ii_tool storage configuration and factory.

This module contains tests for the storage configuration model
and factory function used in tool integrations.
"""

import os
import pytest
from unittest.mock import patch, MagicMock

from ii_tool.integrations.storage.config import StorageConfig
from ii_tool.integrations.storage.factory import create_storage_client
from ii_tool.integrations.storage.local import LocalStorage
from ii_tool.integrations.storage.gcs import GCS


class TestStorageConfig:
    """Tests for StorageConfig model."""

    def test_default_provider_is_local(self):
        """Test that default storage provider is local."""
        config = StorageConfig()
        assert config.storage_provider == "local"

    def test_default_local_storage_path(self):
        """Test default local storage path."""
        config = StorageConfig()
        assert config.local_storage_path == "/.ii_agent/storage"

    def test_gcs_config_without_credentials_raises(self):
        """Test that GCS config without credentials raises error."""
        with pytest.raises(ValueError, match="gcs_bucket_name and gcs_project_id are required"):
            StorageConfig(storage_provider="gcs")

    def test_gcs_config_with_bucket_only_raises(self):
        """Test that GCS with only bucket_name raises error."""
        with pytest.raises(ValueError, match="gcs_bucket_name and gcs_project_id are required"):
            StorageConfig(
                storage_provider="gcs",
                gcs_bucket_name="my-bucket",
            )

    def test_gcs_config_with_project_only_raises(self):
        """Test that GCS with only project_id raises error."""
        with pytest.raises(ValueError, match="gcs_bucket_name and gcs_project_id are required"):
            StorageConfig(
                storage_provider="gcs",
                gcs_project_id="my-project",
            )

    def test_gcs_config_with_full_credentials_valid(self):
        """Test that GCS with full credentials is valid."""
        config = StorageConfig(
            storage_provider="gcs",
            gcs_bucket_name="my-bucket",
            gcs_project_id="my-project",
        )
        assert config.storage_provider == "gcs"
        assert config.gcs_bucket_name == "my-bucket"
        assert config.gcs_project_id == "my-project"

    def test_local_config_ignores_gcs_settings(self):
        """Test that local provider doesn't require GCS settings."""
        config = StorageConfig(
            storage_provider="local",
            local_storage_path="/custom/path",
        )
        assert config.storage_provider == "local"
        assert config.local_storage_path == "/custom/path"


class TestToolStorageFactory:
    """Tests for create_storage_client factory."""

    def test_create_local_storage(self):
        """Test creating local storage client."""
        config = StorageConfig(
            storage_provider="local",
            local_storage_path="/tmp/test-storage",
        )

        storage = create_storage_client(config)

        assert isinstance(storage, LocalStorage)

    def test_create_gcs_storage(self):
        """Test creating GCS storage client."""
        with patch("ii_tool.integrations.storage.gcs.Storage") as mock_storage:
            mock_client = MagicMock()
            mock_storage.Client.return_value = mock_client

            config = StorageConfig(
                storage_provider="gcs",
                gcs_bucket_name="test-bucket",
                gcs_project_id="test-project",
            )

            storage = create_storage_client(config)

            assert isinstance(storage, GCS)

    def test_unsupported_provider_raises(self):
        """Test that unsupported provider raises ValueError."""
        # We need to bypass validation to test the factory
        config = MagicMock()
        config.storage_provider = "unsupported"

        with pytest.raises(ValueError, match="not supported"):
            create_storage_client(config)
