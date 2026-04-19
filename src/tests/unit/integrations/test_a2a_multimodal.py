"""Unit tests for the A2A multimodal Part translation module."""

from __future__ import annotations

import base64

import pytest

a2a_types = pytest.importorskip("a2a.types", reason="a2a-sdk not installed")

from a2a.types import (  # noqa: E402
    DataPart,
    FilePart,
    FileWithBytes,
    FileWithUri,
    Part,
    TextPart,
)

from ii_agent.integrations.a2a.multimodal import (  # noqa: E402
    build_conversation_context,
    content_to_parts,
    extract_historical_image_parts,
    extract_user_content,
    has_multimodal_parts,
)


# ---------------------------------------------------------------------------
# extract_user_content
# ---------------------------------------------------------------------------


class TestExtractUserContent:
    def test_text_only_message(self):
        messages = [{"role": "user", "content": "Hello world"}]
        text, parts = extract_user_content(messages)
        assert text == "Hello world"
        assert len(parts) == 1
        assert isinstance(parts[0].root, TextPart)
        assert parts[0].root.text == "Hello world"

    def test_latest_user_message_extracted(self):
        messages = [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "reply"},
            {"role": "user", "content": "second"},
        ]
        text, parts = extract_user_content(messages)
        assert text == "second"

    def test_non_user_messages_skipped(self):
        messages = [
            {"role": "assistant", "content": "I am assistant"},
            {"role": "system", "content": "system prompt"},
        ]
        text, parts = extract_user_content(messages)
        assert text == ""
        assert parts == []

    def test_empty_messages(self):
        text, parts = extract_user_content([])
        assert text == ""
        assert parts == []

    def test_image_with_url(self):
        messages = [
            {
                "role": "user",
                "content": "Describe this image",
                "images": [{"url": "https://example.com/img.png", "mime_type": "image/png"}],
            }
        ]
        text, parts = extract_user_content(messages)
        assert text == "Describe this image"
        assert len(parts) == 2  # TextPart + FilePart
        assert isinstance(parts[0].root, TextPart)
        assert isinstance(parts[1].root, FilePart)
        assert isinstance(parts[1].root.file, FileWithUri)
        assert parts[1].root.file.uri == "https://example.com/img.png"

    def test_image_with_base64_content(self):
        b64 = base64.b64encode(b"fake-image-bytes").decode()
        messages = [
            {
                "role": "user",
                "content": "What is this?",
                "images": [{"content": b64, "mime_type": "image/jpeg", "id": "img-1"}],
            }
        ]
        text, parts = extract_user_content(messages)
        assert len(parts) == 2
        file_part = parts[1].root
        assert isinstance(file_part, FilePart)
        assert isinstance(file_part.file, FileWithBytes)
        assert file_part.file.bytes == b64

    def test_image_with_filepath(self):
        messages = [
            {
                "role": "user",
                "content": "Check this",
                "images": [{"filepath": "/tmp/test.png", "mime_type": "image/png"}],
            }
        ]
        _, parts = extract_user_content(messages)
        assert len(parts) == 2
        file_part = parts[1].root
        assert isinstance(file_part.file, FileWithUri)
        assert file_part.file.uri == "file:///tmp/test.png"

    def test_file_attachment(self):
        messages = [
            {
                "role": "user",
                "content": "Summarise this PDF",
                "files": [{"url": "https://example.com/doc.pdf", "mime_type": "application/pdf"}],
            }
        ]
        text, parts = extract_user_content(messages)
        assert text == "Summarise this PDF"
        assert len(parts) == 2
        assert isinstance(parts[1].root, FilePart)
        assert parts[1].root.file.uri == "https://example.com/doc.pdf"

    def test_multiple_images_and_files(self):
        b64 = base64.b64encode(b"bytes").decode()
        messages = [
            {
                "role": "user",
                "content": "Compare these",
                "images": [
                    {"url": "https://example.com/a.png", "mime_type": "image/png"},
                    {"content": b64, "mime_type": "image/jpeg"},
                ],
                "files": [
                    {"url": "https://example.com/data.csv", "mime_type": "text/csv"},
                ],
            }
        ]
        _, parts = extract_user_content(messages)
        # 1 text + 2 images + 1 file
        assert len(parts) == 4
        assert isinstance(parts[0].root, TextPart)

    def test_content_as_list_of_dicts(self):
        messages = [
            {
                "role": "user",
                "content": [{"text": "part1"}, {"text": "part2"}],
            }
        ]
        text, parts = extract_user_content(messages)
        assert "part1" in text
        assert "part2" in text

    def test_image_without_any_source_skipped(self):
        # Image with no url, content, or filepath should be skipped.
        messages = [
            {
                "role": "user",
                "content": "test",
                "images": [{"mime_type": "image/png"}],
            }
        ]
        _, parts = extract_user_content(messages)
        # Only the text part
        assert len(parts) == 1
        assert isinstance(parts[0].root, TextPart)

    def test_audio_with_url(self):
        messages = [
            {
                "role": "user",
                "content": "Transcribe this",
                "audio": [{"url": "https://example.com/clip.mp3", "mime_type": "audio/mpeg"}],
            }
        ]
        text, parts = extract_user_content(messages)
        assert text == "Transcribe this"
        assert len(parts) == 2
        assert isinstance(parts[0].root, TextPart)
        assert isinstance(parts[1].root, FilePart)
        assert isinstance(parts[1].root.file, FileWithUri)
        assert parts[1].root.file.uri == "https://example.com/clip.mp3"
        assert parts[1].root.file.mime_type == "audio/mpeg"

    def test_audio_with_base64_content(self):
        b64 = base64.b64encode(b"fake-audio-bytes").decode()
        messages = [
            {
                "role": "user",
                "content": "What is this sound?",
                "audio": [{"content": b64, "mime_type": "audio/wav", "id": "aud-1"}],
            }
        ]
        _, parts = extract_user_content(messages)
        assert len(parts) == 2
        file_part = parts[1].root
        assert isinstance(file_part, FilePart)
        assert isinstance(file_part.file, FileWithBytes)
        assert file_part.file.bytes == b64
        assert file_part.file.name == "aud-1"

    def test_audio_with_filepath(self):
        messages = [
            {
                "role": "user",
                "content": "Check this audio",
                "audio": [{"filepath": "/tmp/test.wav", "mime_type": "audio/wav"}],
            }
        ]
        _, parts = extract_user_content(messages)
        assert len(parts) == 2
        assert isinstance(parts[1].root.file, FileWithUri)
        assert parts[1].root.file.uri == "file:///tmp/test.wav"

    def test_audio_without_any_source_skipped(self):
        messages = [
            {
                "role": "user",
                "content": "test",
                "audio": [{"mime_type": "audio/mpeg"}],
            }
        ]
        _, parts = extract_user_content(messages)
        assert len(parts) == 1
        assert isinstance(parts[0].root, TextPart)

    def test_audio_default_mime_type(self):
        messages = [
            {
                "role": "user",
                "content": "listen",
                "audio": [{"url": "https://example.com/clip.mp3"}],
            }
        ]
        _, parts = extract_user_content(messages)
        assert parts[1].root.file.mime_type == "audio/mpeg"

    def test_video_with_url(self):
        messages = [
            {
                "role": "user",
                "content": "Describe this video",
                "videos": [{"url": "https://example.com/vid.mp4", "mime_type": "video/mp4"}],
            }
        ]
        text, parts = extract_user_content(messages)
        assert text == "Describe this video"
        assert len(parts) == 2
        assert isinstance(parts[1].root, FilePart)
        assert isinstance(parts[1].root.file, FileWithUri)
        assert parts[1].root.file.uri == "https://example.com/vid.mp4"
        assert parts[1].root.file.mime_type == "video/mp4"

    def test_video_with_base64_content(self):
        b64 = base64.b64encode(b"fake-video-bytes").decode()
        messages = [
            {
                "role": "user",
                "content": "What happens here?",
                "videos": [{"content": b64, "mime_type": "video/webm", "id": "vid-1"}],
            }
        ]
        _, parts = extract_user_content(messages)
        assert len(parts) == 2
        file_part = parts[1].root
        assert isinstance(file_part, FilePart)
        assert isinstance(file_part.file, FileWithBytes)
        assert file_part.file.bytes == b64
        assert file_part.file.name == "vid-1"

    def test_video_with_filepath(self):
        messages = [
            {
                "role": "user",
                "content": "Analyse this clip",
                "videos": [{"filepath": "/tmp/clip.mp4", "mime_type": "video/mp4"}],
            }
        ]
        _, parts = extract_user_content(messages)
        assert len(parts) == 2
        assert isinstance(parts[1].root.file, FileWithUri)
        assert parts[1].root.file.uri == "file:///tmp/clip.mp4"

    def test_video_without_any_source_skipped(self):
        messages = [
            {
                "role": "user",
                "content": "test",
                "videos": [{"mime_type": "video/mp4"}],
            }
        ]
        _, parts = extract_user_content(messages)
        assert len(parts) == 1
        assert isinstance(parts[0].root, TextPart)

    def test_video_default_mime_type(self):
        messages = [
            {
                "role": "user",
                "content": "watch",
                "videos": [{"url": "https://example.com/vid.mp4"}],
            }
        ]
        _, parts = extract_user_content(messages)
        assert parts[1].root.file.mime_type == "video/mp4"

    def test_mixed_media_all_types(self):
        b64 = base64.b64encode(b"bytes").decode()
        messages = [
            {
                "role": "user",
                "content": "Compare all of these",
                "images": [{"url": "https://example.com/a.png", "mime_type": "image/png"}],
                "files": [{"url": "https://example.com/data.csv", "mime_type": "text/csv"}],
                "audio": [{"url": "https://example.com/clip.mp3", "mime_type": "audio/mpeg"}],
                "videos": [{"content": b64, "mime_type": "video/mp4"}],
            }
        ]
        _, parts = extract_user_content(messages)
        # 1 text + 1 image + 1 file + 1 audio + 1 video
        assert len(parts) == 5
        assert isinstance(parts[0].root, TextPart)


