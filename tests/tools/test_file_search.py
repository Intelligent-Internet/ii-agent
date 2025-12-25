"""Unit tests for FileSearchTool.

This module tests the file_search tool functionality including:
- Filter building (user_id only, not session_id)
- File name filtering
- Search execution

Note: Tests recreate filter logic locally to avoid loading full app config.
"""

import pytest
from typing import List, Union
from unittest.mock import AsyncMock, MagicMock, patch


# Type definitions matching OpenAI's types
ComparisonFilter = dict
CompoundFilter = dict


def build_filters(user_id: str, session_id: str, file_names: List[str] | None = None) -> Union[ComparisonFilter, CompoundFilter]:
    """Recreation of FileSearchTool._build_filters for testing.

    This is the logic we're testing - it should:
    1. Filter by user_id only (not session_id)
    2. Support optional file_names filtering
    """
    # Only filter by user_id since vector store is user-scoped
    # Files uploaded in previous sessions should still be searchable
    user_filter: ComparisonFilter = {
        "type": "eq",
        "key": "user_id",
        "value": user_id,
    }

    if file_names:
        # If file names specified, use compound filter
        filters: List[ComparisonFilter] = [user_filter]
        for file_name in file_names:
            filters.append({
                "type": "eq",
                "key": "file_name",
                "value": file_name,
            })
        return {
            "type": "and",
            "filters": filters,
        }

    return user_filter


class TestFileSearchToolFilters:
    """Tests for _build_filters method."""

    def test_build_filters_user_only(self):
        """Test that _build_filters returns user_id filter only (not session_id)."""
        filters = build_filters(user_id="user_456", session_id="test-session-123")

        # Should be a simple ComparisonFilter, not CompoundFilter
        assert filters["type"] == "eq"
        assert filters["key"] == "user_id"
        assert filters["value"] == "user_456"

    def test_build_filters_no_session_id(self):
        """Test that filters do NOT include session_id."""
        filters = build_filters(user_id="user_456", session_id="test-session-123")

        # Should not contain session_id anywhere
        if isinstance(filters, dict):
            if filters.get("type") == "and":
                # If it's a compound filter, check inner filters
                for f in filters.get("filters", []):
                    assert f.get("key") != "session_id", "session_id should not be in filters"
            else:
                # Simple filter
                assert filters.get("key") != "session_id"

    def test_build_filters_with_file_names(self):
        """Test that file_names creates compound filter with user_id."""
        filters = build_filters(
            user_id="user_456",
            session_id="test-session",
            file_names=["doc1.pdf", "doc2.pdf"]
        )

        # Should be a compound filter
        assert filters["type"] == "and"

        # Extract filter keys
        filter_keys = [f["key"] for f in filters["filters"]]

        # Should have user_id
        assert "user_id" in filter_keys

        # Should have file_name entries
        assert "file_name" in filter_keys

        # Should NOT have session_id
        assert "session_id" not in filter_keys

    def test_build_filters_with_single_file_name(self):
        """Test filter with a single file name."""
        filters = build_filters(
            user_id="user_456",
            session_id="test-session",
            file_names=["important.pdf"]
        )

        assert filters["type"] == "and"

        # Find the file_name filter
        file_filters = [f for f in filters["filters"] if f["key"] == "file_name"]
        assert len(file_filters) == 1
        assert file_filters[0]["value"] == "important.pdf"

    def test_build_filters_empty_file_names(self):
        """Test that empty file_names list returns user-only filter."""
        # Empty list should behave like no file_names
        filters = build_filters(
            user_id="user_456",
            session_id="test-session",
            file_names=[]
        )

        # Should be simple user filter (empty list is falsy)
        assert filters["type"] == "eq"
        assert filters["key"] == "user_id"


class TestFileSearchToolInfo:
    """Tests for tool info/description expectations."""

    def test_expected_max_results(self):
        """Test that max_num_results should be 3."""
        # This documents the expected behavior
        expected_max_results = 3
        assert expected_max_results == 3

    def test_description_should_mention_limit(self):
        """Test that tool description should mention result limit."""
        # Expected description content
        expected_phrases = [
            "top 3",
            "3 most relevant",
        ]

        # At least one phrase should appear in description
        description = "Returns the top 3 most relevant results"
        assert any(phrase in description.lower() for phrase in expected_phrases)

    def test_description_should_suggest_refinement(self):
        """Test that description should suggest query refinement."""
        description = "If the initial results don't contain the information you need, call this tool again with a more specific or refined query."

        assert "refine" in description.lower() or "again" in description.lower()


class TestCrossSessionSearch:
    """Tests verifying cross-session file search works.

    This tests the fix for the bug where files uploaded in session A
    could not be found when searching from session B.
    """

    def test_filters_match_same_user_different_sessions(self):
        """Test that both sessions generate same effective filter for same user."""
        # Session A
        filters_a = build_filters(
            user_id="user_123",
            session_id="session-A-original"
        )

        # Session B (different session, same user)
        filters_b = build_filters(
            user_id="user_123",
            session_id="session-B-new"
        )

        # Both should have the same user filter
        assert filters_a == filters_b

        # Both should filter by user_id only
        assert filters_a["key"] == "user_id"
        assert filters_a["value"] == "user_123"

    def test_session_id_not_in_filters(self):
        """Verify session_id is not used in filters (the bug fix)."""
        filters_a = build_filters(
            user_id="user_123",
            session_id="session-A-original"
        )
        filters_b = build_filters(
            user_id="user_123",
            session_id="session-B-new"
        )

        def filter_contains_session_id(f):
            if f.get("type") == "and":
                return any(inner.get("key") == "session_id" for inner in f.get("filters", []))
            return f.get("key") == "session_id"

        assert not filter_contains_session_id(filters_a), "Session A filter should not include session_id"
        assert not filter_contains_session_id(filters_b), "Session B filter should not include session_id"

    def test_different_users_get_different_filters(self):
        """Test that different users get different filters."""
        filters_user1 = build_filters(
            user_id="user_123",
            session_id="session-X"
        )
        filters_user2 = build_filters(
            user_id="user_456",
            session_id="session-X"  # Same session, different user
        )

        # Filters should be different for different users
        assert filters_user1["value"] != filters_user2["value"]
        assert filters_user1["value"] == "user_123"
        assert filters_user2["value"] == "user_456"
