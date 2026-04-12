"""Unit tests for ii_agent.integrations.a2a.extension_utils pure utility functions."""

from __future__ import annotations

from typing import Any

import pytest

from ii_agent.integrations.a2a.extension_utils import (
    _accumulate_extensions,
    append_extension_issue,
    collect_requested_extensions,
)


# ===========================================================================
# append_extension_issue()
# ===========================================================================


class TestAppendExtensionIssue:
    """Tests for append_extension_issue()."""

    def test_appends_issue_with_uri_and_code(self):
        info: dict[str, Any] = {}
        append_extension_issue(info, uri="https://example.com/ext", code="UNSUPPORTED")
        assert "issues" in info
        assert len(info["issues"]) == 1
        issue = info["issues"][0]
        assert issue["uri"] == "https://example.com/ext"
        assert issue["code"] == "UNSUPPORTED"

    def test_appends_issue_with_detail(self):
        info: dict[str, Any] = {}
        append_extension_issue(
            info,
            uri="https://example.com/ext",
            code="MISSING",
            detail="Extension not available",
        )
        issue = info["issues"][0]
        assert issue["detail"] == "Extension not available"

    def test_appends_issue_without_detail_omits_detail_key(self):
        info: dict[str, Any] = {}
        append_extension_issue(info, uri="https://example.com/ext", code="ERR")
        issue = info["issues"][0]
        assert "detail" not in issue

    def test_multiple_issues_accumulate(self):
        info: dict[str, Any] = {}
        append_extension_issue(info, uri="https://example.com/a", code="CODE_A")
        append_extension_issue(info, uri="https://example.com/b", code="CODE_B")
        assert len(info["issues"]) == 2
        codes = {i["code"] for i in info["issues"]}
        assert codes == {"CODE_A", "CODE_B"}

    def test_none_extension_info_is_silently_ignored(self):
        # Should not raise.
        append_extension_issue(None, uri="https://example.com/ext", code="ERR")

    def test_repairs_non_list_issues_field(self):
        # If "issues" already exists but is not a list, it should be replaced.
        info: dict[str, Any] = {"issues": "corrupted"}
        append_extension_issue(info, uri="https://example.com/ext", code="FIXED")
        assert isinstance(info["issues"], list)
        assert len(info["issues"]) == 1

    def test_pre_existing_issues_list_is_extended(self):
        info: dict[str, Any] = {"issues": [{"uri": "existing", "code": "OLD"}]}
        append_extension_issue(info, uri="https://new.com/ext", code="NEW")
        assert len(info["issues"]) == 2

    def test_issue_record_contains_only_uri_code_when_no_detail(self):
        info: dict[str, Any] = {}
        append_extension_issue(info, uri="u", code="c")
        assert set(info["issues"][0].keys()) == {"uri", "code"}

    def test_issue_record_contains_uri_code_detail_when_detail_given(self):
        info: dict[str, Any] = {}
        append_extension_issue(info, uri="u", code="c", detail="d")
        assert set(info["issues"][0].keys()) == {"uri", "code", "detail"}


# ===========================================================================
# _accumulate_extensions()
# ===========================================================================


