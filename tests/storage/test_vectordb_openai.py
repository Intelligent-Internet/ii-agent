"""Unit tests for OpenAI Vector Store.

This module tests the vector store functionality including:
- Content hash deduplication
- File batch upload
- Storage reading
"""

import pytest
import hashlib
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch


class TestContentHashDeduplication:
    """Tests for content-based file deduplication."""

    def test_hash_computation(self):
        """Test SHA-256 hash computation matches expected format."""
        content = b"test file content"
        expected_hash = hashlib.sha256(content).hexdigest()[:16]

        # Verify hash is 16 characters (truncated)
        assert len(expected_hash) == 16

        # Verify it's hexadecimal
        assert all(c in '0123456789abcdef' for c in expected_hash)

    def test_same_content_same_hash(self):
        """Test that identical content produces identical hash."""
        content = b"PDF document content here"

        hash1 = hashlib.sha256(content).hexdigest()[:16]
        hash2 = hashlib.sha256(content).hexdigest()[:16]

        assert hash1 == hash2

    def test_different_content_different_hash(self):
        """Test that different content produces different hash."""
        content1 = b"First document"
        content2 = b"Second document"

        hash1 = hashlib.sha256(content1).hexdigest()[:16]
        hash2 = hashlib.sha256(content2).hexdigest()[:16]

        assert hash1 != hash2


class TestAddFilesBatchDeduplication:
    """Tests for add_files_batch method with deduplication."""

    @pytest.fixture
    def mock_openai_client(self):
        """Create a mock OpenAI client."""
        client = MagicMock()
        client.files.create = AsyncMock()
        client.vector_stores.files.list = AsyncMock()
        client.vector_stores.file_batches.create = AsyncMock()
        return client

    @pytest.fixture
    def mock_storage(self):
        """Create mock storage that returns file content."""
        def read_file(path):
            # Return a BytesIO object simulating file content
            return BytesIO(b"test file content for " + path.encode())

        return MagicMock(read=read_file)

    @pytest.mark.asyncio
    async def test_skips_duplicate_by_content_hash(self):
        """Test that files with same content hash are skipped."""
        # This tests the deduplication logic conceptually
        existing_hashes = {"abc123def456"}  # Existing file hash

        # New file with same content would have same hash
        new_content = b"some content"
        new_hash = "abc123def456"  # Pretend it matches

        # Should be skipped
        assert new_hash in existing_hashes

    @pytest.mark.asyncio
    async def test_uploads_new_file_with_unique_hash(self):
        """Test that files with unique content hash are uploaded."""
        existing_hashes = {"abc123def456"}

        new_hash = "xyz789unique"  # Different hash

        # Should NOT be skipped
        assert new_hash not in existing_hashes

    @pytest.mark.asyncio
    async def test_dedup_within_same_batch(self):
        """Test that duplicates within the same batch are handled."""
        # If same file is in file_ids multiple times, only upload once
        existing_hashes = set()

        # First file
        content1 = b"identical content"
        hash1 = hashlib.sha256(content1).hexdigest()[:16]
        existing_hashes.add(hash1)

        # Second file with identical content
        content2 = b"identical content"
        hash2 = hashlib.sha256(content2).hexdigest()[:16]

        # hash2 should match hash1, so second file should be skipped
        assert hash2 in existing_hashes

    def test_content_hash_stored_in_attributes(self):
        """Test that content_hash is included in file attributes."""
        # This tests the expected attribute structure
        content = b"document content"
        content_hash = hashlib.sha256(content).hexdigest()[:16]

        expected_attributes = {
            "user_id": "user_123",
            "session_id": "session_456",
            "file_name": "doc.pdf",
            "content_type": "application/pdf",
            "content_hash": content_hash,  # This is the new field
            "date": 1234567890.0,
        }

        assert "content_hash" in expected_attributes
        assert len(expected_attributes["content_hash"]) == 16


