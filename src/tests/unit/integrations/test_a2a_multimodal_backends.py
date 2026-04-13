"""Unit tests for ClaudeCodeBackend and CopilotBackend multimodal image handling."""

from __future__ import annotations

import base64
import os
import tempfile


from a2a.types import (
    FilePart,
    FileWithBytes,
    FileWithUri,
    Part,
    TextPart,
)

from ii_agent.integrations.a2a.claude_code_backend import (
    _cleanup_temp_files,
    _extract_image_paths_from_parts,
)
from ii_agent.integrations.a2a.copilot_backend import (
    _parts_to_attachments,
)


class TestExtractImagePathsFromParts:
    def test_none_parts_returns_empty(self):
        paths, temps = _extract_image_paths_from_parts(None)
        assert paths == []
        assert temps == []

    def test_empty_list_returns_empty(self):
        paths, temps = _extract_image_paths_from_parts([])
        assert paths == []
        assert temps == []

    def test_text_part_ignored(self):
        parts = [Part(root=TextPart(text="hello"))]
        paths, temps = _extract_image_paths_from_parts(parts)
        assert paths == []
        assert temps == []

    def test_file_uri_with_file_scheme(self):
        parts = [
            Part(
                root=FilePart(
                    file=FileWithUri(name="img", uri="file:///tmp/test.png", mime_type="image/png")
                )
            )
        ]
        paths, temps = _extract_image_paths_from_parts(parts)
        assert paths == ["/tmp/test.png"]
        assert temps == []

    def test_file_with_bytes_creates_temp_file(self):
        raw = b"fake-png-data"
        b64 = base64.b64encode(raw).decode()
        parts = [
            Part(root=FilePart(file=FileWithBytes(name="img", bytes=b64, mime_type="image/png")))
        ]
        paths, temps = _extract_image_paths_from_parts(parts)
        assert len(paths) == 1
        assert len(temps) == 1
        assert paths[0] == temps[0]
        # Verify temp file was written correctly
        with open(temps[0], "rb") as f:
            assert f.read() == raw
        assert temps[0].endswith(".png")
        # Cleanup
        _cleanup_temp_files(temps)
        assert not os.path.exists(temps[0])

    def test_jpeg_extension(self):
        b64 = base64.b64encode(b"data").decode()
        parts = [
            Part(root=FilePart(file=FileWithBytes(name="img", bytes=b64, mime_type="image/jpeg")))
        ]
        paths, temps = _extract_image_paths_from_parts(parts)
        assert temps[0].endswith(".jpg")
        _cleanup_temp_files(temps)

    def test_webp_extension(self):
        b64 = base64.b64encode(b"data").decode()
        parts = [
            Part(root=FilePart(file=FileWithBytes(name="img", bytes=b64, mime_type="image/webp")))
        ]
        paths, temps = _extract_image_paths_from_parts(parts)
        assert temps[0].endswith(".webp")
        _cleanup_temp_files(temps)

    def test_non_image_file_skipped(self):
        parts = [
            Part(
                root=FilePart(
                    file=FileWithUri(
                        name="doc", uri="file:///tmp/doc.pdf", mime_type="application/pdf"
                    )
                )
            )
        ]
        paths, temps = _extract_image_paths_from_parts(parts)
        assert paths == []
        assert temps == []

    def test_remote_url_skipped(self):
        parts = [
            Part(
                root=FilePart(
                    file=FileWithUri(
                        name="img", uri="https://example.com/img.png", mime_type="image/png"
                    )
                )
            )
        ]
        paths, temps = _extract_image_paths_from_parts(parts)
        assert paths == []
        assert temps == []

    def test_multiple_images_mixed(self):
        b64 = base64.b64encode(b"bytes").decode()
        parts = [
            Part(root=TextPart(text="describe these")),
            Part(
                root=FilePart(
                    file=FileWithUri(name="img1", uri="file:///tmp/a.png", mime_type="image/png")
                )
            ),
            Part(root=FilePart(file=FileWithBytes(name="img2", bytes=b64, mime_type="image/gif"))),
        ]
        paths, temps = _extract_image_paths_from_parts(parts)
        assert len(paths) == 2
        assert paths[0] == "/tmp/a.png"
        assert len(temps) == 1
        assert temps[0].endswith(".gif")
        _cleanup_temp_files(temps)


class TestCleanupTempFiles:
    def test_removes_existing_files(self):
        fd, path = tempfile.mkstemp()
        os.close(fd)
        assert os.path.exists(path)
        _cleanup_temp_files([path])
        assert not os.path.exists(path)

    def test_ignores_missing_files(self):
        # Should not raise
        _cleanup_temp_files(["/tmp/nonexistent_a2a_test_file_xyz"])

    def test_empty_list(self):
        _cleanup_temp_files([])


