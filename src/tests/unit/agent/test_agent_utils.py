"""Tests for ii_agent.agents.utils — common.check_type_compatibility + message.get_text_from_message."""

from __future__ import annotations


class TestCheckTypeCompatibilityExtra:
    def test_list_type_with_non_list_value(self):
        """Line 78, branch [77, 78]: origin is list but value is not a list."""
        from typing import List
        from ii_agent.agents.utils.common import check_type_compatibility

        result = check_type_compatibility("not_a_list", List[int])
        assert result is False

    def test_bare_list_type_with_non_list(self):
        from ii_agent.agents.utils.common import check_type_compatibility

        result = check_type_compatibility("not_a_list", list)
        assert result is False

    def test_custom_class_type_isinstance_check(self):
        """Lines 90-91, branch [87, 90]: expected_type is a custom class."""
        from ii_agent.agents.utils.common import check_type_compatibility

        class MyClass:
            pass

        instance = MyClass()
        result = check_type_compatibility(instance, MyClass)
        assert result is True

    def test_custom_class_type_not_instance(self):
        """Lines 90-91: isinstance returns False for wrong type."""
        from ii_agent.agents.utils.common import check_type_compatibility

        class MyClass:
            pass

        result = check_type_compatibility(42, MyClass)
        assert result is False

    def test_type_error_returns_true(self):
        """Lines 92-93, branch for TypeError: isinstance raises → return True."""
        from ii_agent.agents.utils.common import check_type_compatibility

        # Passing a non-type as expected_type causes TypeError in isinstance
        result = check_type_compatibility(42, 42)  # type: ignore
        assert result is True


class TestGetTextFromMessageEdgeCases:
    def test_get_text_with_none_returns_empty(self):
        """Lines 116, 118 + branches [111,116] [116,118]: None falls through to empty."""
        from ii_agent.agents.utils.message import get_text_from_message

        result = get_text_from_message(None)  # type: ignore
        assert result == ""

    def test_get_text_with_integer_returns_empty(self):
        """Non-standard type falls through all checks → empty."""
        from ii_agent.agents.utils.message import get_text_from_message

        result = get_text_from_message(42)  # type: ignore
        assert result == ""
