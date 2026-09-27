"""Unit tests for workers/celery_app.py broker/backend URL derivation."""

from __future__ import annotations

from unittest.mock import patch
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit


def _mock_settings(redis_url="redis://localhost:6379/0"):
    return SimpleNamespace(redis=SimpleNamespace(session_url=redis_url))


class TestGetCeleryBrokerUrl:
    def _get(self):
        from ii_agent.workers.celery_app import get_celery_broker_url

        return get_celery_broker_url()

    def test_uses_env_var_when_set(self, monkeypatch):
        monkeypatch.setenv("CELERY_BROKER_URL", "redis://custom:6379/5")
        assert self._get() == "redis://custom:6379/5"

    @patch("ii_agent.workers.celery_app.get_settings")
    def test_replaces_db0_with_db2(self, mock_settings, monkeypatch):
        monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
        mock_settings.return_value = _mock_settings("redis://host:6379/0")
        assert self._get() == "redis://host:6379/2"

    @patch("ii_agent.workers.celery_app.get_settings")
    def test_replaces_db1_with_db2(self, mock_settings, monkeypatch):
        monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
        mock_settings.return_value = _mock_settings("redis://host:6379/1")
        assert self._get() == "redis://host:6379/2"

    @patch("ii_agent.workers.celery_app.get_settings")
    def test_appends_db2_when_no_trailing_db(self, mock_settings, monkeypatch):
        monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
        mock_settings.return_value = _mock_settings("redis://host:6379")
        assert self._get() == "redis://host:6379/2"

    @patch("ii_agent.workers.celery_app.get_settings")
    def test_appends_db2_when_trailing_slash(self, mock_settings, monkeypatch):
        monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
        mock_settings.return_value = _mock_settings("redis://host:6379/")
        assert self._get() == "redis://host:6379/2"

    @patch("ii_agent.workers.celery_app.get_settings")
    def test_falls_back_to_localhost(self, mock_settings, monkeypatch):
        monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
        mock_settings.return_value = _mock_settings(redis_url=None)
        assert self._get() == "redis://localhost:6379/2"


class TestGetCeleryResultBackend:
    def _get(self):
        from ii_agent.workers.celery_app import get_celery_result_backend

        return get_celery_result_backend()

    def test_uses_env_var_when_set(self, monkeypatch):
        monkeypatch.setenv("CELERY_RESULT_BACKEND", "redis://result:6379/9")
        assert self._get() == "redis://result:6379/9"

    @patch(
        "ii_agent.workers.celery_app.get_celery_broker_url", return_value="redis://broker:6379/2"
    )
    def test_falls_back_to_broker_url(self, _mock_broker, monkeypatch):
        monkeypatch.delenv("CELERY_RESULT_BACKEND", raising=False)
        assert self._get() == "redis://broker:6379/2"
