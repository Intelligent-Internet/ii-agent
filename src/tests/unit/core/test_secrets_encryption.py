"""Tests for ii_agent.core.secrets.encryption — EncryptionManager empty-input guards."""

from __future__ import annotations

import os


class TestEncryptionManagerEmptyInputs:
    """All 6 early-return guards hit by passing empty strings."""

    def _make_manager(self):
        from cryptography.fernet import Fernet
        from ii_agent.core.secrets.encryption import EncryptionManager

        key = Fernet.generate_key().decode()
        return EncryptionManager(key)

    def test_encrypt_empty_string_returns_empty(self):
        mgr = self._make_manager()
        assert mgr.encrypt("") == ""

    def test_decrypt_empty_string_returns_empty(self):
        mgr = self._make_manager()
        assert mgr.decrypt("") == ""

    def test_encrypt_raw_empty_string_returns_empty(self):
        mgr = self._make_manager()
        assert mgr.encrypt_raw("") == ""

    def test_decrypt_raw_empty_string_returns_empty(self):
        mgr = self._make_manager()
        assert mgr.decrypt_raw("") == ""

    def test_is_encrypted_empty_string_returns_false(self):
        mgr = self._make_manager()
        assert mgr.is_encrypted("") is False

    def test_get_key_from_env_uses_env_var(self):
        """Line 111: returns env key when ENCRYPTION_KEY is set."""
        from ii_agent.core.secrets.encryption import _get_key_from_env

        # Use monkeypatching via os.environ
        original = os.environ.get("ENCRYPTION_KEY")
        try:
            os.environ["ENCRYPTION_KEY"] = "test-key-from-env"
            result = _get_key_from_env()
            assert result == "test-key-from-env"
        finally:
            if original is None:
                os.environ.pop("ENCRYPTION_KEY", None)
            else:
                os.environ["ENCRYPTION_KEY"] = original
