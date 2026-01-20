"""Unit tests for OpenAI tool result processing.

Tests the _process_tool_result method which handles tool outputs,
particularly ensuring images are not included in tool messages
(OpenAI API limitation).
"""

import pytest
from unittest.mock import MagicMock


class TestProcessToolResult:
    """Tests for OpenAI _process_tool_result method behavior.
    
    These tests verify the logic without needing to import the full OpenAI client
    which requires API keys and environment setup.
    """

    def _process_tool_result_logic(self, tool_output):
        """Simulate the _process_tool_result logic from OpenAIDirectClient.
        
        This extracts the pure logic to test without OpenAI client dependencies.
        """
        content = tool_output
        if isinstance(tool_output, list):
            processed_content = []
            has_images = False
            for block in tool_output:
                if isinstance(block, dict) and block.get("type") == "image":
                    # Skip image blocks - OpenAI doesn't allow images in tool messages
                    has_images = True
                    continue
                else:
                    processed_content.append(block)
            
            if has_images:
                # If there were images, add a note that they were processed
                if not processed_content:
                    content = "Tool executed successfully. Image results were processed."
                else:
                    content = processed_content
            else:
                content = processed_content
        return content

    def test_string_content_unchanged(self):
        """Test that string content passes through unchanged."""
        result = self._process_tool_result_logic("Simple text result")
        assert result == "Simple text result"

    def test_list_without_images_unchanged(self):
        """Test that list content without images passes through."""
        tool_output = [
            {"type": "text", "text": "Some text"},
            {"type": "code", "code": "print('hello')"},
        ]
        result = self._process_tool_result_logic(tool_output)
        assert result == tool_output

    def test_image_blocks_stripped_from_tool_output(self):
        """Test that image blocks are removed from tool results."""
        tool_output = [
            {"type": "text", "text": "Screenshot captured"},
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": "base64encodeddata..."
                }
            },
        ]
        result = self._process_tool_result_logic(tool_output)
        
        # Should only contain the text block
        assert len(result) == 1
        assert result[0]["type"] == "text"

    def test_only_images_returns_placeholder_message(self):
        """Test that tool result with only images returns placeholder text."""
        tool_output = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": "base64encodeddata..."
                }
            },
        ]
        result = self._process_tool_result_logic(tool_output)
        
        assert result == "Tool executed successfully. Image results were processed."

    def test_multiple_images_all_stripped(self):
        """Test that multiple image blocks are all removed."""
        tool_output = [
            {"type": "text", "text": "Captured 2 screenshots"},
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "img1"}},
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "img2"}},
        ]
        result = self._process_tool_result_logic(tool_output)
        
        assert len(result) == 1
        assert result[0]["text"] == "Captured 2 screenshots"

    def test_non_dict_list_items_preserved(self):
        """Test that non-dict items in list are preserved."""
        tool_output = ["text item", 123, {"type": "text", "text": "dict item"}]
        result = self._process_tool_result_logic(tool_output)
        
        assert result == tool_output

    def test_empty_list_unchanged(self):
        """Test that empty list passes through."""
        result = self._process_tool_result_logic([])
        assert result == []


class TestContentMerging:
    """Tests for content merging logic in message processing.
    
    OpenAI message content can be either string or list format.
    These tests verify the merging behavior.
    """

    def _merge_content_logic(self, existing_content, new_content):
        """Simulate the content merging logic from OpenAIDirectClient.
        
        This extracts the pure logic to test without dependencies.
        """
        # Normalize both to list format for merging
        if isinstance(existing_content, str):
            if existing_content:
                existing_list = [{"type": "text", "text": existing_content}]
            else:
                existing_list = []
        else:
            existing_list = existing_content if existing_content else []
        
        if isinstance(new_content, str):
            if new_content:
                new_list = [{"type": "text", "text": new_content}]
            else:
                new_list = []
        else:
            new_list = new_content if new_content else []
        
        # Merge the content lists
        merged = existing_list + new_list
        
        # If only text blocks and one or fewer, simplify back to string
        if len(merged) == 0:
            return ''
        elif len(merged) == 1 and merged[0].get('type') == 'text':
            return merged[0]['text']
        else:
            return merged

    def test_merge_two_strings(self):
        """Test merging two string contents."""
        result = self._merge_content_logic("Hello", " World")
        # Returns list since we have 2 text blocks
        assert result == [
            {"type": "text", "text": "Hello"},
            {"type": "text", "text": " World"},
        ]

    def test_merge_string_and_empty(self):
        """Test merging string with empty string."""
        result = self._merge_content_logic("Hello", "")
        assert result == "Hello"

    def test_merge_empty_strings(self):
        """Test merging two empty strings."""
        result = self._merge_content_logic("", "")
        assert result == ""

    def test_merge_list_and_string(self):
        """Test merging list content with string."""
        existing = [{"type": "text", "text": "First"}]
        result = self._merge_content_logic(existing, "Second")
        
        assert len(result) == 2
        assert result[0]["text"] == "First"
        assert result[1]["text"] == "Second"

    def test_merge_preserves_image_blocks(self):
        """Test that image blocks are preserved during merge."""
        existing = [{"type": "text", "text": "Before"}]
        new_content = [
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
            {"type": "text", "text": "After"},
        ]
        
        result = self._merge_content_logic(existing, new_content)
        
        assert len(result) == 3
        assert result[0]["type"] == "text"
        assert result[1]["type"] == "image_url"
        assert result[2]["type"] == "text"

    def test_single_text_block_simplified_to_string(self):
        """Test that single text block is simplified to string."""
        result = self._merge_content_logic("", "Only text")
        assert result == "Only text"
        assert isinstance(result, str)

    def test_none_content_handled(self):
        """Test that None content is handled as empty."""
        result = self._merge_content_logic(None, "New content")
        assert result == "New content"
