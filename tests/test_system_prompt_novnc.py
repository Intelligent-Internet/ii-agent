"""Unit tests for noVNC browser handoff instructions in system prompt.

Validates that the system prompt includes noVNC viewer instructions
for CAPTCHA handling and login/authentication scenarios.
"""

import pytest

from ii_agent.prompts.system_prompt import BROWSER_RULES, get_system_prompt


class TestBrowserRulesNoVNC:
    """Tests for noVNC instructions in BROWSER_RULES."""

    def test_browser_rules_contains_novnc_captcha_instruction(self):
        """Test that CAPTCHA handling references noVNC viewer."""
        assert "noVNC viewer" in BROWSER_RULES
        assert "CAPTCHA" in BROWSER_RULES

    def test_browser_rules_contains_expose_port_6080(self):
        """Test that instructions reference port 6080 for noVNC."""
        assert "port 6080" in BROWSER_RULES

    def test_browser_rules_contains_register_deployment_call(self):
        """Test that instructions tell agent to call register_deployment tool."""
        assert "register_deployment" in BROWSER_RULES
        assert "port 6080" in BROWSER_RULES

    def test_browser_rules_contains_login_authentication_instruction(self):
        """Test that login/auth handling references noVNC."""
        assert "Login/Authentication" in BROWSER_RULES
        assert "credentials securely" in BROWSER_RULES

    def test_browser_rules_contains_handoff_steps(self):
        """Test that the 5-step handoff workflow is documented."""
        assert "Share the noVNC URL with the user" in BROWSER_RULES
        assert "Wait for the user to confirm" in BROWSER_RULES
        assert "Resume automation" in BROWSER_RULES

    def test_browser_rules_no_restart_browser_for_captcha(self):
        """Test that old 'restart the browser' CAPTCHA advice is removed."""
        assert "restart the browser" not in BROWSER_RULES


class TestSystemPromptIncludesNoVNC:
    """Tests that get_system_prompt includes noVNC instructions when browser=True."""

    def test_system_prompt_with_browser_includes_novnc(self):
        """Test that system prompt with browser=True includes noVNC instructions."""
        prompt = get_system_prompt(workspace_path="/workspace", browser=True)
        assert "noVNC" in prompt
        assert "port 6080" in prompt

    def test_system_prompt_without_browser_excludes_novnc(self):
        """Test that system prompt with browser=False excludes noVNC instructions."""
        prompt = get_system_prompt(workspace_path="/workspace", browser=False)
        assert "noVNC" not in prompt

    def test_system_prompt_without_design_includes_novnc(self):
        """Test that prompt without design document still includes noVNC when browser=True."""
        prompt = get_system_prompt(
            workspace_path="/workspace", design_document=False, browser=True
        )
        assert "noVNC" in prompt
        assert "port 6080" in prompt
