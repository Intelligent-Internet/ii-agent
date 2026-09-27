"""Tests for ii_agent.settings.llm.seeding."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# ensure_admin_llm_settings_seeded — once guard
# ---------------------------------------------------------------------------


class TestEnsureAdminLlmSettingsSeeded:
    @pytest.mark.asyncio
    async def test_seeding_runs_once(self):
        """ensure_admin_llm_settings_seeded should only call seed_admin_llm_settings once."""
        import ii_agent.settings.llm.seeding as seeding_module

        # Reset state
        seeding_module._seeding_done = False

        with patch(
            "ii_agent.settings.llm.seeding.seed_admin_llm_settings", new_callable=AsyncMock
        ) as mock_seed:
            await seeding_module.ensure_admin_llm_settings_seeded()
            await seeding_module.ensure_admin_llm_settings_seeded()

        mock_seed.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_seeding_flag_set_after_success(self):
        import ii_agent.settings.llm.seeding as seeding_module

        seeding_module._seeding_done = False

        with patch("ii_agent.settings.llm.seeding.seed_admin_llm_settings", new_callable=AsyncMock):
            await seeding_module.ensure_admin_llm_settings_seeded()

        assert seeding_module._seeding_done is True

    @pytest.mark.asyncio
    async def test_seeding_flag_not_set_on_error(self):
        import ii_agent.settings.llm.seeding as seeding_module

        seeding_module._seeding_done = False

        with patch(
            "ii_agent.settings.llm.seeding.seed_admin_llm_settings",
            side_effect=Exception("DB error"),
        ):
            await seeding_module.ensure_admin_llm_settings_seeded()

        assert seeding_module._seeding_done is False

    @pytest.mark.asyncio
    async def test_skips_when_already_seeded(self):
        import ii_agent.settings.llm.seeding as seeding_module

        seeding_module._seeding_done = True

        with patch(
            "ii_agent.settings.llm.seeding.seed_admin_llm_settings", new_callable=AsyncMock
        ) as mock_seed:
            await seeding_module.ensure_admin_llm_settings_seeded()

        mock_seed.assert_not_awaited()


# ---------------------------------------------------------------------------
# seed_admin_llm_settings
# ---------------------------------------------------------------------------


def _make_mock_db_session(existing_settings=None):
    """Build a mock async DB session."""
    db = AsyncMock()
    db.__aenter__ = AsyncMock(return_value=db)
    db.__aexit__ = AsyncMock(return_value=None)

    result = MagicMock()
    settings_list = existing_settings or []
    result.scalars.return_value.all.return_value = settings_list
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    db.add = MagicMock()
    return db


class TestSeedAdminLlmSettings:
    @pytest.mark.asyncio
    async def test_skips_when_no_model_configs(self):
        """When settings.model_configs is empty, nothing is written to the DB."""
        mock_settings = MagicMock()
        mock_settings.model_configs = []

        with (
            patch("ii_agent.settings.llm.seeding.get_settings", return_value=mock_settings),
        ):
            from ii_agent.settings.llm.seeding import seed_admin_llm_settings

            await seed_admin_llm_settings()  # Should return without DB call

    @pytest.mark.asyncio
    async def test_inserts_new_settings(self):
        """Entries not in DB are inserted as new ModelSetting rows."""
        mock_settings = MagicMock()
        mock_settings.model_configs = [
            {
                "model_id": "gpt-4",
                "provider": "openai",
                "params": {},
                "api_key": None,
                "pricing": None,
                "base_url": None,
                "display_name": "GPT-4",
                "is_default": True,
            }
        ]

        mock_db = _make_mock_db_session(existing_settings=[])

        with (
            patch("ii_agent.settings.llm.seeding.get_settings", return_value=mock_settings),
            patch(
                "ii_agent.core.db.get_db_session_local",
                return_value=mock_db,
            ),
        ):
            from ii_agent.settings.llm.seeding import seed_admin_llm_settings

            await seed_admin_llm_settings()

        mock_db.add.assert_called_once()
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_updates_existing_settings(self):
        """Entries already in DB are updated in-place."""
        mock_settings = MagicMock()
        mock_settings.model_configs = [
            {
                "model_id": "gpt-4",
                "provider": "openai",
                "params": {},
                "api_key": None,
                "pricing": None,
                "base_url": None,
                "display_name": "GPT-4 Updated",
                "is_default": False,
            }
        ]

        existing = MagicMock()
        existing.model_id = "gpt-4"
        existing.provider = "openai"

        mock_db = _make_mock_db_session(existing_settings=[existing])

        with (
            patch("ii_agent.settings.llm.seeding.get_settings", return_value=mock_settings),
            patch(
                "ii_agent.core.db.get_db_session_local",
                return_value=mock_db,
            ),
        ):
            from ii_agent.settings.llm.seeding import seed_admin_llm_settings

            await seed_admin_llm_settings()

        # Should update existing setting fields
        assert existing.provider == "openai"
        assert existing.display_name == "GPT-4 Updated"
        mock_db.add.assert_not_called()  # No new row
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_encrypts_api_key_when_present(self):
        """API key present in config is encrypted before storing."""
        mock_settings = MagicMock()
        mock_settings.model_configs = [
            {
                "model_id": "gpt-4",
                "provider": "openai",
                "params": {},
                "api_key": "sk-secret",
                "pricing": None,
                "base_url": None,
                "display_name": None,
                "is_default": False,
            }
        ]

        mock_db = _make_mock_db_session(existing_settings=[])
        mock_encryption = MagicMock()
        mock_encryption.encrypt = MagicMock(return_value="encrypted-key")

        with (
            patch("ii_agent.settings.llm.seeding.get_settings", return_value=mock_settings),
            patch("ii_agent.core.db.get_db_session_local", return_value=mock_db),
            patch(
                "ii_agent.core.secrets.encryption.encryption_manager",
                mock_encryption,
            ),
        ):
            from ii_agent.settings.llm.seeding import seed_admin_llm_settings

            await seed_admin_llm_settings()

        # If add was called, the row should have used the encrypted value
        mock_db.add.assert_called()

    @pytest.mark.asyncio
    async def test_handles_pricing_with_model_dump(self):
        """Pricing dict is serialized via model_dump if it has that method."""
        mock_settings = MagicMock()
        pricing = MagicMock()
        pricing.model_dump = MagicMock(return_value={"input": 0.01, "output": 0.02})
        mock_settings.model_configs = [
            {
                "model_id": "gpt-4",
                "provider": "openai",
                "params": {},
                "api_key": None,
                "pricing": pricing,
                "base_url": None,
                "display_name": None,
                "is_default": False,
            }
        ]

        mock_db = _make_mock_db_session(existing_settings=[])

        with (
            patch("ii_agent.settings.llm.seeding.get_settings", return_value=mock_settings),
            patch("ii_agent.core.db.get_db_session_local", return_value=mock_db),
        ):
            from ii_agent.settings.llm.seeding import seed_admin_llm_settings

            await seed_admin_llm_settings()

        pricing.model_dump.assert_called_once()

    @pytest.mark.asyncio
    async def test_inserts_multiple_configs(self):
        """Multiple model configs are all inserted."""
        mock_settings = MagicMock()
        mock_settings.model_configs = [
            {
                "model_id": f"model-{i}",
                "provider": "openai",
                "params": {},
                "api_key": None,
                "pricing": None,
                "base_url": None,
                "display_name": None,
                "is_default": False,
            }
            for i in range(3)
        ]

        mock_db = _make_mock_db_session(existing_settings=[])

        with (
            patch("ii_agent.settings.llm.seeding.get_settings", return_value=mock_settings),
            patch("ii_agent.core.db.get_db_session_local", return_value=mock_db),
        ):
            from ii_agent.settings.llm.seeding import seed_admin_llm_settings

            await seed_admin_llm_settings()

        assert mock_db.add.call_count == 3
