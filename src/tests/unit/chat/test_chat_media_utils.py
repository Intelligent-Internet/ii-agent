"""Unit tests for chat/media/utils/ - PromptBuilder static methods."""

from ii_agent.chat.media.utils.prompt_builder import PromptBuilder


# ---------------------------------------------------------------------------
# Helpers / shared fixtures
# ---------------------------------------------------------------------------


def _make_ref(ref_type: str):
    """Create a minimal MediaReference-like object using a simple namespace."""
    from types import SimpleNamespace

    return SimpleNamespace(type=ref_type, file_id=f"file-{ref_type}")


class _FakeMediaReference:
    """Minimal stub for MediaReference duck-typing."""

    def __init__(self, ref_type: str, file_id: str = ""):
        self.type = ref_type
        self.file_id = file_id or f"fid-{ref_type}"


# ---------------------------------------------------------------------------
# PromptBuilder.build_reference_guidance tests
# ---------------------------------------------------------------------------


class TestBuildReferenceGuidanceEmpty:
    """Tests when no references are provided."""

    def test_empty_references_returns_empty_string(self):
        text, index_map, next_idx = PromptBuilder.build_reference_guidance([])
        assert text == ""

    def test_empty_references_returns_empty_index_map(self):
        _, index_map, _ = PromptBuilder.build_reference_guidance([])
        assert index_map == {}

    def test_empty_references_preserves_starting_index(self):
        _, _, next_idx = PromptBuilder.build_reference_guidance([], starting_index=5)
        assert next_idx == 5


class TestBuildReferenceGuidanceSingleType:
    """Tests with a single reference type."""

    def test_subject_ref_present_in_guidance(self):
        refs = [_FakeMediaReference("subject")]
        text, _, _ = PromptBuilder.build_reference_guidance(refs)
        assert "MANDATORY SUBJECT" in text
        assert "Image #1" in text

    def test_scene_ref_present_in_guidance(self):
        refs = [_FakeMediaReference("scene")]
        text, _, _ = PromptBuilder.build_reference_guidance(refs)
        assert "MANDATORY SCENE" in text

    def test_style_ref_present_in_guidance(self):
        refs = [_FakeMediaReference("style")]
        text, _, _ = PromptBuilder.build_reference_guidance(refs)
        assert "MANDATORY STYLE" in text

    def test_subject_index_map_correct(self):
        refs = [_FakeMediaReference("subject")]
        _, index_map, _ = PromptBuilder.build_reference_guidance(refs)
        assert "subject" in index_map
        assert index_map["subject"] == [1]

    def test_starting_index_offset_applied(self):
        refs = [_FakeMediaReference("subject")]
        text, index_map, next_idx = PromptBuilder.build_reference_guidance(refs, starting_index=3)
        assert index_map["subject"] == [3]
        assert "Image #3" in text
        assert next_idx == 4


class TestBuildReferenceGuidanceMultipleTypes:
    """Tests with multiple reference types."""

    def test_all_types_present(self):
        refs = [
            _FakeMediaReference("subject"),
            _FakeMediaReference("scene"),
            _FakeMediaReference("style"),
        ]
        text, index_map, next_idx = PromptBuilder.build_reference_guidance(refs)
        assert "MANDATORY SUBJECT" in text
        assert "MANDATORY SCENE" in text
        assert "MANDATORY STYLE" in text
        assert "subject" in index_map
        assert "scene" in index_map
        assert "style" in index_map

    def test_indices_are_sequential(self):
        refs = [
            _FakeMediaReference("subject"),
            _FakeMediaReference("scene"),
            _FakeMediaReference("style"),
        ]
        _, index_map, next_idx = PromptBuilder.build_reference_guidance(refs)
        assert index_map["subject"] == [1]
        assert index_map["scene"] == [2]
        assert index_map["style"] == [3]
        assert next_idx == 4

    def test_multiple_same_type_indices(self):
        refs = [
            _FakeMediaReference("subject"),
            _FakeMediaReference("subject"),
        ]
        _, index_map, next_idx = PromptBuilder.build_reference_guidance(refs)
        assert index_map["subject"] == [1, 2]
        assert next_idx == 3

    def test_header_present(self):
        refs = [_FakeMediaReference("subject")]
        text, _, _ = PromptBuilder.build_reference_guidance(refs)
        assert "REFERENCE IMAGES" in text


# ---------------------------------------------------------------------------
# PromptBuilder.build_previous_images_guidance tests
# ---------------------------------------------------------------------------


class TestBuildPreviousImagesGuidance:
    """Tests for build_previous_images_guidance."""

    def test_returns_non_empty_string(self):
        result = PromptBuilder.build_previous_images_guidance(starting_index=1)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_starting_index(self):
        result = PromptBuilder.build_previous_images_guidance(starting_index=5)
        assert "#5" in result

    def test_contains_key_instructions(self):
        result = PromptBuilder.build_previous_images_guidance(starting_index=1)
        assert "PREVIOUSLY GENERATED IMAGES" in result
        assert "most recent" in result.lower() or "MOST RECENT" in result

    def test_index_one(self):
        result = PromptBuilder.build_previous_images_guidance(starting_index=1)
        assert "#1" in result

    def test_index_ten(self):
        result = PromptBuilder.build_previous_images_guidance(starting_index=10)
        assert "#10" in result


# ---------------------------------------------------------------------------
# PromptBuilder.build_checklist tests
# ---------------------------------------------------------------------------


