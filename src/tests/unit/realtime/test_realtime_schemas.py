"""Tests for ii_agent.realtime.schemas — AppleAuth2FAContent + SaveExpoTokenContent validators."""

from __future__ import annotations

import pytest


class TestRealtimeSchemaValidators:
    def test_apple_auth_2fa_valid_code(self):
        """Branch [338, 340]: valid code → return v."""
        from ii_agent.realtime.schemas import AppleAuth2FAContent

        content = AppleAuth2FAContent(code="123456")
        assert content.code == "123456"

    def test_apple_auth_2fa_invalid_short_code(self):
        """Branch [338, 339]: invalid code → raise ValueError."""
        from ii_agent.realtime.schemas import AppleAuth2FAContent

        with pytest.raises(Exception):
            AppleAuth2FAContent(code="12")

    def test_apple_auth_2fa_non_digit_code(self):
        """Branch [338, 339]: non-digit code → raise ValueError."""
        from ii_agent.realtime.schemas import AppleAuth2FAContent

        with pytest.raises(Exception):
            AppleAuth2FAContent(code="abcdef")

    def test_apple_auth_2fa_empty_code(self):
        """Branch [338, 339]: empty string → raise ValueError."""
        from ii_agent.realtime.schemas import AppleAuth2FAContent

        with pytest.raises(Exception):
            AppleAuth2FAContent(code="")

    def test_save_expo_token_valid(self):
        """Branch [369, 371]: valid token → return v."""
        from ii_agent.realtime.schemas import SaveExpoTokenContent

        content = SaveExpoTokenContent(expo_token="valid-expo-token-12345")
        assert content.expo_token == "valid-expo-token-12345"

    def test_save_expo_token_whitespace_stripped(self):
        """Validator strips whitespace before checking."""
        from ii_agent.realtime.schemas import SaveExpoTokenContent

        content = SaveExpoTokenContent(expo_token="  my-token  ")
        assert content.expo_token == "my-token"

    def test_save_expo_token_empty_raises(self):
        """Branch [369, 370]: empty token → raise ValueError."""
        from ii_agent.realtime.schemas import SaveExpoTokenContent

        with pytest.raises(Exception):
            SaveExpoTokenContent(expo_token="")

    def test_save_expo_token_whitespace_only_raises(self):
        """Branch [369, 370]: whitespace-only → raise ValueError."""
        from ii_agent.realtime.schemas import SaveExpoTokenContent

        with pytest.raises(Exception):
            SaveExpoTokenContent(expo_token="   ")