# ---------------------------------------------------------------------------
# Copilot SDK attachment conversion
# ---------------------------------------------------------------------------


class TestPartsToAttachments:
    """Test _parts_to_attachments for Copilot SDK image forwarding."""

    def test_none_parts_returns_empty(self):
        attachments, temps = _parts_to_attachments(None)
        assert attachments == []
        assert temps == []

    def test_empty_list_returns_empty(self):
        attachments, temps = _parts_to_attachments([])
        assert attachments == []
        assert temps == []

    def test_text_part_ignored(self):
        parts = [Part(root=TextPart(text="hello"))]
        attachments, temps = _parts_to_attachments(parts)
        assert attachments == []
        assert temps == []

    def test_file_uri_with_file_scheme_produces_file_attachment(self):
        parts = [
            Part(
                root=FilePart(
                    file=FileWithUri(name="img", uri="file:///tmp/test.png", mime_type="image/png")
                )
            )
        ]
        attachments, temps = _parts_to_attachments(parts)
        assert len(attachments) == 1
        assert attachments[0] == {"type": "file", "path": "/tmp/test.png"}
        assert temps == []

    def test_file_with_bytes_produces_file_attachment(self):
        raw = b"fake-png-data"
        b64 = base64.b64encode(raw).decode()
        parts = [
            Part(root=FilePart(file=FileWithBytes(name="img", bytes=b64, mime_type="image/png")))
        ]
        attachments, temps = _parts_to_attachments(parts)
        assert len(attachments) == 1
        # SDK has no blob type; bytes are written to a temp file
        assert attachments[0]["type"] == "file"
        assert attachments[0]["path"].endswith(".png")
        assert len(temps) == 1  # temp file path tracked for cleanup
        # Verify the temp file contains the decoded data
        import os

        assert os.path.exists(temps[0])
        with open(temps[0], "rb") as f:
            assert f.read() == raw
        # Cleanup
        for p in temps:
            os.unlink(p)

    def test_remote_url_skipped(self):
        parts = [
            Part(
                root=FilePart(
                    file=FileWithUri(
                        name="img", uri="https://example.com/img.png", mime_type="image/png"
                    )
                )
            )
        ]
        attachments, temps = _parts_to_attachments(parts)
        assert attachments == []
        assert temps == []

    def test_non_image_file_skipped(self):
        parts = [
            Part(
                root=FilePart(
                    file=FileWithUri(
                        name="doc", uri="file:///tmp/doc.pdf", mime_type="application/pdf"
                    )
                )
            )
        ]
        attachments, temps = _parts_to_attachments(parts)
        assert attachments == []
        assert temps == []

    def test_multiple_images_mixed(self):
        b64 = base64.b64encode(b"bytes").decode()
        parts = [
            Part(root=TextPart(text="describe these")),
            Part(
                root=FilePart(
                    file=FileWithUri(name="img1", uri="file:///tmp/a.png", mime_type="image/png")
                )
            ),
            Part(root=FilePart(file=FileWithBytes(name="img2", bytes=b64, mime_type="image/gif"))),
        ]
        attachments, temps = _parts_to_attachments(parts)
        assert len(attachments) == 2
        assert attachments[0] == {"type": "file", "path": "/tmp/a.png"}
        # Second attachment is a temp file from bytes
        assert attachments[1]["type"] == "file"
        assert attachments[1]["path"].endswith(".gif")
        assert len(temps) == 1
        # Cleanup
        import os

        for p in temps:
            os.unlink(p)

    def test_jpeg_mime_accepted(self):
        b64 = base64.b64encode(b"data").decode()
        parts = [
            Part(root=FilePart(file=FileWithBytes(name="img", bytes=b64, mime_type="image/jpeg")))
        ]
        attachments, temps = _parts_to_attachments(parts)
        assert len(attachments) == 1
        assert attachments[0]["type"] == "file"
        assert attachments[0]["path"].endswith(".jpg")
        assert len(temps) == 1
        import os

        for p in temps:
            os.unlink(p)

    def test_webp_mime_accepted(self):
        b64 = base64.b64encode(b"data").decode()
        parts = [
            Part(root=FilePart(file=FileWithBytes(name="img", bytes=b64, mime_type="image/webp")))
        ]
        attachments, temps = _parts_to_attachments(parts)
        assert len(attachments) == 1
        assert attachments[0]["type"] == "file"
        assert attachments[0]["path"].endswith(".webp")
        assert len(temps) == 1
        import os

        for p in temps:
            os.unlink(p)
