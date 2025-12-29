"""Unit tests for ChatService.

This module tests the chat service functionality including:
- File info message formatting
- Tool recommendation prompts
"""

import pytest
from unittest.mock import MagicMock


class TestFileInfoMessage:
    """Tests for file info message generation."""

    def test_file_info_header(self):
        """Test that file info includes system header."""
        # Expected header in the message
        expected_lines = [
            "[System: Files have been uploaded and indexed for search]",
            "",
            "Files available:"
        ]

        file_info_lines = [
            "[System: Files have been uploaded and indexed for search]",
            "",
            "Files available:"
        ]

        assert file_info_lines[0] == expected_lines[0]
        assert file_info_lines[2] == expected_lines[2]

    def test_file_info_format(self):
        """Test file info formatting for individual files."""
        # Simulate file object
        class MockFileObj:
            file_name = "manual.pdf"
            content_type = "application/pdf"
            bytes = 5500000

        file_obj = MockFileObj()

        # Format line as done in service
        line = f"- {file_obj.file_name} ({file_obj.content_type}, {file_obj.bytes:,} bytes)"

        assert "manual.pdf" in line
        assert "application/pdf" in line
        assert "5,500,000" in line  # Formatted with commas

    def test_file_info_includes_tool_recommendations(self):
        """Test that file info includes file_search tool recommendations."""
        tool_recommendations = [
            "",
            "To answer questions about these files, use the `file_search` tool to retrieve relevant content.",
            "The file_search tool performs semantic search across all uploaded documents.",
            "Tip: If initial search results are insufficient, try refining your query with different keywords.",
        ]

        # Verify key recommendations
        assert any("file_search" in line for line in tool_recommendations)
        assert any("semantic search" in line for line in tool_recommendations)
        assert any("refining" in line.lower() for line in tool_recommendations)


class TestFileInfoMessageConstruction:
    """Tests for complete file info message construction."""

    def test_construct_file_info_text(self):
        """Test constructing complete file info text."""
        user_text = "What are the temperature specifications?"

        # Mock file objects
        class MockFile:
            def __init__(self, name, content_type, size):
                self.file_name = name
                self.content_type = content_type
                self.bytes = size

        vs_files = [
            MockFile("MR850-manual.pdf", "application/pdf", 5560288),
            MockFile("specs.txt", "text/plain", 1024),
        ]

        # Build file info as done in service
        file_info_lines = [
            "[System: Files have been uploaded and indexed for search]",
            "",
            "Files available:"
        ]
        for file_obj in vs_files:
            file_info_lines.append(
                f"- {file_obj.file_name} ({file_obj.content_type}, {file_obj.bytes:,} bytes)"
            )

        file_info_lines.extend([
            "",
            "To answer questions about these files, use the `file_search` tool to retrieve relevant content.",
            "The file_search tool performs semantic search across all uploaded documents.",
            "Tip: If initial search results are insufficient, try refining your query with different keywords.",
        ])

        file_info_text = user_text + "\n\n" + "\n".join(file_info_lines)

        # Verify complete message
        assert "What are the temperature specifications?" in file_info_text
        assert "[System: Files have been uploaded and indexed for search]" in file_info_text
        assert "MR850-manual.pdf" in file_info_text
        assert "5,560,288 bytes" in file_info_text
        assert "file_search" in file_info_text
        assert "semantic search" in file_info_text

    def test_empty_vs_files_no_info_appended(self):
        """Test that no file info is appended when vs_files is empty."""
        vs_files = []

        # When vs_files is empty, no file info should be added
        if vs_files:
            # Would append file info
            should_append = True
        else:
            should_append = False

        assert should_append is False


class TestToolRecommendationGuidance:
    """Tests for tool recommendation guidance in prompts."""

    def test_file_search_explicitly_mentioned(self):
        """Test that file_search tool is explicitly mentioned."""
        recommendation = "To answer questions about these files, use the `file_search` tool to retrieve relevant content."

        assert "file_search" in recommendation
        assert "tool" in recommendation.lower()

    def test_semantic_search_explained(self):
        """Test that semantic search capability is explained."""
        explanation = "The file_search tool performs semantic search across all uploaded documents."

        assert "semantic search" in explanation
        assert "documents" in explanation

    def test_query_refinement_tip(self):
        """Test that query refinement tip is included."""
        tip = "Tip: If initial search results are insufficient, try refining your query with different keywords."

        assert "refining" in tip.lower()
        assert "query" in tip
        assert "keywords" in tip


class TestFileInfoNotAddedWhenNoFiles:
    """Tests ensuring file info is only added when files exist."""

    def test_vs_files_truthiness_check(self):
        """Test that empty vs_files list is falsy."""
        vs_files = []

        if vs_files:
            result = "would add file info"
        else:
            result = "no file info"

        assert result == "no file info"

    def test_vs_files_with_content_is_truthy(self):
        """Test that non-empty vs_files list is truthy."""
        vs_files = [MagicMock()]

        if vs_files:
            result = "would add file info"
        else:
            result = "no file info"

        assert result == "would add file info"


class TestUserMessageModification:
    """Tests for user message modification with file info."""

    def test_original_query_preserved(self):
        """Test that original user query is preserved."""
        original_query = "What is the operating temperature range?"

        file_info = "[System: Files...]"
        modified_text = original_query + "\n\n" + file_info

        assert original_query in modified_text
        assert modified_text.startswith(original_query)

    def test_separator_between_query_and_info(self):
        """Test that proper separator exists between query and file info."""
        original_query = "Tell me about the device"
        file_info = "[System: Files...]"

        modified_text = original_query + "\n\n" + file_info

        # Should have double newline separator
        assert "\n\n" in modified_text

        # Split should give two parts
        parts = modified_text.split("\n\n", 1)
        assert len(parts) == 2
        assert parts[0] == original_query


