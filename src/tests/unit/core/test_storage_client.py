"""Tests for ii_agent.core.storage.client — _create_storage, get_storage, set_storage, reset_storage."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestStorageClient:
    def setup_method(self):
        from ii_agent.core.storage import client as sc

        sc._storage = None

    def teardown_method(self):
        from ii_agent.core.storage import client as sc

        sc._storage = None

    def _mock_settings(self, provider="minio", **overrides):
        s = MagicMock()
        s.provider = provider
        s.serve_base_url = overrides.get("serve_base_url", None)
        s.project_id = overrides.get("project_id", "proj")
        s.bucket_name = overrides.get("bucket_name", "bucket")
        s.custom_domain = overrides.get("custom_domain", None)
        s.minio_endpoint = "http://minio:9000"
        s.minio_access_key = "access"
        s.minio_secret_key = "secret"
        s.minio_region = "us-east-1"
        s.minio_secure = False
        s.minio_external_endpoint = None
        return s

    def test_create_storage_minio(self):
        """MinIO provider created."""
        from ii_agent.core.storage.client import _create_storage

        mock_s = self._mock_settings(provider="minio")
        with patch("ii_agent.core.storage.client.get_settings") as ms:
            ms.return_value.storage = mock_s
            with patch("ii_agent.core.storage.providers.minio.MinIOProvider") as mock_prov:
                mock_prov.return_value = MagicMock()
                _create_storage()
                mock_prov.assert_called_once()

    def test_create_storage_unknown_provider_raises(self):
        """Line 64: unknown provider raises ValueError."""
        from ii_agent.core.storage.client import _create_storage

        mock_s = self._mock_settings(provider="unknown_xyz")
        with patch("ii_agent.core.storage.client.get_settings") as ms:
            ms.return_value.storage = mock_s
            try:
                _create_storage()
                assert False, "Should have raised ValueError"
            except ValueError as e:
                assert "unknown_xyz" in str(e)

    def test_create_storage_gcs_missing_config_raises(self):
        """Lines 33-34: GCS missing required config."""
        from ii_agent.core.storage.client import _create_storage

        mock_s = self._mock_settings(provider="gcs", project_id=None)
        mock_s.project_id = None
        with patch("ii_agent.core.storage.client.get_settings") as ms:
            ms.return_value.storage = mock_s
            with patch("ii_agent.core.storage.providers.gcs.GCSProvider"):
                try:
                    _create_storage()
                    assert False, "Should raise"
                except ValueError:
                    pass

    def test_create_storage_minio_missing_bucket_raises(self):
        """Lines 44-46: MinIO missing bucket_name."""
        from ii_agent.core.storage.client import _create_storage

        mock_s = self._mock_settings(provider="minio", bucket_name=None)
        mock_s.bucket_name = None
        with patch("ii_agent.core.storage.client.get_settings") as ms:
            ms.return_value.storage = mock_s
            try:
                _create_storage()
                assert False, "Should raise"
            except ValueError:
                pass

    def test_get_storage_creates_when_none(self):
        """Lines 70-72: creates provider on first call."""
        from ii_agent.core.storage.client import get_storage

        mock_provider = MagicMock()
        with patch("ii_agent.core.storage.client._create_storage", return_value=mock_provider):
            result = get_storage()
            assert result is mock_provider

    def test_get_storage_returns_existing(self):
        """Branch: returns cached instance without calling _create_storage."""
        from ii_agent.core.storage.client import get_storage, set_storage

        mock_provider = MagicMock()
        set_storage(mock_provider)
        with patch("ii_agent.core.storage.client._create_storage") as mock_create:
            result = get_storage()
            mock_create.assert_not_called()
            assert result is mock_provider

    def test_set_storage_injects_provider(self):
        """Line 78: set_storage injects custom provider."""
        from ii_agent.core.storage.client import set_storage
        import ii_agent.core.storage.client as sc

        mock_provider = MagicMock()
        set_storage(mock_provider)
        assert sc._storage is mock_provider

    def test_reset_storage(self):
        """Line 84: reset_storage sets _storage to None."""
        from ii_agent.core.storage.client import set_storage, reset_storage
        import ii_agent.core.storage.client as sc

        set_storage(MagicMock())
        reset_storage()
        assert sc._storage is None
