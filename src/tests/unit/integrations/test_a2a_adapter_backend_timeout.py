"""Regression tests for ``_backend_timeout_from_env``.

Guards against the 300 s hard-coded default that was cutting off long
deep-research turns in the Copilot/Claude-Code/Codex A2A backends.
"""

from __future__ import annotations

import pytest

from ii_agent.integrations.a2a.adapter_server import _backend_timeout_from_env


pytestmark = pytest.mark.unit


class TestBackendTimeoutFromEnv:
    def test_default_when_unset(self, monkeypatch):
        monkeypatch.delenv("A2A_COPILOT_TIMEOUT", raising=False)
        assert _backend_timeout_from_env("A2A_COPILOT_TIMEOUT", 900.0) == 900.0

    def test_default_when_empty(self, monkeypatch):
        monkeypatch.setenv("A2A_COPILOT_TIMEOUT", "")
        assert _backend_timeout_from_env("A2A_COPILOT_TIMEOUT", 900.0) == 900.0

    def test_default_when_whitespace(self, monkeypatch):
        monkeypatch.setenv("A2A_COPILOT_TIMEOUT", "   ")
        assert _backend_timeout_from_env("A2A_COPILOT_TIMEOUT", 900.0) == 900.0

    def test_parses_integer(self, monkeypatch):
        monkeypatch.setenv("A2A_COPILOT_TIMEOUT", "1200")
        assert _backend_timeout_from_env("A2A_COPILOT_TIMEOUT", 900.0) == 1200.0

    def test_parses_float(self, monkeypatch):
        monkeypatch.setenv("A2A_COPILOT_TIMEOUT", "450.5")
        assert _backend_timeout_from_env("A2A_COPILOT_TIMEOUT", 900.0) == 450.5

    def test_rejects_non_numeric(self, monkeypatch):
        monkeypatch.setenv("A2A_COPILOT_TIMEOUT", "forever")
        assert _backend_timeout_from_env("A2A_COPILOT_TIMEOUT", 900.0) == 900.0

    def test_rejects_zero(self, monkeypatch):
        monkeypatch.setenv("A2A_COPILOT_TIMEOUT", "0")
        assert _backend_timeout_from_env("A2A_COPILOT_TIMEOUT", 900.0) == 900.0

    def test_rejects_negative(self, monkeypatch):
        monkeypatch.setenv("A2A_COPILOT_TIMEOUT", "-1")
        assert _backend_timeout_from_env("A2A_COPILOT_TIMEOUT", 900.0) == 900.0
