"""Unit tests for core/config/yaml_source.py and model_configs_source.py."""

from __future__ import annotations

import tempfile

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# YamlSettingsSource
# ---------------------------------------------------------------------------


class TestYamlSettingsSource:
    def _make_source(self, yaml_path=None, env_path=None, monkeypatch=None):
        """Build a YamlSettingsSource with optional path overrides."""
        from pydantic_settings import BaseSettings

        class _DummySettings(BaseSettings):
            some_field: str = "default"

        if monkeypatch and env_path:
            monkeypatch.setenv("SETTINGS_YAML_PATH", env_path)
        elif monkeypatch:
            monkeypatch.delenv("SETTINGS_YAML_PATH", raising=False)

        from ii_agent.core.config.yaml_source import YamlSettingsSource

        return YamlSettingsSource(_DummySettings, yaml_path=yaml_path)

    def test_loads_from_explicit_path(self, tmp_path):
        yaml_file = tmp_path / "settings.yaml"
        yaml_file.write_text("some_field: explicit_value\n")

        src = self._make_source(yaml_path=str(yaml_file))
        assert src() == {"some_field": "explicit_value"}

    def test_loads_from_env_var_path(self, tmp_path, monkeypatch):
        yaml_file = tmp_path / "env_settings.yaml"
        yaml_file.write_text("database:\n  host: db.local\n")

        src = self._make_source(env_path=str(yaml_file), monkeypatch=monkeypatch)
        result = src()
        assert result["database"]["host"] == "db.local"

    def test_returns_empty_when_no_file_found(self, monkeypatch):
        monkeypatch.chdir(tempfile.mkdtemp())  # no settings.yaml here
        src = self._make_source(monkeypatch=monkeypatch)
        assert src() == {}

    def test_get_field_value_returns_value_when_present(self, tmp_path):
        yaml_file = tmp_path / "settings.yaml"
        yaml_file.write_text("some_field: hello\n")

        src = self._make_source(yaml_path=str(yaml_file))
        val, name, present = src.get_field_value(None, "some_field")
        assert val == "hello"
        assert name == "some_field"
        assert present is True

    def test_get_field_value_returns_none_when_absent(self, tmp_path):
        yaml_file = tmp_path / "settings.yaml"
        yaml_file.write_text("other: value\n")

        src = self._make_source(yaml_path=str(yaml_file))
        val, name, present = src.get_field_value(None, "some_field")
        assert val is None
        assert present is False

    def test_explicit_path_takes_priority_over_env(self, tmp_path, monkeypatch):
        explicit_file = tmp_path / "explicit.yaml"
        explicit_file.write_text("source: explicit\n")

        env_file = tmp_path / "env.yaml"
        env_file.write_text("source: env\n")

        src = self._make_source(
            yaml_path=str(explicit_file),
            env_path=str(env_file),
            monkeypatch=monkeypatch,
        )
        assert src()["source"] == "explicit"


# ---------------------------------------------------------------------------
# ModelConfigsYamlSource
# ---------------------------------------------------------------------------


class TestModelConfigsYamlSource:
    def _make_source(self, env_file=None, monkeypatch=None):
        from pydantic_settings import BaseSettings

        class _DummySettings(BaseSettings):
            model_configs: list = []

        if monkeypatch and env_file:
            monkeypatch.setenv("MODEL_CONFIGS_FILE", env_file)
        elif monkeypatch:
            monkeypatch.delenv("MODEL_CONFIGS_FILE", raising=False)

        from ii_agent.core.config.model_configs_source import ModelConfigsYamlSource

        return ModelConfigsYamlSource(_DummySettings)

    def test_loads_model_configs_list(self, tmp_path, monkeypatch):
        yaml_file = tmp_path / "models.yaml"
        yaml_file.write_text(
            "- model_id: gpt-4\n  provider: openai\n- model_id: claude-3\n  provider: anthropic\n"
        )

        src = self._make_source(env_file=str(yaml_file), monkeypatch=monkeypatch)
        result = src()
        assert "model_configs" in result
        assert len(result["model_configs"]) == 2
        assert result["model_configs"][0]["model_id"] == "gpt-4"

    def test_returns_empty_when_no_env_var(self, monkeypatch):
        src = self._make_source(monkeypatch=monkeypatch)
        assert src() == {}

    def test_returns_empty_when_file_missing(self, monkeypatch):
        monkeypatch.setenv("MODEL_CONFIGS_FILE", "/nonexistent/path.yaml")
        src = self._make_source(env_file="/nonexistent/path.yaml", monkeypatch=monkeypatch)
        assert src() == {}

    def test_returns_empty_when_yaml_is_not_list(self, tmp_path, monkeypatch):
        yaml_file = tmp_path / "models.yaml"
        yaml_file.write_text("key: value\n")

        src = self._make_source(env_file=str(yaml_file), monkeypatch=monkeypatch)
        assert src() == {}

    def test_get_field_value_for_model_configs(self, tmp_path, monkeypatch):
        yaml_file = tmp_path / "models.yaml"
        yaml_file.write_text("- model_id: test\n")

        src = self._make_source(env_file=str(yaml_file), monkeypatch=monkeypatch)
        val, name, present = src.get_field_value(None, "model_configs")
        assert present is True
        assert val == [{"model_id": "test"}]

    def test_get_field_value_for_other_field(self, tmp_path, monkeypatch):
        yaml_file = tmp_path / "models.yaml"
        yaml_file.write_text("- model_id: test\n")

        src = self._make_source(env_file=str(yaml_file), monkeypatch=monkeypatch)
        val, name, present = src.get_field_value(None, "other_field")
        assert present is False
        assert val is None
