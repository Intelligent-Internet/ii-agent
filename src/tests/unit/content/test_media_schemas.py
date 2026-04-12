"""Tests for ii_agent.content.media.schemas — get_image_limits."""

from __future__ import annotations


class TestContentMediaSchemas:
    def test_get_image_limits_default_for_unknown_tool(self):
        from ii_agent.content.media.schemas import get_image_limits

        result = get_image_limits("Unknown Tool")
        assert result == (1, 4)

    def test_get_image_limits_known_group_photo(self):
        from ii_agent.content.media.schemas import get_image_limits

        result = get_image_limits("Group Photo")
        assert result == (2, 4)
