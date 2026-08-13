"""Tests for ii_agent.auth.oidc_verify — verify_at_hash_if_present and helpers."""

from __future__ import annotations


class TestVerifyAtHash:
    def test_no_at_hash_in_claims(self):
        """Branch [91,92]: at_hash absent → no-op."""
        from ii_agent.auth.oidc_verify import verify_at_hash_if_present

        verify_at_hash_if_present(claims={}, access_token="tok")  # must not raise

    def test_no_access_token(self):
        """Branch [91,92]: access_token=None → no-op."""
        from ii_agent.auth.oidc_verify import verify_at_hash_if_present

        verify_at_hash_if_present(claims={"at_hash": "somevalue"}, access_token=None)

    def test_matching_at_hash(self):
        """Lines 94-103: correct at_hash → no error."""
        import hashlib
        import base64
        from ii_agent.auth.oidc_verify import verify_at_hash_if_present

        access_token = "my_access_token"
        digest = hashlib.sha256(access_token.encode("ascii")).digest()
        left_half = digest[: len(digest) // 2]
        at_hash = base64.urlsafe_b64encode(left_half).rstrip(b"=").decode("ascii")

        verify_at_hash_if_present(
            claims={"at_hash": at_hash},
            access_token=access_token,
            alg="RS256",
        )

    def test_mismatched_at_hash_raises(self):
        """Line 104: mismatch → RuntimeError."""
        from ii_agent.auth.oidc_verify import verify_at_hash_if_present

        try:
            verify_at_hash_if_present(
                claims={"at_hash": "wrong_hash_value"},
                access_token="my_access_token",
            )
            assert False, "Should raise RuntimeError"
        except RuntimeError as e:
            assert "at_hash" in str(e)

    def test_get_http_returns_client(self):
        """Line 13: _get_http returns httpx.Client."""
        from ii_agent.auth.oidc_verify import _get_http
        import httpx

        client = _get_http()
        assert isinstance(client, httpx.Client)

    def test_get_http_custom_timeout(self):
        """Line 13: _get_http with custom timeout."""
        from ii_agent.auth.oidc_verify import _get_http

        client = _get_http(timeout=5.0)
        assert client.timeout.read == 5.0