class TestBuildChecklist:
    """Tests for build_checklist."""

    def test_empty_references_returns_empty_string(self):
        result = PromptBuilder.build_checklist([])
        assert result == ""

    def test_subject_ref_includes_subject_check(self):
        refs = [_FakeMediaReference("subject")]
        result = PromptBuilder.build_checklist(refs)
        assert "Subject" in result or "subject" in result.lower()
        assert "MANDATORY GENERATION RULES" in result

    def test_scene_ref_includes_scene_check(self):
        refs = [_FakeMediaReference("scene")]
        result = PromptBuilder.build_checklist(refs)
        assert "Background" in result or "SCENE" in result

    def test_style_ref_includes_style_checks(self):
        refs = [_FakeMediaReference("style")]
        result = PromptBuilder.build_checklist(refs)
        assert "style" in result.lower() or "STYLE" in result
        # Should warn about content not appearing from style image
        assert "NO content" in result or "style" in result.lower()

    def test_all_types_produce_full_checklist(self):
        refs = [
            _FakeMediaReference("subject"),
            _FakeMediaReference("scene"),
            _FakeMediaReference("style"),
        ]
        result = PromptBuilder.build_checklist(refs)
        assert "MANDATORY GENERATION RULES" in result
        assert len(result) > 100

    def test_checklist_contains_prompt_construction_rule(self):
        refs = [_FakeMediaReference("subject")]
        result = PromptBuilder.build_checklist(refs)
        assert "PROMPT CONSTRUCTION RULE" in result

    def test_checklist_contains_invalid_generation_section(self):
        refs = [_FakeMediaReference("style")]
        result = PromptBuilder.build_checklist(refs)
        assert "INVALID" in result


# ---------------------------------------------------------------------------
# PromptBuilder.build_settings_constraint tests
# ---------------------------------------------------------------------------


class TestBuildSettingsConstraint:
    """Tests for build_settings_constraint."""

    def test_both_none_returns_empty_string(self):
        result = PromptBuilder.build_settings_constraint(None, None)
        assert result == ""

    def test_aspect_ratio_only(self):
        result = PromptBuilder.build_settings_constraint("16:9", None)
        assert "16:9" in result
        assert "aspect_ratio" in result

    def test_resolution_only(self):
        result = PromptBuilder.build_settings_constraint(None, "1024x1024")
        assert "1024x1024" in result
        assert "resolution" in result

    def test_both_present(self):
        result = PromptBuilder.build_settings_constraint("4:3", "800x600")
        assert "4:3" in result
        assert "800x600" in result

    def test_none_aspect_ratio_uses_default(self):
        result = PromptBuilder.build_settings_constraint(None, "1024x1024")
        assert "default" in result

    def test_none_resolution_uses_default(self):
        result = PromptBuilder.build_settings_constraint("16:9", None)
        assert "default" in result

    def test_contains_override_notice(self):
        result = PromptBuilder.build_settings_constraint("16:9", "1920x1080")
        assert "UI Settings Override" in result or "settings" in result.lower()

    def test_contains_generate_one_image_instruction(self):
        result = PromptBuilder.build_settings_constraint("1:1", "512x512")
        assert "ONE image" in result


# ---------------------------------------------------------------------------
# PromptBuilder.build_mini_tool_hint tests
# ---------------------------------------------------------------------------


class TestBuildMiniToolHint:
    """Tests for build_mini_tool_hint."""

    def test_returns_string(self):
        result = PromptBuilder.build_mini_tool_hint("tool-id-1", "My Tool")
        assert isinstance(result, str)

    def test_contains_tool_id(self):
        result = PromptBuilder.build_mini_tool_hint("tool-123", "Some Tool")
        assert "tool-123" in result

    def test_contains_tool_name(self):
        result = PromptBuilder.build_mini_tool_hint("tid", "Fancy Tool Name")
        assert "Fancy Tool Name" in result

    def test_non_empty_output(self):
        result = PromptBuilder.build_mini_tool_hint("x", "y")
        assert len(result.strip()) > 0

    def test_format_includes_mini_tool_id_key(self):
        result = PromptBuilder.build_mini_tool_hint("abc", "def")
        assert "mini_tool_id" in result

    def test_format_includes_mini_tool_name_key(self):
        result = PromptBuilder.build_mini_tool_hint("abc", "def")
        assert "mini_tool_name" in result


# ---------------------------------------------------------------------------
# chat/media/utils/prompt_builder.py – build_checklist + build_reference_guidance edge cases
# ---------------------------------------------------------------------------


class TestPromptBuilderChecklistEmpty:
    def test_build_checklist_empty_references_returns_empty_string(self):
        """Branch [88, 93]: build_checklist with empty list returns ''."""
        result = PromptBuilder.build_checklist([])
        assert result == ""

    def test_build_reference_guidance_empty_returns_empty(self):
        guidance, index_map, next_idx = PromptBuilder.build_reference_guidance([], starting_index=1)
        assert guidance == ""
        assert index_map == {}
        assert next_idx == 1

    def test_build_reference_guidance_unknown_type_gives_empty_guidance(self):
        """Line 93: else branch when ref_descriptions is empty (unrecognized type)."""
        from types import SimpleNamespace

        # A reference with type "other" is not subject/scene/style → ref_descriptions stays empty
        ref = SimpleNamespace(type="other", file_id="file-other")
        guidance, index_map, next_idx = PromptBuilder.build_reference_guidance(
            [ref], starting_index=1
        )
        assert guidance == ""
        assert index_map == {}
