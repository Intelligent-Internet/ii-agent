"""Tests for FileResponseObject validation edge cases.

Covers:
- id field: str type, explicit str() conversion at call sites (UUID coerced)
- provider field: str type (widened from Literal to support additional providers)
- Optional field defaults
"""

from __future__ import annotations

import uuid

import pytest

from ii_agent.chat.llm.anthropic.provider import FileResponseObject

pytestmark = pytest.mark.unit


class TestFileResponseObjectValidation:
    """FileResponseObject Pydantic model validation edge cases."""

    def test_accepts_string_id(self):
        """Standard case: string ID should work."""
        obj = FileResponseObject(
            id="file-abc123",
            provider_file_id="pf-123",
            provider="anthropic",
            content_type="image/png",
            file_name="test.png",
        )
        assert obj.id == "file-abc123"

    def test_rejects_raw_uuid_object(self):
        """Pydantic str field rejects raw UUID objects.
        Call sites must use str(uuid) explicitly."""
        from pydantic import ValidationError

        file_uuid = uuid.uuid4()
        with pytest.raises(ValidationError):
            FileResponseObject(
                id=file_uuid,
                provider_file_id="pf-123",
                provider="anthropic",
                content_type="image/png",
                file_name="test.png",
            )

    def test_accepts_stringified_uuid(self):
        """Call sites use str(uuid) explicitly, which Pydantic accepts."""
        file_uuid = uuid.uuid4()
        obj = FileResponseObject(
            id=str(file_uuid),
            provider_file_id="pf-123",
            provider="anthropic",
            content_type="image/png",
            file_name="test.png",
        )
        assert obj.id == str(file_uuid)

    def test_accepts_any_provider_string(self):
        """Provider field is str to support additional providers (e.g., google)."""
        obj = FileResponseObject(
            id="file-abc123",
            provider_file_id="pf-123",
            provider="Anthropic",
            content_type="image/png",
            file_name="test.png",
        )
        assert obj.provider == "Anthropic"

    def test_accepts_openai_any_case(self):
        """Provider is plain str — any casing is accepted."""
        obj = FileResponseObject(
            id="file-abc123",
            provider_file_id="pf-123",
            provider="OpenAI",
            content_type="image/png",
            file_name="test.png",
        )
        assert obj.provider == "OpenAI"

    def test_accepts_lowercase_anthropic(self):
        """Correct usage: lowercase 'anthropic'."""
        obj = FileResponseObject(
            id="file-abc123",
            provider_file_id="pf-123",
            provider="anthropic",
            content_type="image/png",
            file_name="test.png",
        )
        assert obj.provider == "anthropic"

    def test_accepts_lowercase_openai(self):
        """Correct usage: lowercase 'openai'."""
        obj = FileResponseObject(
            id="file-abc123",
            provider_file_id="pf-123",
            provider="openai",
            content_type="image/png",
            file_name="test.png",
        )
        assert obj.provider == "openai"

    def test_accepts_google_provider(self):
        """Extended provider: 'google' is now a valid provider."""
        obj = FileResponseObject(
            id="file-abc123",
            provider_file_id="pf-123",
            provider="google",
            content_type="image/png",
            file_name="test.png",
        )
        assert obj.provider == "google"

    def test_stringified_uuid_and_arbitrary_provider(self):
        """Both str(uuid) id and arbitrary provider work together."""
        file_uuid = uuid.uuid4()
        obj = FileResponseObject(
            id=str(file_uuid),
            provider_file_id="pf-123",
            provider="custom_provider",
            content_type="image/png",
            file_name="test.png",
        )
        assert obj.id == str(file_uuid)
        assert obj.provider == "custom_provider"

    def test_optional_fields_default_correctly(self):
        """Verify optional fields have correct defaults."""
        obj = FileResponseObject(
            id="file-abc123",
            provider_file_id="pf-123",
            provider="anthropic",
            content_type="image/png",
            file_name="test.png",
        )
        assert obj.file_size == 0
        assert obj.raw_file_object is None
