"""Tests for ii_agent.core.encryption.EncryptionManager."""

from __future__ import annotations

import base64
import os
from unittest.mock import patch


from ii_agent.core.encryption import EncryptionManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_manager(**env_overrides) -> EncryptionManager:
    """Create an EncryptionManager with controlled environment variables."""
    base_env = {
        "ENCRYPTION_KEY": None,
        "ENCRYPTION_PASSWORD": None,
        "ENCRYPTION_SALT": None,
    }
    base_env.update(env_overrides)

    env_patch = {k: v for k, v in base_env.items() if v is not None}
    remove_keys = [k for k, v in base_env.items() if v is None]

    cleaned_env = {k: v for k, v in os.environ.items() if k not in remove_keys}
    cleaned_env.update(env_patch)

    with patch.dict(os.environ, cleaned_env, clear=True):
        return EncryptionManager()


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestEncryptionManagerInit:
    def test_creates_with_env_key(self):
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()
        manager = _make_manager(ENCRYPTION_KEY=key)
        assert manager.encryption_key == key.encode()

    def test_creates_with_password_and_salt(self):
        manager = _make_manager(ENCRYPTION_PASSWORD="testpass", ENCRYPTION_SALT="testsalt")
        assert manager.encryption_key is not None
        assert len(manager.encryption_key) > 0

    def test_same_password_salt_produces_same_key(self):
        m1 = _make_manager(ENCRYPTION_PASSWORD="pw", ENCRYPTION_SALT="salt")
        m2 = _make_manager(ENCRYPTION_PASSWORD="pw", ENCRYPTION_SALT="salt")
        assert m1.encryption_key == m2.encryption_key

    def test_different_passwords_produce_different_keys(self):
        m1 = _make_manager(ENCRYPTION_PASSWORD="pw1", ENCRYPTION_SALT="salt")
        m2 = _make_manager(ENCRYPTION_PASSWORD="pw2", ENCRYPTION_SALT="salt")
        assert m1.encryption_key != m2.encryption_key

    def test_different_salts_produce_different_keys(self):
        m1 = _make_manager(ENCRYPTION_PASSWORD="pw", ENCRYPTION_SALT="salt1")
        m2 = _make_manager(ENCRYPTION_PASSWORD="pw", ENCRYPTION_SALT="salt2")
        assert m1.encryption_key != m2.encryption_key

    def test_default_env_values_work(self):
        """Even with no env vars, manager initializes using hard-coded defaults."""
        manager = _make_manager()
        assert manager.encryption_key is not None
        assert manager.fernet is not None


# ---------------------------------------------------------------------------
# Encrypt
# ---------------------------------------------------------------------------


class TestEncryptionManagerEncrypt:
    def setup_method(self):
        self.manager = _make_manager(ENCRYPTION_PASSWORD="testpw", ENCRYPTION_SALT="testsalt")

    def test_encrypt_returns_string(self):
        result = self.manager.encrypt("hello")
        assert isinstance(result, str)

    def test_encrypt_empty_string_returns_empty(self):
        assert self.manager.encrypt("") == ""

    def test_encrypted_differs_from_plaintext(self):
        plaintext = "my secret value"
        encrypted = self.manager.encrypt(plaintext)
        assert encrypted != plaintext

    def test_same_plaintext_different_ciphertext_each_time(self):
        """Fernet uses a random IV so two encryptions differ."""
        enc1 = self.manager.encrypt("hello")
        enc2 = self.manager.encrypt("hello")
        assert enc1 != enc2

    def test_encrypt_is_base64(self):
        encrypted = self.manager.encrypt("test value")
        # Should not raise when decoded
        base64.urlsafe_b64decode(encrypted)


# ---------------------------------------------------------------------------
# Decrypt
# ---------------------------------------------------------------------------


class TestEncryptionManagerDecrypt:
    def setup_method(self):
        self.manager = _make_manager(ENCRYPTION_PASSWORD="testpw", ENCRYPTION_SALT="testsalt")

    def test_roundtrip(self):
        original = "my api key"
        encrypted = self.manager.encrypt(original)
        decrypted = self.manager.decrypt(encrypted)
        assert decrypted == original

    def test_decrypt_empty_string_returns_empty(self):
        assert self.manager.decrypt("") == ""

    def test_decrypt_garbage_returns_empty(self):
        result = self.manager.decrypt("not-valid-encrypted-data")
        assert result == ""

    def test_decrypt_with_wrong_key_returns_empty(self):
        m1 = _make_manager(ENCRYPTION_PASSWORD="key1", ENCRYPTION_SALT="salt")
        m2 = _make_manager(ENCRYPTION_PASSWORD="key2", ENCRYPTION_SALT="salt")
        encrypted = m1.encrypt("secret")
        result = m2.decrypt(encrypted)
        assert result == ""

    def test_roundtrip_special_characters(self):
        original = "p@ss!w0rd#~\n\t"
        encrypted = self.manager.encrypt(original)
        decrypted = self.manager.decrypt(encrypted)
        assert decrypted == original

    def test_roundtrip_unicode(self):
        original = "héllo wörld 日本語"
        encrypted = self.manager.encrypt(original)
        decrypted = self.manager.decrypt(encrypted)
        assert decrypted == original


# ---------------------------------------------------------------------------
# is_encrypted
# ---------------------------------------------------------------------------


class TestEncryptionManagerIsEncrypted:
    def setup_method(self):
        self.manager = _make_manager(ENCRYPTION_PASSWORD="testpw", ENCRYPTION_SALT="testsalt")

    def test_raw_fernet_token_detected(self):
        """is_encrypted checks for the raw Fernet token prefix (gAAA/AAAA)."""
        # Produce a raw Fernet token (no extra base64 wrapping)
        raw_token = self.manager.fernet.encrypt(b"hello world").decode()
        # Raw Fernet tokens are long and start with gAAA
        assert raw_token.startswith("gAAA")
        assert self.manager.is_encrypted(raw_token) is True

    def test_empty_string_not_encrypted(self):
        assert self.manager.is_encrypted("") is False

    def test_plain_text_not_encrypted(self):
        assert self.manager.is_encrypted("plain text") is False

    def test_short_base64_not_encrypted(self):
        # Too short to be a Fernet token
        assert self.manager.is_encrypted("aGVsbG8=") is False

    def test_double_encoded_encrypt_output_not_detected(self):
        # encrypt() wraps Fernet output in additional base64, so is_encrypted
        # returns False for values produced by encrypt()
        encrypted = self.manager.encrypt("hello world")
        # The outer encoding starts with 'Z0FB...' not 'gAAA'
        assert not encrypted.startswith("gAAA")
        assert self.manager.is_encrypted(encrypted) is False


# ---------------------------------------------------------------------------
# Global encryption_manager singleton
# ---------------------------------------------------------------------------


class TestGlobalEncryptionManager:
    def test_global_manager_exists(self):
        from ii_agent.core.encryption import encryption_manager

        assert encryption_manager is not None
        assert isinstance(encryption_manager, EncryptionManager)

    def test_global_manager_can_roundtrip(self):
        from ii_agent.core.encryption import encryption_manager

        value = "test123"
        enc = encryption_manager.encrypt(value)
        assert encryption_manager.decrypt(enc) == value
