"""Tests for ii_agent.agents.exceptions — RetryAgentRun, BaseCheckError, InputCheckError, OutputCheckError."""

from __future__ import annotations


class TestAgentExceptions:
    def test_retry_agent_run_init(self):
        from ii_agent.agents.exceptions import RetryAgentRun

        exc = RetryAgentRun("something went wrong")
        assert exc.error_id == "retry_agent_run_error"
        assert exc.stop_execution is False

    def test_retry_agent_run_with_messages(self):
        from ii_agent.agents.exceptions import RetryAgentRun

        exc = RetryAgentRun("error", user_message="Please retry", agent_message="Retrying")
        assert exc.user_message == "Please retry"

    def test_base_check_error_init(self):
        from ii_agent.agents.exceptions import BaseCheckError, CheckTrigger

        exc = BaseCheckError("test msg", "input_check_error", CheckTrigger.OFF_TOPIC)
        assert exc.message == "test msg"
        assert exc.check_trigger == CheckTrigger.OFF_TOPIC
        assert exc.error_id == "off_topic"

    def test_base_check_error_with_non_enum_trigger(self):
        """Branch: check_trigger is not CheckTrigger → str(check_trigger)."""
        from ii_agent.agents.exceptions import BaseCheckError

        exc = BaseCheckError("msg", "error_type", "custom_trigger")
        assert exc.error_id == "custom_trigger"

    def test_input_check_error_default_trigger(self):
        from ii_agent.agents.exceptions import InputCheckError, CheckTrigger

        exc = InputCheckError("input not allowed")
        assert exc.check_trigger == CheckTrigger.INPUT_NOT_ALLOWED

    def test_output_check_error_default_trigger(self):
        from ii_agent.agents.exceptions import OutputCheckError, CheckTrigger

        exc = OutputCheckError("output not allowed")
        assert exc.check_trigger == CheckTrigger.OUTPUT_NOT_ALLOWED

    def test_input_check_error_custom_trigger(self):
        from ii_agent.agents.exceptions import InputCheckError, CheckTrigger

        exc = InputCheckError("pii found", check_trigger=CheckTrigger.PII_DETECTED)
        assert exc.check_trigger == CheckTrigger.PII_DETECTED
