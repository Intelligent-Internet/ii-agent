"""Encryption utilities for sensitive data."""

import os
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class EncryptionManager:
    """Manager for encrypting and decrypting sensitive data like API keys."""

    def __init__(self):
        # Get encryption key from environment or generate one
        self.encryption_key = self._get_or_generate_key()
        self.fernet = Fernet(self.encryption_key)

    def _get_or_generate_key(self) -> bytes:
        """Get encryption key from environment or generate a new one."""
        # Try to get key from environment
        env_key = os.getenv("ENCRYPTION_KEY")

        if env_key:
            return env_key.encode()

        # Generate key from a password and salt
        password = os.getenv(
            "ENCRYPTION_PASSWORD", "default-password-change-in-production"
        ).encode()
        salt = os.getenv("ENCRYPTION_SALT", "default-salt").encode()

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )

        key = base64.urlsafe_b64encode(kdf.derive(password))
        return key

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a plaintext string.

        Args:
            plaintext: The string to encrypt

        Returns:
            Base64 encoded encrypted string
        """
        if not plaintext:
            return ""

        encrypted_bytes = self.fernet.encrypt(plaintext.encode())
        return base64.urlsafe_b64encode(encrypted_bytes).decode()

    def decrypt(self, encrypted_text: str) -> str:
        """Decrypt an encrypted string.

        Args:
            encrypted_text: Base64 encoded encrypted string

        Returns:
            Decrypted plaintext string
        """
        if not encrypted_text:
            return ""

        try:
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_text.encode())
            decrypted_bytes = self.fernet.decrypt(encrypted_bytes)
            return decrypted_bytes.decode()
        except Exception:
            # If decryption fails, return empty string
            return ""

    def is_encrypted(self, text: str) -> bool:
        """Check if a string appears to be encrypted.

        Args:
            text: String to check

        Returns:
            True if string appears to be encrypted
        """
        if not text:
            return False

        try:
            # Try to decode as base64
            base64.urlsafe_b64decode(text.encode())
            # If it decodes and contains the Fernet version byte, it's likely encrypted
            return text.startswith(("gAAA", "AAAA")) and len(text) > 50
        except Exception:
            return False


# Global encryption manager instance
encryption_manager = EncryptionManager()
