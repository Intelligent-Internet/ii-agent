"""Tests for ii_agent.agents.runs.messages — RunMessages.get_input_messages."""

from __future__ import annotations

from unittest.mock import MagicMock


class TestRunMessages:
    def _msg(self):
        """Return a minimal mock Message."""
        return MagicMock()

    def _make(self, **kwargs):
        from ii_agent.agents.runs.messages import RunMessages

        return RunMessages(**kwargs)

    def test_get_input_messages_all_none(self):
        """No system, user, or extra → empty list."""
        rm = self._make()
        assert rm.get_input_messages() == []

    def test_get_input_messages_system_only(self):
        """Branch [26, 27]: system_message present."""
        sys_msg = self._msg()
        rm = self._make(system_message=sys_msg)
        result = rm.get_input_messages()
        assert result == [sys_msg]

    def test_get_input_messages_user_only(self):
        """Branch [28, 29]: user_message present."""
        usr_msg = self._msg()
        rm = self._make(user_message=usr_msg)
        result = rm.get_input_messages()
        assert result == [usr_msg]

    def test_get_input_messages_extra_only(self):
        """Branch [30, 31]: extra_messages present."""
        e1, e2 = self._msg(), self._msg()
        rm = self._make(extra_messages=[e1, e2])
        result = rm.get_input_messages()
        assert result == [e1, e2]

    def test_get_input_messages_all_present(self):
        """All three present: system + user + extra."""
        sys_msg, usr_msg, e1 = self._msg(), self._msg(), self._msg()
        rm = self._make(system_message=sys_msg, user_message=usr_msg, extra_messages=[e1])
        result = rm.get_input_messages()
        assert result == [sys_msg, usr_msg, e1]

    def test_get_input_messages_none_branches(self):
        """Branch [26, 28] and [28, 30]: system/user absent but extra present."""
        e1 = self._msg()
        rm = self._make(extra_messages=[e1])
        assert rm.get_input_messages() == [e1]

    def test_get_input_messages_returns_copy(self):
        """Returned list is a fresh list, not the stored one."""
        e1 = self._msg()
        rm = self._make(extra_messages=[e1])
        r1 = rm.get_input_messages()
        r2 = rm.get_input_messages()
        assert r1 is not r2