# ---------------------------------------------------------------------------
# content_to_parts (outbound)
# ---------------------------------------------------------------------------


class TestContentToParts:
    def test_string_content(self):
        parts = content_to_parts("hello")
        assert len(parts) == 1
        assert parts[0].root.text == "hello"

    def test_empty_string(self):
        assert content_to_parts("") == []

    def test_none_content(self):
        assert content_to_parts(None) == []

    def test_dict_with_text(self):
        parts = content_to_parts({"text": "some text"})
        assert len(parts) == 1
        assert parts[0].root.text == "some text"

    def test_dict_with_image_url(self):
        parts = content_to_parts({"text": "caption", "image_url": "https://example.com/img.png"})
        assert len(parts) == 2
        assert isinstance(parts[0].root, TextPart)
        assert isinstance(parts[1].root, FilePart)
        assert parts[1].root.file.uri == "https://example.com/img.png"

    def test_dict_with_image_dict(self):
        parts = content_to_parts(
            {"image": {"url": "https://example.com/photo.jpg", "mime_type": "image/jpeg"}}
        )
        assert len(parts) == 1
        assert isinstance(parts[0].root, FilePart)

    def test_dict_with_file_url(self):
        parts = content_to_parts({"file_url": "https://example.com/doc.pdf"})
        assert len(parts) == 1
        assert isinstance(parts[0].root, FilePart)

    def test_dict_with_data(self):
        parts = content_to_parts({"data": {"key": "value"}})
        assert len(parts) == 1
        assert isinstance(parts[0].root, DataPart)
        assert parts[0].root.data == {"key": "value"}

    def test_dict_with_message_key(self):
        parts = content_to_parts({"message": "msg text"})
        assert len(parts) == 1
        assert parts[0].root.text == "msg text"

    def test_non_dict_non_string(self):
        parts = content_to_parts(42)
        assert len(parts) == 1
        assert parts[0].root.text == "42"

    def test_dict_with_file_dict(self):
        parts = content_to_parts(
            {"file": {"url": "https://example.com/f.txt", "mime_type": "text/plain"}}
        )
        assert len(parts) == 1
        assert isinstance(parts[0].root, FilePart)

    def test_image_output_in_content(self):
        parts = content_to_parts(
            {
                "text": "Generated image",
                "image_output": {
                    "url": "https://example.com/generated.png",
                    "mime_type": "image/png",
                },
            }
        )
        assert len(parts) == 2
        assert isinstance(parts[0].root, TextPart)
        assert isinstance(parts[1].root, FilePart)


