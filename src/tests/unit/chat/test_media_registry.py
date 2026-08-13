"""Tests for ii_agent.chat.media.registry — register_handler, get_handler, list_handlers, is_handler_registered."""

from __future__ import annotations


class TestMediaRegistry:
    def setup_method(self):
        """Reset the registry between tests."""
        import ii_agent.chat.media.registry as reg

        reg._HANDLER_REGISTRY.clear()

    def test_register_handler_decorator(self):
        """Lines 30-32, 34: decorator registers handler class."""
        from ii_agent.chat.media.registry import register_handler, _HANDLER_REGISTRY

        @register_handler("my_type")
        class MyHandler:
            pass

        assert "my_type" in _HANDLER_REGISTRY
        assert _HANDLER_REGISTRY["my_type"] is MyHandler

    def test_register_handler_returns_class(self):
        """Decorator returns the class unchanged."""
        from ii_agent.chat.media.registry import register_handler

        @register_handler("img")
        class ImgHandler:
            pass

        assert ImgHandler.__name__ == "ImgHandler"

    def test_get_handler_found(self):
        """Line 47: returns handler when registered."""
        from ii_agent.chat.media.registry import register_handler, get_handler

        @register_handler("video")
        class VideoHandler:
            pass

        assert get_handler("video") is VideoHandler

    def test_get_handler_not_found(self):
        """Line 47 None branch: returns None for unknown type."""
        from ii_agent.chat.media.registry import get_handler

        assert get_handler("nonexistent_xyz") is None

    def test_list_handlers(self):
        """Line 57: returns list of registered names."""
        from ii_agent.chat.media.registry import register_handler, list_handlers

        @register_handler("audio")
        class AudioHandler:
            pass

        names = list_handlers()
        assert "audio" in names

    def test_list_handlers_empty(self):
        """Line 57: empty list when nothing registered."""
        from ii_agent.chat.media.registry import list_handlers

        assert list_handlers() == []

    def test_is_handler_registered_true(self):
        """Line 70: registered handler → True."""
        from ii_agent.chat.media.registry import register_handler, is_handler_registered

        @register_handler("poster")
        class PosterHandler:
            pass

        assert is_handler_registered("poster") is True

    def test_is_handler_registered_false(self):
        """Line 70: unknown handler → False."""
        from ii_agent.chat.media.registry import is_handler_registered

        assert is_handler_registered("unknown_xyz") is False
