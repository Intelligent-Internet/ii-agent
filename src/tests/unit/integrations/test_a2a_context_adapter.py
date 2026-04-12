"""Unit tests for ii_agent.integrations.a2a.context_adapter pure utility functions."""

from __future__ import annotations

from typing import Any

import pytest

from ii_agent.integrations.a2a.context_adapter import (
    _as_bool,
    _as_int,
    _as_str,
    _deep_merge,
    _extract_mapping,
    _pick_first_key,
)


# ===========================================================================
# _as_bool()
# ===========================================================================


class TestAsBool:
    """Tests for _as_bool()."""

    # --- native bool ---

    def test_true_bool_returns_true(self):
        assert _as_bool(True) is True

    def test_false_bool_returns_false(self):
        assert _as_bool(False) is False

    # --- truthy string variants ---

    def test_string_true_returns_true(self):
        assert _as_bool("true") is True

    def test_string_True_uppercase_returns_true(self):
        assert _as_bool("True") is True

    def test_string_TRUE_returns_true(self):
        assert _as_bool("TRUE") is True

    def test_string_1_returns_true(self):
        assert _as_bool("1") is True

    def test_string_yes_returns_true(self):
        assert _as_bool("yes") is True

    def test_string_YES_returns_true(self):
        assert _as_bool("YES") is True

    # --- falsy string variants ---

    def test_string_false_returns_false(self):
        assert _as_bool("false") is False

    def test_string_False_uppercase_returns_false(self):
        assert _as_bool("False") is False

    def test_string_0_returns_false(self):
        assert _as_bool("0") is False

    def test_string_no_returns_false(self):
        assert _as_bool("no") is False

    def test_string_NO_returns_false(self):
        assert _as_bool("NO") is False

    # --- string with whitespace ---

    def test_string_with_leading_whitespace_true(self):
        assert _as_bool("  true  ") is True

    def test_string_with_leading_whitespace_false(self):
        assert _as_bool("  false  ") is False

    # --- non-string truthy/falsy fallback ---

    def test_integer_1_uses_bool_coercion(self):
        assert _as_bool(1) is True

    def test_integer_0_uses_bool_coercion(self):
        assert _as_bool(0) is False

    def test_none_uses_bool_coercion(self):
        assert _as_bool(None) is False

    def test_empty_string_uses_bool_coercion(self):
        # An unrecognized string falls through to bool("..."), which is True
        # for non-empty and False for empty.
        assert _as_bool("") is False

    def test_unrecognized_nonempty_string_coerces_truthy(self):
        # Any string that is not in the recognized sets falls through to bool(value).
        assert _as_bool("maybe") is True

    def test_list_uses_bool_coercion(self):
        assert _as_bool([1, 2]) is True
        assert _as_bool([]) is False


# ===========================================================================
# _as_int()
# ===========================================================================


class TestAsInt:
    """Tests for _as_int()."""

    def test_none_returns_none(self):
        assert _as_int(None) is None

    def test_integer_returns_same(self):
        assert _as_int(42) == 42

    def test_zero_returns_zero(self):
        assert _as_int(0) == 0

    def test_negative_integer_returns_same(self):
        assert _as_int(-7) == -7

    def test_string_integer_is_converted(self):
        assert _as_int("120") == 120

    def test_string_negative_integer_is_converted(self):
        assert _as_int("-5") == -5

    def test_float_is_truncated_to_int(self):
        # int(3.9) == 3
        assert _as_int(3.9) == 3

    def test_invalid_string_returns_none(self):
        assert _as_int("not-a-number") is None

    def test_empty_string_returns_none(self):
        assert _as_int("") is None

    def test_object_that_cannot_convert_returns_none(self):
        assert _as_int(object()) is None

    def test_string_zero_is_converted(self):
        assert _as_int("0") == 0


# ===========================================================================
# _as_str()
# ===========================================================================


class TestAsStr:
    """Tests for _as_str()."""

    def test_none_returns_none(self):
        assert _as_str(None) is None

    def test_string_returns_same(self):
        assert _as_str("hello") == "hello"

    def test_empty_string_returns_empty_string(self):
        assert _as_str("") == ""

    def test_integer_is_stringified(self):
        assert _as_str(42) == "42"

    def test_float_is_stringified(self):
        result = _as_str(3.14)
        assert result is not None
        assert "3.14" in result

    def test_bool_true_is_stringified(self):
        assert _as_str(True) == "True"

    def test_bool_false_is_stringified(self):
        assert _as_str(False) == "False"

    def test_list_is_stringified(self):
        result = _as_str([1, 2, 3])
        assert result is not None
        assert isinstance(result, str)


# ===========================================================================
# _deep_merge()
# ===========================================================================