# ---------------------------------------------------------------------------
# extract_historical_image_parts
# ---------------------------------------------------------------------------


class TestExtractHistoricalImageParts:
    def test_no_prior_images(self):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
            {"role": "user", "content": "follow-up"},
        ]
        parts = extract_historical_image_parts(messages)
        assert parts == []

    def test_prior_user_image_collected(self):
        img_b64 = base64.b64encode(b"\x89PNG_FAKE").decode()
        messages = [
            {
                "role": "user",
                "content": "describe this",
                "images": [{"id": "img1", "content": img_b64, "mime_type": "image/png"}],
            },
            {"role": "assistant", "content": "It's a cat."},
            {"role": "user", "content": "What color is it?"},
        ]
        parts = extract_historical_image_parts(messages)
        assert len(parts) == 1
        assert isinstance(parts[0].root, FilePart)

    def test_latest_user_message_excluded(self):
        """Images on the last user message are handled by extract_user_content."""
        img_b64 = base64.b64encode(b"\x89PNG_FAKE").decode()
        messages = [
            {"role": "user", "content": "no image here"},
            {"role": "assistant", "content": "ok"},
            {
                "role": "user",
                "content": "now with image",
                "images": [{"id": "img1", "content": img_b64, "mime_type": "image/png"}],
            },
        ]
        parts = extract_historical_image_parts(messages)
        assert parts == []

    def test_deduplicates_by_id(self):
        img_b64 = base64.b64encode(b"\x89PNG_FAKE").decode()
        messages = [
            {
                "role": "user",
                "content": "turn1",
                "images": [{"id": "img1", "content": img_b64, "mime_type": "image/png"}],
            },
            {"role": "assistant", "content": "reply1"},
            {
                "role": "user",
                "content": "turn2",
                "images": [{"id": "img1", "content": img_b64, "mime_type": "image/png"}],
            },
            {"role": "assistant", "content": "reply2"},
            {"role": "user", "content": "turn3"},
        ]
        parts = extract_historical_image_parts(messages)
        assert len(parts) == 1  # same id, deduped

    def test_multiple_images_across_turns(self):
        img1_b64 = base64.b64encode(b"\x89PNG_FAKE1").decode()
        img2_b64 = base64.b64encode(b"\x89PNG_FAKE2").decode()
        messages = [
            {
                "role": "user",
                "content": "turn1",
                "images": [{"id": "img1", "content": img1_b64, "mime_type": "image/png"}],
            },
            {"role": "assistant", "content": "reply1"},
            {
                "role": "user",
                "content": "turn2",
                "images": [{"id": "img2", "content": img2_b64, "mime_type": "image/jpeg"}],
            },
            {"role": "assistant", "content": "reply2"},
            {"role": "user", "content": "turn3"},
        ]
        parts = extract_historical_image_parts(messages)
        assert len(parts) == 2

    def test_single_user_message_returns_empty(self):
        """Single user message has no prior history."""
        img_b64 = base64.b64encode(b"\x89PNG").decode()
        messages = [
            {
                "role": "user",
                "content": "describe this",
                "images": [{"id": "img1", "content": img_b64, "mime_type": "image/png"}],
            },
        ]
        parts = extract_historical_image_parts(messages)
        assert parts == []

    def test_assistant_images_ignored(self):
        """Only user message images are collected, not assistant."""
        img_b64 = base64.b64encode(b"\x89PNG").decode()
        messages = [
            {"role": "user", "content": "generate something"},
            {
                "role": "assistant",
                "content": "Here it is",
                "images": [{"id": "gen1", "content": img_b64, "mime_type": "image/png"}],
            },
            {"role": "user", "content": "tell me more"},
        ]
        parts = extract_historical_image_parts(messages)
        assert parts == []

    def test_empty_messages(self):
        assert extract_historical_image_parts([]) == []

    def test_images_without_id_not_deduped(self):
        """Images without an id field should all be collected."""
        img_b64 = base64.b64encode(b"\x89PNG").decode()
        messages = [
            {
                "role": "user",
                "content": "turn1",
                "images": [{"content": img_b64, "mime_type": "image/png"}],
            },
            {"role": "assistant", "content": "reply"},
            {
                "role": "user",
                "content": "turn2",
                "images": [{"content": img_b64, "mime_type": "image/png"}],
            },
            {"role": "assistant", "content": "reply2"},
            {"role": "user", "content": "turn3"},
        ]
        parts = extract_historical_image_parts(messages)
        assert len(parts) == 2  # no id means no dedup