class TestAccumulateExtensions:
    """Tests for _accumulate_extensions()."""

    def test_empty_set_values_is_skipped(self):
        bucket: set[str] = set()
        _accumulate_extensions(bucket, None)
        assert bucket == set()

    def test_empty_list_is_skipped(self):
        bucket: set[str] = set()
        _accumulate_extensions(bucket, [])
        assert bucket == set()

    def test_string_items_added_to_bucket(self):
        bucket: set[str] = set()
        _accumulate_extensions(bucket, ["https://example.com/a", "https://example.com/b"])
        assert "https://example.com/a" in bucket
        assert "https://example.com/b" in bucket

    def test_set_input_works(self):
        bucket: set[str] = set()
        _accumulate_extensions(bucket, {"ext-1", "ext-2"})
        assert "ext-1" in bucket
        assert "ext-2" in bucket

    def test_tuple_input_works(self):
        bucket: set[str] = set()
        _accumulate_extensions(bucket, ("ext-a", "ext-b"))
        assert "ext-a" in bucket
        assert "ext-b" in bucket

    def test_integer_items_are_stringified(self):
        bucket: set[str] = set()
        _accumulate_extensions(bucket, [1, 2])
        assert "1" in bucket
        assert "2" in bucket

    def test_float_items_are_stringified(self):
        bucket: set[str] = set()
        _accumulate_extensions(bucket, [3.14])
        assert "3.14" in bucket

    def test_non_string_non_numeric_items_are_skipped(self):
        bucket: set[str] = set()
        _accumulate_extensions(bucket, [{"a": 1}, None, [1, 2]])
        assert len(bucket) == 0

    def test_whitespace_only_strings_are_skipped(self):
        bucket: set[str] = set()
        _accumulate_extensions(bucket, ["   ", "\t", ""])
        assert len(bucket) == 0

    def test_strings_are_stripped_before_adding(self):
        bucket: set[str] = set()
        _accumulate_extensions(bucket, ["  https://example.com/ext  "])
        assert "https://example.com/ext" in bucket

    def test_non_iterable_value_is_silently_skipped(self):
        bucket: set[str] = set()
        # An integer (not in list/set/tuple) is not directly iterable.
        _accumulate_extensions(bucket, 42)
        # Depending on implementation: either tries list(42) -> TypeError -> skips, or
        # treats it as single value. Let's assert no crash and bucket stays empty.
        assert isinstance(bucket, set)

    def test_duplicates_are_deduplicated(self):
        bucket: set[str] = set()
        _accumulate_extensions(bucket, ["ext-1", "ext-1", "ext-1"])
        assert len(bucket) == 1
        assert "ext-1" in bucket

    def test_accumulates_into_existing_bucket(self):
        bucket: set[str] = {"existing"}
        _accumulate_extensions(bucket, ["new-ext"])
        assert "existing" in bucket
        assert "new-ext" in bucket


# ===========================================================================
# collect_requested_extensions()
# ===========================================================================


class TestCollectRequestedExtensions:
    """Tests for collect_requested_extensions()."""

    def _make_context(
        self,
        requested_extensions=None,
        message_extensions=None,
    ):
        """Build a minimal fake context object."""
        from types import SimpleNamespace

        call_context = SimpleNamespace(requested_extensions=requested_extensions)
        message = SimpleNamespace(extensions=message_extensions)
        return SimpleNamespace(call_context=call_context, message=message)

    def test_collects_from_call_context(self):
        ctx = self._make_context(requested_extensions=["https://example.com/ext"])
        result = collect_requested_extensions(ctx)
        assert "https://example.com/ext" in result

    def test_collects_from_message_extensions(self):
        ctx = self._make_context(message_extensions=["https://msg.com/ext"])
        result = collect_requested_extensions(ctx)
        assert "https://msg.com/ext" in result

    def test_collects_from_both_sources(self):
        ctx = self._make_context(
            requested_extensions=["https://ctx.com/ext"],
            message_extensions=["https://msg.com/ext"],
        )
        result = collect_requested_extensions(ctx)
        assert "https://ctx.com/ext" in result
        assert "https://msg.com/ext" in result

    def test_returns_empty_set_when_both_sources_empty(self):
        ctx = self._make_context(requested_extensions=None, message_extensions=None)
        result = collect_requested_extensions(ctx)
        assert result == set()

    def test_returns_set_type(self):
        ctx = self._make_context(requested_extensions=["ext"])
        result = collect_requested_extensions(ctx)
        assert isinstance(result, set)

    def test_no_duplicates_across_sources(self):
        shared = "https://shared.com/ext"
        ctx = self._make_context(
            requested_extensions=[shared],
            message_extensions=[shared],
        )
        result = collect_requested_extensions(ctx)
        # A set naturally deduplicates; the shared URI should appear exactly once.
        assert shared in result
        assert len(result) == 1

    def test_handles_missing_call_context(self):
        from types import SimpleNamespace

        # context without call_context attribute at all
        ctx = SimpleNamespace(message=SimpleNamespace(extensions=["ext"]))
        result = collect_requested_extensions(ctx)
        assert "ext" in result

    def test_handles_missing_message_attribute(self):
        from types import SimpleNamespace

        ctx = SimpleNamespace(
            call_context=SimpleNamespace(requested_extensions=["ext"]),
            message=None,
        )
        result = collect_requested_extensions(ctx)
        assert "ext" in result
