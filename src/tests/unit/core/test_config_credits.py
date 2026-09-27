"""Tests for ii_agent.core.config.credits — CreditsSettings helpers."""

from __future__ import annotations


class TestCreditsSettings:
    def test_get_plan_credits_known_plan(self):
        from ii_agent.core.config.credits import CreditsSettings

        settings = CreditsSettings()
        assert settings.get_plan_credits("free") == 300.0

    def test_get_plan_credits_unknown_plan_returns_default(self):
        from ii_agent.core.config.credits import CreditsSettings

        settings = CreditsSettings()
        result = settings.get_plan_credits("enterprise_xyz")
        assert result == settings.default_user_credits

    def test_should_grant_beta_bonus_when_enabled(self):
        from ii_agent.core.config.credits import CreditsSettings

        settings = CreditsSettings()
        settings.beta_program_enabled = True
        settings.beta_program_bonus_credits = 100.0
        assert settings.should_grant_beta_bonus() is True

    def test_should_grant_beta_bonus_when_disabled(self):
        from ii_agent.core.config.credits import CreditsSettings

        settings = CreditsSettings()
        settings.beta_program_enabled = False
        assert settings.should_grant_beta_bonus() is False

    def test_should_grant_beta_bonus_when_zero_credits(self):
        from ii_agent.core.config.credits import CreditsSettings

        settings = CreditsSettings()
        settings.beta_program_enabled = True
        settings.beta_program_bonus_credits = 0.0
        assert settings.should_grant_beta_bonus() is False