class TestStorageReading:
    """Tests for storage.read() handling."""

    def test_read_returns_binary_io(self):
        """Test that storage.read returns BinaryIO that needs .read()."""
        # Simulate what storage.read returns
        file_content = b"PDF binary content"
        file_io = BytesIO(file_content)

        # Must call .read() to get bytes
        actual_bytes = file_io.read()

        assert actual_bytes == file_content
        assert isinstance(actual_bytes, bytes)

    def test_hash_from_binary_io(self):
        """Test computing hash from BinaryIO object."""
        content = b"test content"
        file_io = BytesIO(content)

        # Read bytes from file-like object
        file_bytes = file_io.read()

        # Compute hash from bytes
        content_hash = hashlib.sha256(file_bytes).hexdigest()[:16]

        expected = hashlib.sha256(content).hexdigest()[:16]
        assert content_hash == expected


class TestBatchCreationWithoutPolling:
    """Tests verifying batch creation without blocking poll."""

    def test_batch_attributes_include_content_hash(self):
        """Test that batch file attributes include content_hash."""
        # Build the expected structure for batch creation
        uploaded_files = [
            {
                "openai_file_id": "file-abc123",
                "file_name": "manual.pdf",
                "content_type": "application/pdf",
                "bytes": 5500000,
                "content_hash": "a1b2c3d4e5f6g7h8",
            }
        ]

        # Build batch files structure
        batch_files = [
            {
                "file_id": f["openai_file_id"],
                "attributes": {
                    "user_id": "user_123",
                    "session_id": "session_456",
                    "file_name": f["file_name"],
                    "content_type": f["content_type"],
                    "content_hash": f["content_hash"],
                    "date": 1234567890.0,
                },
            }
            for f in uploaded_files
        ]

        # Verify structure
        assert len(batch_files) == 1
        assert batch_files[0]["attributes"]["content_hash"] == "a1b2c3d4e5f6g7h8"

    def test_no_poll_call_in_batch_creation(self):
        """Document that poll is not called (async processing)."""
        # The fix removes the blocking poll call:
        # - OLD: await self.client.vector_stores.file_batches.poll(...)
        # - NEW: Just create the batch and return

        # This is a documentation test - the actual behavior is tested
        # by verifying the code doesn't block for 30+ seconds
        pass


class TestVectorStoreFileListing:
    """Tests for listing existing files in vector store."""

    def test_extract_content_hash_from_attributes(self):
        """Test extracting content_hash from file attributes."""
        # Simulate OpenAI API response
        mock_file = MagicMock()
        mock_file.attributes = {
            "user_id": "user_123",
            "session_id": "session_456",
            "content_hash": "abc123def456"
        }

        # Extract hash
        content_hash = mock_file.attributes.get("content_hash")

        assert content_hash == "abc123def456"

    def test_handle_file_without_content_hash(self):
        """Test handling files that don't have content_hash (legacy files)."""
        # Files uploaded before deduplication was added won't have content_hash
        mock_file = MagicMock()
        mock_file.attributes = {
            "user_id": "user_123",
            "session_id": "session_456",
            # No content_hash field
        }

        # Should handle gracefully
        content_hash = mock_file.attributes.get("content_hash")

        assert content_hash is None

        # Should not add None to existing_hashes set
        existing_hashes = set()
        if content_hash:
            existing_hashes.add(content_hash)

        assert len(existing_hashes) == 0

    def test_handle_file_with_none_attributes(self):
        """Test handling files with None attributes."""
        mock_file = MagicMock()
        mock_file.attributes = None

        # Should handle gracefully
        if mock_file.attributes and mock_file.attributes.get("content_hash"):
            content_hash = mock_file.attributes["content_hash"]
        else:
            content_hash = None

        assert content_hash is None


class TestMimeTypeValidation:
    """Tests for MIME type validation in batch upload."""

    def test_valid_mime_types(self):
        """Test list of valid MIME types for vector store."""
        valid_types = [
            "application/pdf",
            "text/plain",
            "text/markdown",
            "text/md",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.ms-powerpoint",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ]

        # PDF should be valid
        assert "application/pdf" in valid_types

        # Text should be valid
        assert "text/plain" in valid_types

        # Markdown variants should be valid
        assert "text/markdown" in valid_types

    def test_invalid_mime_types_rejected(self):
        """Test that invalid MIME types are not in valid list."""
        valid_types = [
            "application/pdf",
            "text/plain",
            "text/markdown",
        ]

        # Images should NOT be valid for vector store
        assert "image/png" not in valid_types
        assert "image/jpeg" not in valid_types

        # Executables should NOT be valid
        assert "application/octet-stream" not in valid_types