# ---------------------------------------------------------------------------
# has_multimodal_parts
# ---------------------------------------------------------------------------


class TestHasMultimodalParts:
    def test_text_only(self):
        parts = [Part(root=TextPart(text="hello"))]
        assert has_multimodal_parts(parts) is False

    def test_with_file_part(self):
        parts = [
            Part(root=TextPart(text="hello")),
            Part(root=FilePart(file=FileWithUri(name="img", uri="https://example.com/img.png"))),
        ]
        assert has_multimodal_parts(parts) is True

    def test_empty_list(self):
        assert has_multimodal_parts([]) is False

    def test_only_file_part(self):
        parts = [Part(root=FilePart(file=FileWithUri(name="f", uri="https://example.com/f.txt")))]
        assert has_multimodal_parts(parts) is True


# ---------------------------------------------------------------------------
# build_conversation_context
# ---------------------------------------------------------------------------


class TestBuildConversationContext:
    def test_empty_messages(self):
        assert build_conversation_context([]) == ""

    def test_single_user_message_returns_empty(self):
        """A single user message is the current prompt — no history to build."""
        messages = [{"role": "user", "content": "Hello"}]
        assert build_conversation_context(messages) == ""

    def test_system_messages_excluded(self):
        """System/developer messages should not appear in history."""
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "developer", "content": "Be concise."},
            {"role": "user", "content": "Hello"},
        ]
        assert build_conversation_context(messages) == ""

    def test_basic_user_assistant_history(self):
        messages = [
            {"role": "user", "content": "What is 2+2?"},
            {"role": "assistant", "content": "The answer is 4."},
            {"role": "user", "content": "And 3+3?"},
        ]
        result = build_conversation_context(messages)
        assert "<conversation_history>" in result
        assert "</conversation_history>" in result
        assert "[User]: What is 2+2?" in result
        assert "[Assistant]: The answer is 4." in result
        # Current prompt should NOT be in history
        assert "3+3" not in result

    def test_multi_turn_conversation(self):
        messages = [
            {"role": "user", "content": "Turn 1"},
            {"role": "assistant", "content": "Reply 1"},
            {"role": "user", "content": "Turn 2"},
            {"role": "assistant", "content": "Reply 2"},
            {"role": "user", "content": "Turn 3 (current)"},
        ]
        result = build_conversation_context(messages)
        assert "[User]: Turn 1" in result
        assert "[Assistant]: Reply 1" in result
        assert "[User]: Turn 2" in result
        assert "[Assistant]: Reply 2" in result
        assert "Turn 3 (current)" not in result

    def test_reasoning_content_preserved(self):
        """Assistant thinking/reasoning blocks should be wrapped in <thinking> tags."""
        messages = [
            {"role": "user", "content": "Solve this math problem."},
            {
                "role": "assistant",
                "content": "The answer is 42.",
                "reasoning_content": "Let me think step by step...\nFirst, I need to consider...",
            },
            {"role": "user", "content": "Explain more."},
        ]
        result = build_conversation_context(messages)
        assert "<thinking>" in result
        assert "Let me think step by step..." in result
        assert "</thinking>" in result
        assert "[Assistant]: The answer is 42." in result

    def test_tool_calls_preserved(self):
        """Assistant tool calls should show tool name and arguments."""
        messages = [
            {"role": "user", "content": "Run a command."},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_123",
                        "function": {
                            "name": "RunCommand",
                            "arguments": '{"command": "ls -la"}',
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "content": "file1.txt\nfile2.txt",
                "tool_call_id": "call_123",
                "tool_name": "RunCommand",
            },
            {"role": "user", "content": "What did you find?"},
        ]
        result = build_conversation_context(messages)
        assert "[Assistant Tool Call]: RunCommand(" in result
        assert "[Tool Result (RunCommand)]:" in result
        assert "file1.txt" in result

    def test_tool_result_without_name(self):
        """Tool results without a tool_name should still be labeled correctly."""
        messages = [
            {"role": "user", "content": "Do something."},
            {
                "role": "tool",
                "content": "Some result",
                "tool_call_id": "call_456",
            },
            {"role": "user", "content": "Continue."},
        ]
        result = build_conversation_context(messages)
        assert "[Tool Result]:" in result
        assert "Some result" in result

    def test_long_tool_args_truncated(self):
        """Very long tool arguments should be truncated."""
        long_args = "x" * 3000
        messages = [
            {"role": "user", "content": "Start."},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_789",
                        "function": {"name": "BigTool", "arguments": long_args},
                    }
                ],
            },
            {"role": "user", "content": "Done."},
        ]
        result = build_conversation_context(messages)
        assert "... (truncated)" in result

    def test_long_tool_result_truncated(self):
        """Very long tool results should be truncated."""
        long_result = "y" * 5000
        messages = [
            {"role": "user", "content": "Start."},
            {
                "role": "tool",
                "content": long_result,
                "tool_name": "BigOutput",
            },
            {"role": "user", "content": "Done."},
        ]
        result = build_conversation_context(messages)
        assert "... (truncated)" in result
        # Should be truncated to ~3000 chars + truncation message
        history_section = result.split("[Tool Result (BigOutput)]:")[1].split("\n\n")[0]
        assert len(history_section) < 3200

    def test_image_references_in_user_message(self):
        """User messages with images should note them inline."""
        messages = [
            {
                "role": "user",
                "content": "Describe this.",
                "images": [{"url": "https://example.com/photo.jpg", "alt_text": "sunset"}],
            },
            {"role": "assistant", "content": "Beautiful sunset."},
            {"role": "user", "content": "More detail?"},
        ]
        result = build_conversation_context(messages)
        assert "[Attached image: sunset" in result
        assert "https://example.com/photo.jpg" in result

    def test_file_references_in_user_message(self):
        """User messages with files should note them inline."""
        messages = [
            {
                "role": "user",
                "content": "Summarize this.",
                "files": [{"url": "https://example.com/doc.pdf", "filename": "report.pdf"}],
            },
            {"role": "assistant", "content": "Summary here."},
            {"role": "user", "content": "More?"},
        ]
        result = build_conversation_context(messages)
        assert "[Attached file: report.pdf" in result

    def test_tool_call_with_dict_arguments(self):
        """Tool calls with dict arguments should be JSON-serialized."""
        messages = [
            {"role": "user", "content": "Navigate."},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_abc",
                        "function": {
                            "name": "browser_navigate",
                            "arguments": {"url": "https://example.com"},
                        },
                    }
                ],
            },
            {"role": "user", "content": "What happened?"},
        ]
        result = build_conversation_context(messages)
        assert "[Assistant Tool Call]: browser_navigate(" in result
        assert "https://example.com" in result

    def test_multiple_tool_calls_in_one_message(self):
        """Multiple tool calls in a single assistant message should all appear."""
        messages = [
            {"role": "user", "content": "Do two things."},
            {
                "role": "assistant",
                "content": "I'll do both.",
                "tool_calls": [
                    {"id": "c1", "function": {"name": "tool_a", "arguments": "{}"}},
                    {"id": "c2", "function": {"name": "tool_b", "arguments": "{}"}},
                ],
            },
            {"role": "user", "content": "Next?"},
        ]
        result = build_conversation_context(messages)
        assert "[Assistant Tool Call]: tool_a(" in result
        assert "[Assistant Tool Call]: tool_b(" in result
        assert "[Assistant]: I'll do both." in result

    def test_complex_multi_turn_with_tools_and_reasoning(self):
        """Full conversation with user, assistant (with thinking), tool calls, tool results."""
        messages = [
            {"role": "system", "content": "You are a helpful agent."},
            {"role": "user", "content": "Navigate to example.com"},
            {
                "role": "assistant",
                "content": "",
                "reasoning_content": "I need to use the browser tool.",
                "tool_calls": [
                    {
                        "id": "tc1",
                        "function": {
                            "name": "browser_navigate",
                            "arguments": '{"url": "https://example.com"}',
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "content": "Page loaded: Example Domain",
                "tool_call_id": "tc1",
                "tool_name": "browser_navigate",
            },
            {
                "role": "assistant",
                "content": "I've navigated to example.com. It shows the Example Domain page.",
            },
            {"role": "user", "content": "Now take a screenshot."},
        ]
        result = build_conversation_context(messages)
        # System message excluded
        assert "You are a helpful agent" not in result
        # First user message
        assert "[User]: Navigate to example.com" in result
        # Thinking
        assert "[Assistant Thinking]:" in result
        assert "I need to use the browser tool." in result
        # Tool call
        assert "[Assistant Tool Call]: browser_navigate(" in result
        # Tool result
        assert "[Tool Result (browser_navigate)]:" in result
        assert "Page loaded: Example Domain" in result
        # Final assistant response
        assert "[Assistant]: I've navigated to example.com" in result
        # Current prompt excluded
        assert "take a screenshot" not in result

    def test_only_system_and_user_returns_empty(self):
        """Only system + single user message = no history."""
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "current prompt"},
        ]
        assert build_conversation_context(messages) == ""

    def test_content_as_list(self):
        """Messages with content as a list of dicts should extract text."""
        messages = [
            {"role": "user", "content": [{"text": "part1"}, {"text": "part2"}]},
            {"role": "assistant", "content": "reply"},
            {"role": "user", "content": "next"},
        ]
        result = build_conversation_context(messages)
        assert "[User]: part1" in result
        assert "[Assistant]: reply" in result

    # --- Gap closures: summary messages ---

    def test_summary_message_labeled_distinctly(self):
        """Messages with is_summary=True should be labeled [Session Summary]."""
        messages = [
            {
                "role": "user",
                "content": "Previously the user asked about Python decorators and the assistant explained them.",
                "is_summary": True,
            },
            {"role": "user", "content": "Now tell me about generators."},
        ]
        result = build_conversation_context(messages)
        assert "[Session Summary]:" in result
        assert "Python decorators" in result
        # Should NOT use [User]: label for summary messages
        assert "[User]:" not in result

    def test_summary_message_assistant_role(self):
        """Summary messages with assistant role should still use [Session Summary] label."""
        messages = [
            {
                "role": "assistant",
                "content": "Conversation covered Python basics, data types, and functions.",
                "is_summary": True,
            },
            {"role": "user", "content": "Continue with classes."},
        ]
        result = build_conversation_context(messages)
        assert "[Session Summary]:" in result
        assert "[Assistant]:" not in result

    # --- Gap closures: redacted reasoning ---

    def test_redacted_reasoning_content_noted(self):
        """Encrypted/redacted reasoning should be noted in history."""
        messages = [
            {"role": "user", "content": "Think hard."},
            {
                "role": "assistant",
                "content": "Here's my answer.",
                "redacted_reasoning_content": "encrypted_block_abc123...",
            },
            {"role": "user", "content": "Explain more."},
        ]
        result = build_conversation_context(messages)
        assert "[Assistant had encrypted reasoning (redacted)]" in result
        assert "[Assistant]: Here's my answer." in result
        # The actual encrypted content should NOT appear
        assert "encrypted_block_abc123" not in result

    def test_both_reasoning_and_redacted_reasoning(self):
        """Both visible and redacted reasoning should both appear."""
        messages = [
            {"role": "user", "content": "Think."},
            {
                "role": "assistant",
                "content": "Answer.",
                "reasoning_content": "I think step by step...",
                "redacted_reasoning_content": "encrypted...",
            },
            {"role": "user", "content": "More."},
        ]
        result = build_conversation_context(messages)
        assert "<thinking>" in result
        assert "I think step by step..." in result
        assert "[Assistant had encrypted reasoning (redacted)]" in result

    # --- Gap closures: tool call errors ---

    def test_tool_call_error_labeled(self):
        """Failed tool calls should be labeled [Tool Error] instead of [Tool Result]."""
        messages = [
            {"role": "user", "content": "Run this."},
            {
                "role": "tool",
                "content": "Error: command not found",
                "tool_name": "RunCommand",
                "tool_call_error": True,
            },
            {"role": "user", "content": "Try again."},
        ]
        result = build_conversation_context(messages)
        assert "[Tool Error (RunCommand)]:" in result
        assert "Error: command not found" in result
        assert "[Tool Result" not in result

    def test_tool_call_error_without_name(self):
        """Failed tool calls without a tool_name should still show [Tool Error]."""
        messages = [
            {"role": "user", "content": "Do it."},
            {
                "role": "tool",
                "content": "Permission denied",
                "tool_call_error": True,
            },
            {"role": "user", "content": "Fix it."},
        ]
        result = build_conversation_context(messages)
        assert "[Tool Error]:" in result
        assert "Permission denied" in result

    def test_successful_tool_not_labeled_as_error(self):
        """Successful tool calls should use [Tool Result], not [Tool Error]."""
        messages = [
            {"role": "user", "content": "Run it."},
            {
                "role": "tool",
                "content": "Success!",
                "tool_name": "RunCommand",
                "tool_call_error": False,
            },
            {"role": "user", "content": "Great."},
        ]
        result = build_conversation_context(messages)
        assert "[Tool Result (RunCommand)]:" in result
        assert "[Tool Error" not in result

    # --- Gap closures: audio attachments ---

    def test_audio_attachments_referenced(self):
        """Audio attachments on user messages should be noted."""
        messages = [
            {
                "role": "user",
                "content": "Transcribe this.",
                "audio": [{"id": "audio_001", "transcript": "Hello world"}],
            },
            {"role": "assistant", "content": "I heard: Hello world"},
            {"role": "user", "content": "More."},
        ]
        result = build_conversation_context(messages)
        assert "[Attached audio: audio_001" in result
        assert "transcript: Hello world" in result

    def test_audio_attachment_without_transcript(self):
        """Audio attachments without transcript should still appear."""
        messages = [
            {
                "role": "user",
                "content": "Listen.",
                "audio": [{"id": "clip_42"}],
            },
            {"role": "assistant", "content": "OK"},
            {"role": "user", "content": "Next."},
        ]
        result = build_conversation_context(messages)
        assert "[Attached audio: clip_42]" in result

    # --- Gap closures: video attachments ---

    def test_video_attachments_referenced(self):
        """Video attachments on user messages should be noted."""
        messages = [
            {
                "role": "user",
                "content": "Analyze this video.",
                "videos": [{"id": "vid_001", "url": "https://example.com/video.mp4"}],
            },
            {"role": "assistant", "content": "I see a cat."},
            {"role": "user", "content": "Describe more."},
        ]
        result = build_conversation_context(messages)
        assert "[Attached video: vid_001" in result
        assert "https://example.com/video.mp4" in result

    def test_video_attachment_without_url(self):
        """Video attachments without URL should still appear."""
        messages = [
            {
                "role": "user",
                "content": "Watch.",
                "videos": [{"id": "vid_002"}],
            },
            {"role": "assistant", "content": "Seen."},
            {"role": "user", "content": "Next."},
        ]
        result = build_conversation_context(messages)
        assert "[Attached video: vid_002]" in result

    # --- Gap closures: assistant media outputs ---

    def test_assistant_image_output(self):
        """Assistant image_output should be noted as [Generated image]."""
        messages = [
            {"role": "user", "content": "Generate an image of a cat."},
            {
                "role": "assistant",
                "content": "Here's your cat image.",
                "image_output": {"id": "img_gen_1", "url": "https://example.com/cat.png"},
            },
            {"role": "user", "content": "Make it blue."},
        ]
        result = build_conversation_context(messages)
        assert "[Generated image:" in result
        assert "https://example.com/cat.png" in result

    def test_assistant_file_output(self):
        """Assistant file_output should be noted as [Generated file]."""
        messages = [
            {"role": "user", "content": "Create a CSV."},
            {
                "role": "assistant",
                "content": "CSV created.",
                "file_output": {"filename": "data.csv", "url": "https://example.com/data.csv"},
            },
            {"role": "user", "content": "Add more rows."},
        ]
        result = build_conversation_context(messages)
        assert "[Generated file: data.csv" in result
        assert "https://example.com/data.csv" in result

    def test_assistant_audio_output(self):
        """Assistant audio_output should be noted as [Generated audio]."""
        messages = [
            {"role": "user", "content": "Read this aloud."},
            {
                "role": "assistant",
                "content": "Here's the audio.",
                "audio_output": {"id": "tts_1", "transcript": "Hello, I am reading this aloud."},
            },
            {"role": "user", "content": "Louder."},
        ]
        result = build_conversation_context(messages)
        assert "[Generated audio: tts_1" in result
        assert "transcript: Hello, I am reading this aloud." in result

    def test_assistant_video_output(self):
        """Assistant video_output should be noted as [Generated video]."""
        messages = [
            {"role": "user", "content": "Make me a video."},
            {
                "role": "assistant",
                "content": "Video done.",
                "video_output": {"id": "vid_gen_1", "url": "https://example.com/clip.mp4"},
            },
            {"role": "user", "content": "Shorter."},
        ]
        result = build_conversation_context(messages)
        assert "[Generated video: vid_gen_1" in result
        assert "https://example.com/clip.mp4" in result

    # --- Gap closures: assistant media attachments ---

    def test_assistant_images_referenced(self):
        """Images attached to assistant messages should be noted."""
        messages = [
            {"role": "user", "content": "Find images."},
            {
                "role": "assistant",
                "content": "Found these.",
                "images": [{"url": "https://example.com/found.jpg", "alt_text": "result"}],
            },
            {"role": "user", "content": "More."},
        ]
        result = build_conversation_context(messages)
        assert "[Attached image: result" in result
        assert "https://example.com/found.jpg" in result

    # --- Gap closures: citations ---

    def test_citations_on_assistant_message(self):
        """Citations on assistant messages should be noted."""
        messages = [
            {"role": "user", "content": "What's the latest news?"},
            {
                "role": "assistant",
                "content": "Here are the results.",
                "citations": {
                    "citations": [
                        {"title": "News Article", "url": "https://example.com/news"},
                        {"title": "Blog Post", "url": "https://example.com/blog"},
                    ]
                },
            },
            {"role": "user", "content": "Tell me more."},
        ]
        result = build_conversation_context(messages)
        assert "[Citation: News Article — https://example.com/news]" in result
        assert "[Citation: Blog Post — https://example.com/blog]" in result

    def test_citations_empty_does_not_crash(self):
        """Empty citations dict should not produce output or crash."""
        messages = [
            {"role": "user", "content": "Search."},
            {
                "role": "assistant",
                "content": "Nothing found.",
                "citations": {},
            },
            {"role": "user", "content": "Try again."},
        ]
        result = build_conversation_context(messages)
        assert "[Citation" not in result
        assert "[Assistant]: Nothing found." in result

    # --- Gap closures: combined complex scenario ---

    def test_all_features_combined(self):
        """Full conversation exercising every feature: summary, reasoning, redacted,
        tool calls, tool errors, audio, video, image/file outputs, citations."""
        messages = [
            # Session summary from prior compressed history
            {
                "role": "user",
                "content": "User asked to build a web app. Assistant set up the project.",
                "is_summary": True,
            },
            # User with audio attachment
            {
                "role": "user",
                "content": "Here's my voice note about the design.",
                "audio": [{"id": "voice_1", "transcript": "I want a blue theme"}],
            },
            # Assistant with reasoning + redacted reasoning + tool call
            {
                "role": "assistant",
                "content": "",
                "reasoning_content": "Let me set up the blue theme.",
                "redacted_reasoning_content": "encrypted_data",
                "tool_calls": [
                    {
                        "id": "tc1",
                        "function": {
                            "name": "WriteFile",
                            "arguments": '{"path": "theme.css", "content": "body { color: blue; }"}',
                        },
                    }
                ],
            },
            # Successful tool result
            {
                "role": "tool",
                "content": "File written successfully.",
                "tool_name": "WriteFile",
                "tool_call_id": "tc1",
            },
            # Failed tool call
            {
                "role": "tool",
                "content": "Error: file not found",
                "tool_name": "ReadFile",
                "tool_call_id": "tc2",
                "tool_call_error": True,
            },
            # Assistant with image output and citations
            {
                "role": "assistant",
                "content": "Done! Here's a preview.",
                "image_output": {"id": "preview_1", "url": "https://example.com/preview.png"},
                "citations": {
                    "citations": [
                        {"title": "CSS Guide", "url": "https://example.com/css"},
                    ]
                },
            },
            # User with video attachment
            {
                "role": "user",
                "content": "Check this screencast.",
                "videos": [{"id": "screen_1", "url": "https://example.com/screencast.mp4"}],
            },
            # Current prompt
            {"role": "user", "content": "Now add dark mode."},
        ]
        result = build_conversation_context(messages)

        # Summary
        assert "[Session Summary]:" in result
        assert "build a web app" in result

        # Audio attachment
        assert "[Attached audio: voice_1" in result
        assert "transcript: I want a blue theme" in result

        # Reasoning + redacted
        assert "<thinking>" in result
        assert "set up the blue theme" in result
        assert "[Assistant had encrypted reasoning (redacted)]" in result

        # Tool call
        assert "[Assistant Tool Call]: WriteFile(" in result

        # Successful tool result
        assert "[Tool Result (WriteFile)]:" in result

        # Failed tool
        assert "[Tool Error (ReadFile)]:" in result
        assert "Error: file not found" in result

        # Image output
        assert "[Generated image:" in result
        assert "https://example.com/preview.png" in result

        # Citations
        assert "[Citation: CSS Guide" in result

        # Video attachment
        assert "[Attached video: screen_1" in result

        # Current prompt excluded
        assert "dark mode" not in result
