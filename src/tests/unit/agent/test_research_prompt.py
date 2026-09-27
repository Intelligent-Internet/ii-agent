"""Tests for ii_agent.agents.prompts.research_to_website_prompt."""

from __future__ import annotations


class TestResearchToWebsitePrompt:
    def test_get_research_to_website_prompt_returns_string(self):
        """Line 20: f-string builds the prompt."""
        from ii_agent.agents.prompts.research_to_website_prompt import (
            get_research_to_website_prompt,
        )

        result = get_research_to_website_prompt()
        assert isinstance(result, str)
        assert len(result) > 100

    def test_get_research_to_website_prompt_custom_workspace(self):
        from ii_agent.agents.prompts.research_to_website_prompt import (
            get_research_to_website_prompt,
        )

        result = get_research_to_website_prompt(workspace_path="/custom/path")
        assert "/custom/path" in result

    def test_format_fork_user_message_no_additional(self):
        """Lines 129, 132, 138: additional_instruction=None → empty section."""
        from ii_agent.agents.prompts.research_to_website_prompt import (
            format_fork_user_message,
        )

        result = format_fork_user_message(
            attachments=["file1.md", "file2.md"],
            research_mode="deep",
            additional_instruction=None,
        )
        assert isinstance(result, str)
        assert "file1.md" in result
        assert "file2.md" in result

    def test_format_fork_user_message_with_additional(self):
        """Lines 132-134: additional_instruction present → section included."""
        from ii_agent.agents.prompts.research_to_website_prompt import (
            format_fork_user_message,
        )

        result = format_fork_user_message(
            attachments=["report.md"],
            research_mode="fast",
            additional_instruction="Use purple color scheme",
        )
        assert "Use purple color scheme" in result

    def test_format_fork_user_message_empty_attachments(self):
        from ii_agent.agents.prompts.research_to_website_prompt import (
            format_fork_user_message,
        )

        result = format_fork_user_message(
            attachments=[],
            research_mode="deep",
        )
        assert isinstance(result, str)