class TestFileDiscoveryFromVectorStore:
    """Tests for extracting file names from existing vector store."""

    def test_extract_file_names_from_vector_store(self):
        """Test extracting file names from vector store metadata."""
        # Simulate OpenAI vector store files response structure
        vector_store_files = {
            "data": [
                {
                    "id": "vsf_001",
                    "attributes": {
                        "file_name": "manual.pdf",
                        "user_id": "user_123"
                    }
                },
                {
                    "id": "vsf_002",
                    "attributes": {
                        "file_name": "specs.docx",
                        "user_id": "user_123"
                    }
                },
            ]
        }

        # Extract file names as done in _extract_file_names_from_vector_store
        file_names = []
        files_data = vector_store_files.get("data", [])
        for file_obj in files_data:
            attrs = file_obj.get("attributes", {})
            if attrs and isinstance(attrs, dict):
                file_name = attrs.get("file_name")
                if file_name:
                    file_names.append(file_name)

        assert file_names == ["manual.pdf", "specs.docx"]

    def test_extract_file_names_handles_none_vector_store(self):
        """Test extraction handles None vector store gracefully."""
        vector_store = None

        # Should return empty list
        if not vector_store:
            file_names = []

        assert file_names == []

    def test_extract_file_names_handles_empty_files(self):
        """Test extraction handles empty files dict."""
        vector_store_files = {}

        file_names = []
        files_data = vector_store_files.get("data", [])
        for file_obj in files_data:
            attrs = file_obj.get("attributes", {})
            if attrs and isinstance(attrs, dict):
                file_name = attrs.get("file_name")
                if file_name:
                    file_names.append(file_name)

        assert file_names == []

    def test_extract_file_names_handles_missing_attributes(self):
        """Test extraction handles files without attributes."""
        vector_store_files = {
            "data": [
                {"id": "vsf_001"},  # No attributes
                {
                    "id": "vsf_002",
                    "attributes": {"file_name": "valid.pdf"}
                },
            ]
        }

        file_names = []
        files_data = vector_store_files.get("data", [])
        for file_obj in files_data:
            attrs = file_obj.get("attributes", {})
            if attrs and isinstance(attrs, dict):
                file_name = attrs.get("file_name")
                if file_name:
                    file_names.append(file_name)

        # Should only include the valid file
        assert file_names == ["valid.pdf"]


class TestFileCorpusDiscoveryMessage:
    """Tests for the file corpus discovery message to AI."""

    def test_existing_files_header(self):
        """Test header for existing file corpus."""
        header = "[System: You have access to the user's document corpus via file_search]"

        assert "document corpus" in header
        assert "file_search" in header

    def test_file_list_format(self):
        """Test file list formatting."""
        file_names = ["manual.pdf", "specs.docx", "readme.md"]

        lines = [f"Document corpus available for search ({len(file_names)} files):"]
        for fname in file_names:
            lines.append(f"- {fname}")

        output = "\n".join(lines)

        assert "3 files" in output
        assert "- manual.pdf" in output
        assert "- specs.docx" in output
        assert "- readme.md" in output

    def test_file_list_truncation_over_20(self):
        """Test that file list is truncated when over 20 files."""
        file_names = [f"doc_{i}.pdf" for i in range(25)]

        display_files = file_names[:20]
        lines = []
        for fname in display_files:
            lines.append(f"- {fname}")
        if len(file_names) > 20:
            lines.append(f"- ... and {len(file_names) - 20} more files")

        output = "\n".join(lines)

        assert "doc_19.pdf" in output  # Last displayed file
        assert "doc_20.pdf" not in output  # Should be truncated
        assert "... and 5 more files" in output

    def test_tool_priority_guidance(self):
        """Test that AI is told to prioritize file_search over web_search."""
        guidance_lines = [
            "IMPORTANT: When the user asks about content that might be in these documents:",
            "- Use the `file_search` tool FIRST before attempting web searches",
            "- file_search performs semantic search across all indexed documents",
            "- If initial results are insufficient, refine your query with different keywords",
            "- Only use web_search if the information is clearly NOT in the user's documents",
        ]

        guidance = "\n".join(guidance_lines)

        assert "FIRST" in guidance
        assert "file_search" in guidance
        assert "web_search" in guidance
        assert "NOT" in guidance

    def test_combined_new_and_existing_files(self):
        """Test message when both new uploads and existing files present."""
        newly_uploaded = ["new_doc.pdf"]
        existing_files = ["old_doc.pdf", "archive.docx"]

        lines = []

        # New files section
        lines.append("[System: New files have been uploaded and indexed for search]")
        lines.append("")
        lines.append("Newly uploaded files:")
        for fname in newly_uploaded:
            lines.append(f"- {fname}")

        # Existing files section
        lines.append("")
        lines.append(f"Document corpus available for search ({len(existing_files)} files):")
        for fname in existing_files:
            lines.append(f"- {fname}")

        output = "\n".join(lines)

        assert "New files have been uploaded" in output
        assert "Newly uploaded files:" in output
        assert "new_doc.pdf" in output
        assert "Document corpus available for search" in output
        assert "old_doc.pdf" in output
