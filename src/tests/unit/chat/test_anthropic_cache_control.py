"""Tests for ii_agent.chat.llm.anthropic.cache_control — AnthropicCacheControl and CacheControlValidator."""

from __future__ import annotations


class TestAnthropicCacheControl:
    def test_to_dict_no_ttl(self):
        """Line 21-22: ttl is None → only type in result."""
        from ii_agent.chat.llm.anthropic.cache_control import AnthropicCacheControl

        cc = AnthropicCacheControl()
        d = cc.to_dict()
        assert d == {"type": "ephemeral"}
        assert "ttl" not in d

    def test_to_dict_with_ttl(self):
        """Lines 22-23: ttl set → included in result."""
        from ii_agent.chat.llm.anthropic.cache_control import AnthropicCacheControl

        cc = AnthropicCacheControl(ttl="1h")
        d = cc.to_dict()
        assert d == {"type": "ephemeral", "ttl": "1h"}

    def test_to_dict_with_5m_ttl(self):
        from ii_agent.chat.llm.anthropic.cache_control import AnthropicCacheControl

        cc = AnthropicCacheControl(ttl="5m")
        d = cc.to_dict()
        assert d["ttl"] == "5m"


class TestCacheControlValidator:
    def _make(self):
        from ii_agent.chat.llm.anthropic.cache_control import CacheControlValidator

        return CacheControlValidator()

    def _cc(self, ttl=None):
        from ii_agent.chat.llm.anthropic.cache_control import AnthropicCacheControl

        return AnthropicCacheControl(ttl=ttl)

    def test_get_cache_control_returns_none_when_none_passed(self):
        """Branch [73,74]: cache_control is None → return None."""
        v = self._make()
        result = v.get_cache_control(None, {"type": "text", "can_cache": True})
        assert result is None

    def test_get_cache_control_unsupported_context(self):
        """Lines 73-85, branch [73,77],[77,78]: can_cache=False → warning, return None."""
        v = self._make()
        result = v.get_cache_control(self._cc(), {"type": "tool_result", "can_cache": False})
        assert result is None
        warnings = v.get_warnings()
        assert len(warnings) == 1
        assert warnings[0].type == "unsupported-setting"

    def test_get_cache_control_valid(self):
        """Lines 88, 100: breakpoint within limit → returns dict."""
        v = self._make()
        result = v.get_cache_control(self._cc(), {"type": "text", "can_cache": True})
        assert result == {"type": "ephemeral"}

    def test_get_cache_control_exceeds_limit(self):
        """Lines 88-98, branch [88,89],[89,90]: exceeds 4 breakpoints."""
        v = self._make()
        ctx = {"type": "text", "can_cache": True}
        for _ in range(4):
            v.get_cache_control(self._cc(), ctx)
        # 5th should be rejected
        result = v.get_cache_control(self._cc(), ctx)
        assert result is None
        warnings = v.get_warnings()
        assert any("exceeded" in w.details for w in warnings)

    def test_get_warnings_returns_copy(self):
        """Line 108: returns a copy of warnings list."""
        v = self._make()
        w1 = v.get_warnings()
        w2 = v.get_warnings()
        assert w1 is not w2

    def test_reset_clears_state(self):
        """Lines 112-113: reset clears breakpoint count and warnings."""
        v = self._make()
        ctx = {"type": "text", "can_cache": True}
        v.get_cache_control(self._cc(), ctx)
        v.reset()
        # After reset, can use 4 more breakpoints
        for _ in range(4):
            result = v.get_cache_control(self._cc(), ctx)
            assert result is not None
        assert v.get_warnings() == []

    def test_cache_control_warning_dataclass(self):
        """Lines 54-55: CacheControlWarning with all fields."""
        from ii_agent.chat.llm.anthropic.cache_control import CacheControlWarning

        w = CacheControlWarning(
            type="unsupported-setting",
            setting="cacheControl",
            details="test details",
        )
        assert w.type == "unsupported-setting"
        assert w.setting == "cacheControl"
        assert w.details == "test details"

    def test_cache_control_warning_minimal(self):
        from ii_agent.chat.llm.anthropic.cache_control import CacheControlWarning

        w = CacheControlWarning(type="other")
        assert w.setting is None
        assert w.details is None
