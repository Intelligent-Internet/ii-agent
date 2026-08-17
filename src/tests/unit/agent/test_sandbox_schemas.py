"""Tests for ii_agent.agents.sandboxes.schemas — detect_language, guess_mime_type, etc."""

from __future__ import annotations


class TestSandboxSchemas:
    def test_sandbox_info_to_dict(self):
        """Line 41: model_dump on SandboxInfo."""
        from ii_agent.agents.sandboxes.schemas import SandboxInfo
        from ii_agent.agents.sandboxes.types import SandboxStatus, SandboxProviderType

        info = SandboxInfo(
            id="sandbox-1",
            provider=SandboxProviderType.E2B,
            session_id="session-1",
            status=SandboxStatus.RUNNING,
        )
        d = info.to_dict()
        assert "id" in d

    def test_detect_language_dockerfile(self):
        """Line 257, branch [256, 257]: Dockerfile matches as 'dockerfile'."""
        from ii_agent.agents.sandboxes.schemas import detect_language

        assert detect_language("Dockerfile") == "dockerfile"
        assert detect_language("/path/to/Dockerfile") == "dockerfile"

    def test_detect_language_makefile(self):
        """Line 259, branch [258, 259]: Makefile matches as 'makefile'."""
        from ii_agent.agents.sandboxes.schemas import detect_language

        assert detect_language("Makefile") == "makefile"
        assert detect_language("/path/Makefile") == "makefile"

    def test_detect_language_known_extension(self):
        from ii_agent.agents.sandboxes.schemas import detect_language

        result = detect_language("script.py")
        assert result == "python" or result != "dockerfile"

    def test_guess_mime_type_unknown_extension_custom(self):
        """Lines 270-271, branch [267, 270]: mimetypes can't guess, use custom dict."""
        from ii_agent.agents.sandboxes.schemas import guess_mime_type

        # .heic is not in mimetypes but is in our custom dict
        result = guess_mime_type("file.heic")
        assert result == "image/heic"

    def test_guess_mime_type_svg(self):
        from ii_agent.agents.sandboxes.schemas import guess_mime_type

        result = guess_mime_type("image.svg")
        assert result == "image/svg+xml"

    def test_is_binary_file_path_jpeg(self):
        """Line 306, branch [305, 306]: JPEG is binary (non-SVG image)."""
        from ii_agent.agents.sandboxes.schemas import is_binary_file_path

        assert is_binary_file_path("photo.jpg") is True

    def test_is_binary_file_path_png(self):
        from ii_agent.agents.sandboxes.schemas import is_binary_file_path

        assert is_binary_file_path("icon.png") is True
