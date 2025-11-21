"""Tests for LocalSession context monitoring and cliff detection in REPL."""

import importlib
import pytest

from ii_agent.cli.repl import LocalSession


def _get_context_manager():
    try:
        return importlib.import_module("ii_agent.server.chat.context_manager")
    except Exception:
        return None


def _get_performance_cliff_threshold(model_id: str):
    mod = _get_context_manager()
    if not mod:
        # fallback default
        return {"early_degradation": 30000, "moderate_cliff": 64000}
    return mod.get_performance_cliff_threshold(model_id)


class TestLocalSessionContext:
    def test_approaching_cliff_triggers_flag(self):
        session = LocalSession(".")
        session.model = "gpt-4o"

        cliffs = _get_performance_cliff_threshold(session.model)
        early = cliffs.get("early_degradation", 0)
        safety = int(early * 0.8)

        # Add user messages with tokens to approach early degradation
        # Use explicit token counts for determinism
        session.add_message("user", "a" * 10, tokens=safety - 100)
        # Ensure current tokens are under safety threshold
        assert session.total_tokens < safety

        # Now cross threshold
        session.add_message("user", "b" * 10, tokens=200)
        assert session.total_tokens >= safety
        assert session.is_approaching_cliff() is True

    def test_context_status_contains_usage_bar(self):
        session = LocalSession(".")
        session.model = "gpt-4o"
        session.add_message("user", "hi", tokens=10)
        status = session.get_context_status()
        assert "context_usage_bar" in status
        assert status["context_usage_bar"].startswith("[") and status["context_usage_bar"].endswith("]")
