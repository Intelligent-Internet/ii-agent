"""Tests for the Anthropic LLM client safety net.

The safety net in AnthropicDirectClient.generate() and agenerate() scans
all assistant messages for trailing thinking/redacted_thinking blocks and
appends an AnthropicTextBlock before sending to the API.  This prevents
400 errors ("The final block in an assistant message cannot be 'thinking'").

We replicate the safety net logic here (same pattern as
test_anthropic_max_tokens.py) to test it in isolation without
instantiating the full client.
"""

import pytest
from anthropic.types import (
    TextBlock as AnthropicTextBlock,
    ThinkingBlock as AnthropicThinkingBlock,
    RedactedThinkingBlock as AnthropicRedactedThinkingBlock,
)


def _apply_safety_net(anthropic_messages: list[dict]) -> list[dict]:
    """Replicate the safety net logic from AnthropicDirectClient.generate/agenerate."""
    for msg in anthropic_messages:
        if msg["role"] == "assistant" and msg["content"]:
            last_block = msg["content"][-1]
            block_type = getattr(last_block, "type", None) or (
                last_block.get("type") if isinstance(last_block, dict) else None
            )
            if block_type in ("thinking", "redacted_thinking"):
                msg["content"].append(
                    AnthropicTextBlock(type="text", text="(continued)")
                )
    return anthropic_messages


class TestAnthropicSafetyNet:
    """Tests for the safety net that prevents trailing thinking blocks in API messages."""

    def test_assistant_trailing_thinking_block_gets_text_appended(self):
        msgs = [
            {
                "role": "assistant",
                "content": [
                    AnthropicThinkingBlock(
                        type="thinking", thinking="deep thought", signature="sig"
                    )
                ],
            }
        ]
        result = _apply_safety_net(msgs)
        assert len(result[0]["content"]) == 2
        assert result[0]["content"][-1].type == "text"
        assert result[0]["content"][-1].text == "(continued)"

    def test_assistant_trailing_redacted_thinking_gets_text_appended(self):
        msgs = [
            {
                "role": "assistant",
                "content": [
                    AnthropicRedactedThinkingBlock(type="redacted_thinking", data="abc")
                ],
            }
        ]
        result = _apply_safety_net(msgs)
        assert len(result[0]["content"]) == 2
        assert result[0]["content"][-1].type == "text"
        assert result[0]["content"][-1].text == "(continued)"

    def test_assistant_trailing_text_unchanged(self):
        msgs = [
            {
                "role": "assistant",
                "content": [
                    AnthropicThinkingBlock(
                        type="thinking", thinking="thought", signature="s"
                    ),
                    AnthropicTextBlock(type="text", text="done"),
                ],
            }
        ]
        result = _apply_safety_net(msgs)
        assert len(result[0]["content"]) == 2
        assert result[0]["content"][-1].text == "done"

    def test_user_message_with_thinking_type_not_modified(self):
        """Only assistant messages should be checked — user messages are left alone."""
        fake_block = {"type": "thinking", "thinking": "something", "signature": "s"}
        msgs = [{"role": "user", "content": [fake_block]}]
        result = _apply_safety_net(msgs)
        assert len(result[0]["content"]) == 1

    def test_empty_content_unchanged(self):
        msgs = [{"role": "assistant", "content": []}]
        result = _apply_safety_net(msgs)
        assert len(result[0]["content"]) == 0

    def test_dict_block_with_thinking_type_caught(self):
        """Safety net uses getattr with dict fallback, so dict blocks also work."""
        msgs = [
            {
                "role": "assistant",
                "content": [{"type": "thinking", "thinking": "x", "signature": "s"}],
            }
        ]
        result = _apply_safety_net(msgs)
        assert len(result[0]["content"]) == 2
        assert result[0]["content"][-1].type == "text"

    def test_dict_block_with_redacted_thinking_type_caught(self):
        msgs = [
            {
                "role": "assistant",
                "content": [{"type": "redacted_thinking", "data": "abc"}],
            }
        ]
        result = _apply_safety_net(msgs)
        assert len(result[0]["content"]) == 2
        assert result[0]["content"][-1].type == "text"

    def test_multiple_messages_only_trailing_fixed(self):
        msgs = [
            {
                "role": "user",
                "content": [AnthropicTextBlock(type="text", text="hello")],
            },
            {
                "role": "assistant",
                "content": [
                    AnthropicThinkingBlock(
                        type="thinking", thinking="t1", signature="s1"
                    ),
                    AnthropicTextBlock(type="text", text="ok"),
                ],
            },
            {
                "role": "user",
                "content": [AnthropicTextBlock(type="text", text="next")],
            },
            {
                "role": "assistant",
                "content": [
                    AnthropicThinkingBlock(
                        type="thinking", thinking="t2", signature="s2"
                    ),
                ],
            },
        ]
        result = _apply_safety_net(msgs)
        # Message 1 (assistant): has trailing text, unchanged
        assert len(result[1]["content"]) == 2
        assert result[1]["content"][-1].type == "text"
        assert result[1]["content"][-1].text == "ok"
        # Message 3 (assistant): trailing thinking, should have text appended
        assert len(result[3]["content"]) == 2
        assert result[3]["content"][-1].type == "text"
        assert result[3]["content"][-1].text == "(continued)"
