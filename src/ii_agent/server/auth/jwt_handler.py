"""JWT token handling utilities."""

import os
import jwt
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any


class JWTHandler:
    """Handles JWT token creation and validation."""

    def __init__(self):
        self.secret_key = os.getenv(
            "JWT_SECRET_KEY", "your-secret-key-change-in-production"
        )
        self.algorithm = "HS256"
        self.access_token_expire_minutes = int(
            os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15")
        )
        self.refresh_token_expire_days = int(
            os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7")
        )

    def create_access_token(self, user_id: str, email: str, role: str = "user") -> str:
        """Create a new access token."""
        now = datetime.now(timezone.utc)
        exp_time = now + timedelta(minutes=self.access_token_expire_minutes)
        payload = {
            "user_id": user_id,
            "email": email,
            "role": role,
            "type": "access",
            "exp": int(exp_time.timestamp()),
            "iat": int(now.timestamp()),
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def create_refresh_token(self, user_id: str) -> str:
        """Create a new refresh token."""
        payload = {
            "user_id": user_id,
            "type": "refresh",
            "exp": datetime.now(timezone.utc)
            + timedelta(days=self.refresh_token_expire_days),
            "iat": datetime.now(timezone.utc),
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify and decode a JWT token."""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    def verify_access_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify an access token specifically."""
        payload = self.verify_token(token)
        if payload and payload.get("type") == "access":
            return payload
        return None

    def verify_refresh_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify a refresh token specifically."""
        payload = self.verify_token(token)
        if payload and payload.get("type") == "refresh":
            return payload
        return None


# Global JWT handler instance
jwt_handler = JWTHandler()
