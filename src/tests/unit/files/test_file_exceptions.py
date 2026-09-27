"""Tests for ii_agent.files.exceptions — FileUploadNotFoundError, FileAccessDeniedError, FileSizeLimitExceededError."""

from __future__ import annotations


class TestFilesExceptions:
    def test_file_upload_not_found_with_file_id(self):
        from ii_agent.files.exceptions import FileUploadNotFoundError

        exc = FileUploadNotFoundError(file_id="abc-123")
        assert "abc-123" in str(exc)
        assert exc.file_id == "abc-123"

    def test_file_upload_not_found_without_file_id(self):
        from ii_agent.files.exceptions import FileUploadNotFoundError

        exc = FileUploadNotFoundError(file_id=None)
        assert exc.file_id is None

    def test_file_upload_not_found_with_explicit_message(self):
        from ii_agent.files.exceptions import FileUploadNotFoundError

        exc = FileUploadNotFoundError("custom message", file_id="xyz")
        assert exc.file_id == "xyz"

    def test_file_access_denied_with_file_id(self):
        from ii_agent.files.exceptions import FileAccessDeniedError

        exc = FileAccessDeniedError(file_id="def-456")
        assert "def-456" in str(exc)

    def test_file_size_limit_exceeded(self):
        from ii_agent.files.exceptions import FileSizeLimitExceededError

        exc = FileSizeLimitExceededError(file_size=10_000_000, max_size=5_000_000)
        assert exc.file_size == 10_000_000
        assert exc.max_size == 5_000_000
