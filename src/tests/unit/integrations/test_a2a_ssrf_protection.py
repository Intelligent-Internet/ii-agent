"""Tests for SSRF protection in A2A adapter server.

Covers the _is_safe_url() function that validates URLs before making
external requests during agent discovery.
"""

from __future__ import annotations

import pytest

from ii_agent.integrations.a2a.adapter_server import _is_safe_url

pytestmark = pytest.mark.unit


class TestIsSafeUrl:
    """Validate URL safety checks for SSRF prevention."""

    # -- Valid URLs --

    def test_allows_http_url(self):
        safe, msg = _is_safe_url("http://example.com/agent")
        assert safe is True
        assert msg == ""

    def test_allows_https_url(self):
        safe, msg = _is_safe_url("https://agent.example.com/.well-known/agent.json")
        assert safe is True
        assert msg == ""

    def test_allows_url_with_port(self):
        safe, msg = _is_safe_url("https://agent.example.com:8080/agent")
        assert safe is True
        assert msg == ""

    def test_allows_url_with_path_and_query(self):
        safe, msg = _is_safe_url("https://api.example.com/v1/agent?version=2")
        assert safe is True
        assert msg == ""

    # -- Scheme restrictions --

    def test_rejects_file_scheme(self):
        safe, msg = _is_safe_url("file:///etc/passwd")
        assert safe is False
        assert "scheme" in msg.lower()

    def test_rejects_ftp_scheme(self):
        safe, msg = _is_safe_url("ftp://internal-server/data")
        assert safe is False
        assert "scheme" in msg.lower()

    def test_rejects_gopher_scheme(self):
        safe, msg = _is_safe_url("gopher://evil.com")
        assert safe is False

    def test_rejects_empty_scheme(self):
        safe, msg = _is_safe_url("://no-scheme.com/path")
        assert safe is False

    # -- Private IP ranges --

    def test_rejects_localhost_127(self):
        safe, msg = _is_safe_url("http://127.0.0.1/secret")
        assert safe is False
        assert "private" in msg.lower() or "internal" in msg.lower()

    def test_rejects_localhost_127_variant(self):
        safe, msg = _is_safe_url("http://127.0.0.2:8080")
        assert safe is False

    def test_rejects_10_network(self):
        safe, msg = _is_safe_url("http://10.0.0.1/internal")
        assert safe is False

    def test_rejects_172_16_network(self):
        safe, msg = _is_safe_url("http://172.16.0.1/admin")
        assert safe is False

    def test_rejects_192_168_network(self):
        safe, msg = _is_safe_url("http://192.168.1.100/api")
        assert safe is False

    def test_rejects_link_local_169_254(self):
        safe, msg = _is_safe_url("http://169.254.169.254/latest/meta-data/")
        assert safe is False

    def test_rejects_ipv6_loopback(self):
        safe, msg = _is_safe_url("http://[::1]/secret")
        assert safe is False

    # -- Dangerous hostnames --

    def test_rejects_gcp_metadata_hostname(self):
        safe, msg = _is_safe_url("http://metadata.google.internal/computeMetadata/v1/")
        assert safe is False
        assert "blocked" in msg.lower()

    def test_rejects_aws_metadata_ip(self):
        safe, msg = _is_safe_url("http://169.254.169.254/latest/meta-data/")
        assert safe is False

    # -- Edge cases --

    def test_rejects_url_without_hostname(self):
        safe, msg = _is_safe_url("http:///path-only")
        assert safe is False
        assert "hostname" in msg.lower()

    def test_rejects_empty_url(self):
        safe, msg = _is_safe_url("")
        assert safe is False

    def test_rejects_garbage_input(self):
        safe, msg = _is_safe_url("not a url at all")
        assert safe is False

    def test_allows_hostname_not_ip(self):
        """Non-IP hostnames are allowed (DNS rebinding is harder to prevent)."""
        safe, msg = _is_safe_url("https://my-internal-agent.corp.example.com/agent")
        assert safe is True
