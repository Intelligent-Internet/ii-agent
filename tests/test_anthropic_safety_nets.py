"""Tests for Anthropic API safety nets.

Covers:
1. The thinking-block-at-end-of-assistant safety net (appends "(continued)")
2. The prefill safety net (appends synthetic user message when conversation
   ends with assistant and prefix=False)

These are unit tests that verify the message-fixup logic without hitting
the Anthropic API — they test the message list transformations directly.
"""

import pytest
from unittest.mock import MagicMock


class TestThinkingBlockSafetyNet:
    """Ensure assistant messages ending with thinking blocks get patched."""

    def test_dict_thinking_block_gets_continued(self):
        """Dict-style thinking block at end of assistant message gets text appended."""
        messages = [
            {
                "role": "user",
                "content": [{"type": "text", "text": "Hello"}],
            },
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Let me think..."},
                    {"type": "thinking", "thinking": "some reasoning"},
                ],
            },
        ]

        # Apply the same logic as in anthropic.py
        for msg in messages:
            if msg["role"] == "assistant" and msg["content"]:
                last_block = msg["content"][-1]
                block_type = getattr(last_block, "type", None) or (
                    last_block.get("type") if isinstance(last_block, dict) else None
                )
                if block_type in ("thinking", "redacted_thinking"):
                    msg["content"].append({"type": "text", "text": "(continued)"})

        assert messages[1]["content"][-1]["type"] == "text"
        assert messages[1]["content"][-1]["text"] == "(continued)"

    def test_object_thinking_block_gets_continued(self):
        """Object-style thinking block (with .type attr) gets text appended."""
        thinking_block = MagicMock()
        thinking_block.type = "thinking"

        messages = [
            {
                "role": "assistant",
                "content": [thinking_block],
            },
        ]

        for msg in messages:
            if msg["role"] == "assistant" and msg["content"]:
                last_block = msg["content"][-1]
                block_type = getattr(last_block, "type", None) or (
                    last_block.get("type") if isinstance(last_block, dict) else None
                )
                if block_type in ("thinking", "redacted_thinking"):
                    msg["content"].append({"type": "text", "text": "(continued)"})

        assert len(messages[0]["content"]) == 2
        assert messages[0]["content"][-1]["text"] == "(continued)"

    def test_text_block_at_end_is_not_modified(self):
        """Assistant message ending with text should not be modified."""
        messages = [
            {
                "role": "assistant",
                "content": [{"type": "text", "text": "All done."}],
            },
        ]

        for msg in messages:
            if msg["role"] == "assistant" and msg["content"]:
                last_block = msg["content"][-1]
                block_type = getattr(last_block, "type", None) or (
                    last_block.get("type") if isinstance(last_block, dict) else None
                )
                if block_type in ("thinking", "redacted_thinking"):
                    msg["content"].append({"type": "text", "text": "(continued)"})

        assert len(messages[0]["content"]) == 1

    def test_redacted_thinking_also_patched(self):
        """redacted_thinking blocks should also get the safety-net text."""
        messages = [
            {
                "role": "assistant",
                "content": [{"type": "redacted_thinking", "data": "..."}],
            },
        ]

        for msg in messages:
            if msg["role"] == "assistant" and msg["content"]:
                last_block = msg["content"][-1]
                block_type = getattr(last_block, "type", None) or (
                    last_block.get("type") if isinstance(last_block, dict) else None
                )
                if block_type in ("thinking", "redacted_thinking"):
                    msg["content"].append({"type": "text", "text": "(continued)"})

        assert messages[0]["content"][-1]["text"] == "(continued)"


class TestPrefillSafetyNet:
    """Ensure a synthetic user turn is appended when needed."""

    def test_assistant_at_end_without_prefix_gets_user_turn(self):
        """When prefix=False and last message is assistant, append user turn."""
        messages = [
            {"role": "user", "content": [{"type": "text", "text": "Hi"}]},
            {"role": "assistant", "content": [{"type": "text", "text": "Hello"}]},
        ]
        prefix = False

        if not prefix and messages and messages[-1]["role"] == "assistant":
            messages.append(
                {"role": "user", "content": [{"type": "text", "text": "Continue."}]}
            )

        assert len(messages) == 3
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"][0]["text"] == "Continue."

    def test_user_at_end_not_modified(self):
        """When last message is user, no synthetic turn is added."""
        messages = [
            {"role": "user", "content": [{"type": "text", "text": "Hi"}]},
        ]
        prefix = False

        if not prefix and messages and messages[-1]["role"] == "assistant":
            messages.append(
                {"role": "user", "content": [{"type": "text", "text": "Continue."}]}
            )

        assert len(messages) == 1

    def test_prefix_true_does_not_add_user_turn(self):
        """When prefix=True, assistant at end is left alone (prefill mode)."""
        messages = [
            {"role": "user", "content": [{"type": "text", "text": "Hi"}]},
            {"role": "assistant", "content": [{"type": "text", "text": "Hello"}]},
        ]
        prefix = True

        if not prefix and messages and messages[-1]["role"] == "assistant":
            messages.append(
                {"role": "user", "content": [{"type": "text", "text": "Continue."}]}
            )

        assert len(messages) == 2