class TestDeepMerge:
    """Tests for _deep_merge()."""

    def test_merges_flat_dicts(self):
        target: dict[str, Any] = {"a": 1}
        source: dict[str, Any] = {"b": 2}
        _deep_merge(target, source)
        assert target == {"a": 1, "b": 2}

    def test_source_overwrites_scalar_in_target(self):
        target: dict[str, Any] = {"a": 1}
        source: dict[str, Any] = {"a": 99}
        _deep_merge(target, source)
        assert target["a"] == 99

    def test_nested_dicts_are_recursively_merged(self):
        target: dict[str, Any] = {"cfg": {"x": 1, "y": 2}}
        source: dict[str, Any] = {"cfg": {"y": 99, "z": 3}}
        _deep_merge(target, source)
        assert target["cfg"] == {"x": 1, "y": 99, "z": 3}

    def test_deeply_nested_merge(self):
        target: dict[str, Any] = {"level1": {"level2": {"a": 1}}}
        source: dict[str, Any] = {"level1": {"level2": {"b": 2}}}
        _deep_merge(target, source)
        assert target["level1"]["level2"] == {"a": 1, "b": 2}

    def test_non_dict_in_source_replaces_dict_in_target(self):
        target: dict[str, Any] = {"key": {"nested": 1}}
        source: dict[str, Any] = {"key": "scalar"}
        _deep_merge(target, source)
        assert target["key"] == "scalar"

    def test_dict_in_source_replaces_non_dict_in_target(self):
        target: dict[str, Any] = {"key": "scalar"}
        source: dict[str, Any] = {"key": {"nested": 1}}
        _deep_merge(target, source)
        assert target["key"] == {"nested": 1}

    def test_empty_source_leaves_target_unchanged(self):
        target: dict[str, Any] = {"a": 1}
        _deep_merge(target, {})
        assert target == {"a": 1}

    def test_empty_target_gets_all_source_keys(self):
        target: dict[str, Any] = {}
        _deep_merge(target, {"x": 10, "y": 20})
        assert target == {"x": 10, "y": 20}

    def test_merges_list_values_by_replacement(self):
        target: dict[str, Any] = {"items": [1, 2]}
        source: dict[str, Any] = {"items": [3, 4, 5]}
        _deep_merge(target, source)
        assert target["items"] == [3, 4, 5]


# ===========================================================================
# _pick_first_key()
# ===========================================================================


class TestPickFirstKey:
    """Tests for _pick_first_key()."""

    def test_returns_value_for_first_matching_key(self):
        data = {"ii-agent": {"tool_args": {}}, "other": "x"}
        result = _pick_first_key(data, ("ii-agent", "ii_agent"))
        assert result == {"tool_args": {}}

    def test_returns_value_for_second_matching_key_when_first_absent(self):
        data = {"ii_agent": {"tool_args": {}}}
        result = _pick_first_key(data, ("ii-agent", "ii_agent", "iiAgent"))
        assert result == {"tool_args": {}}

    def test_returns_none_when_no_key_matches(self):
        data = {"other": "value"}
        result = _pick_first_key(data, ("ii-agent", "ii_agent", "iiAgent"))
        assert result is None

    def test_returns_none_for_empty_data(self):
        result = _pick_first_key({}, ("ii-agent",))
        assert result is None

    def test_returns_none_for_empty_keys_list(self):
        result = _pick_first_key({"ii-agent": {}}, ())
        assert result is None

    def test_does_not_return_none_value_stored_under_key(self):
        # If the stored value is None the key still exists but should not be returned.
        # The implementation skips None values.
        data = {"ii-agent": None, "ii_agent": {"k": "v"}}
        result = _pick_first_key(data, ("ii-agent", "ii_agent"))
        # Because "ii-agent" maps to None, the function moves on to "ii_agent".
        assert result == {"k": "v"}

    def test_returns_value_regardless_of_other_keys_present(self):
        data = {"unrelated": 42, "iiAgent": {"sandbox": {"reuse": True}}}
        result = _pick_first_key(data, ("ii-agent", "ii_agent", "iiAgent"))
        assert result == {"sandbox": {"reuse": True}}


# ===========================================================================
# _extract_mapping()
# ===========================================================================


class TestExtractMapping:
    """Tests for _extract_mapping()."""

    def test_returns_dict_for_first_matching_key(self):
        source = {"tool_args": {"web_search": True}}
        result = _extract_mapping(source, ("tool_args", "toolArgs"))
        assert result == {"web_search": True}

    def test_falls_back_to_second_alias(self):
        source = {"toolArgs": {"image_search": False}}
        result = _extract_mapping(source, ("tool_args", "toolArgs"))
        assert result == {"image_search": False}

    def test_returns_empty_dict_when_no_key_matches(self):
        source = {"other": {"x": 1}}
        result = _extract_mapping(source, ("tool_args", "toolArgs"))
        assert result == {}

    def test_returns_empty_dict_for_empty_source(self):
        result = _extract_mapping({}, ("sandbox", "sandbox_options"))
        assert result == {}

    def test_ignores_non_mapping_values(self):
        # If the key exists but maps to a non-Mapping, it should be skipped.
        source = {"tool_args": "not-a-dict", "toolArgs": {"real": True}}
        result = _extract_mapping(source, ("tool_args", "toolArgs"))
        assert result == {"real": True}

    def test_returns_copy_not_original_reference(self):
        inner = {"key": "val"}
        source = {"sandbox": inner}
        result = _extract_mapping(source, ("sandbox",))
        result["extra"] = "added"
        # Original dict should be unchanged.
        assert "extra" not in inner

    def test_returns_empty_dict_when_keys_list_is_empty(self):
        source = {"sandbox": {"reuse": True}}
        result = _extract_mapping(source, ())
        assert result == {}
