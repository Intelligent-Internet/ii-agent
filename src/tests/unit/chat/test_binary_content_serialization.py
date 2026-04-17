"""Tests for BinaryContent base64 validator and serializer.

Covers the new field_validator/_decode_base64 and field_serializer/_encode_base64
added to BinaryContent in chat/types.py.
"""

from __future__ import annotations

import base64

import pytest

from ii_agent.chat.types import BinaryContent

pytestmark = pytest.mark.unit


class TestBinaryContentBase64RoundTrip:
    """BinaryContent serialization/deserialization of the `data` field."""

    def test_raw_bytes_accepted(self):
        """Raw bytes are stored as-is."""
        obj = BinaryContent(path="img.png", mime_type="image/png", data=b"\x89PNG")
        assert obj.data == b"\x89PNG"

    def test_base64_string_decoded_on_construction(self):
        """A base64-encoded string (e.g. from DB JSON) is decoded to bytes."""
        raw = b"\x89PNG\r\n\x1a\n"
        encoded = base64.b64encode(raw).decode("ascii")
        obj = BinaryContent(path="img.png", mime_type="image/png", data=encoded)
        assert obj.data == raw

    def test_model_dump_json_encodes_data_as_base64(self):
        """model_dump() serializes data as a base64 string via field_serializer."""
        raw = b"hello world"
        obj = BinaryContent(path="file.bin", mime_type="application/octet-stream", data=raw)
        dumped = obj.model_dump()
        assert dumped["data"] == base64.b64encode(raw).decode("ascii")

    def test_full_round_trip_bytes(self):
        """Construct from bytes -> dump -> reconstruct from dump."""
        raw = b"\x00\x01\x02\xff"
        obj = BinaryContent(path="f.bin", mime_type="application/octet-stream", data=raw)
        dumped = obj.model_dump()
        restored = BinaryContent(**dumped)
        assert restored.data == raw

    def test_full_round_trip_base64_string(self):
        """Construct from base64 string -> dump -> reconstruct from dump."""
        raw = b"\x89PNG fake image data"
        encoded = base64.b64encode(raw).decode("ascii")
        obj = BinaryContent(path="img.png", mime_type="image/png", data=encoded)
        dumped = obj.model_dump()
        restored = BinaryContent(**dumped)
        assert restored.data == raw

    def test_empty_bytes(self):
        """Empty bytes round-trip correctly."""
        obj = BinaryContent(path="empty.bin", mime_type="application/octet-stream", data=b"")
        dumped = obj.model_dump()
        assert dumped["data"] == ""
        restored = BinaryContent(**dumped)
        assert restored.data == b""

    def test_to_base64_anthropic(self):
        """to_base64() returns plain base64 for anthropic provider."""
        raw = b"test data"
        obj = BinaryContent(path="f.bin", mime_type="text/plain", data=raw)
        result = obj.to_base64(provider="anthropic")
        assert result == base64.b64encode(raw).decode("utf-8")

    def test_to_base64_openai(self):
        """to_base64() returns data URI for openai provider."""
        raw = b"test data"
        obj = BinaryContent(path="f.bin", mime_type="image/jpeg", data=raw)
        result = obj.to_base64(provider="openai")
        expected = f"data:image/jpeg;base64,{base64.b64encode(raw).decode('utf-8')}"
        assert result == expected

    def test_invalid_base64_string_raises(self):
        """Invalid base64 string raises a validation error."""
        with pytest.raises(Exception):
            BinaryContent(path="f.bin", mime_type="text/plain", data="not-valid-base64!!!")
