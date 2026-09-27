"""Tests for ii_agent.agents.models.metrics — Metrics.__add__, __radd__, timer helpers."""

from __future__ import annotations


class TestMetricsAdd:
    def _m(self, **kw):
        from ii_agent.agents.models.metrics import Metrics

        return Metrics(**kw)

    def test_add_both_have_provider_metrics(self):
        """Lines 72-77, branches [72,73],[74,75],[76,77]."""
        a = self._m(input_tokens=10, provider_metrics={"latency": 1.0})
        b = self._m(input_tokens=20, provider_metrics={"calls": 5})
        result = a + b
        assert result.input_tokens == 30
        assert result.provider_metrics is not None
        assert "latency" in result.provider_metrics
        assert "calls" in result.provider_metrics

    def test_add_only_self_has_provider_metrics(self):
        """Branches [74,75],[76,80]: only self.provider_metrics set."""
        a = self._m(provider_metrics={"x": 1})
        b = self._m()
        result = a + b
        assert result.provider_metrics == {"x": 1}

    def test_add_only_other_has_provider_metrics(self):
        """Branches [74,76],[76,77]: only other.provider_metrics set."""
        a = self._m()
        b = self._m(provider_metrics={"y": 2})
        result = a + b
        assert result.provider_metrics == {"y": 2}

    def test_add_no_provider_metrics(self):
        """Branch [72,80]: neither has provider_metrics."""
        a = self._m(input_tokens=5)
        b = self._m(input_tokens=5)
        result = a + b
        assert result.provider_metrics is None

    def test_add_both_have_additional_metrics(self):
        """Lines 80-85, branches [80,81],[82,83],[84,85]."""
        a = self._m(additional_metrics={"a": 1})
        b = self._m(additional_metrics={"b": 2})
        result = a + b
        assert result.additional_metrics == {"a": 1, "b": 2}

    def test_add_only_self_has_additional_metrics(self):
        """Branch [82,83],[84,88]: only self."""
        a = self._m(additional_metrics={"x": 10})
        b = self._m()
        result = a + b
        assert result.additional_metrics == {"x": 10}

    def test_add_only_other_has_additional_metrics(self):
        """Branch [84,85],[84,88]: only other."""
        a = self._m()
        b = self._m(additional_metrics={"z": 5})
        result = a + b
        assert result.additional_metrics == {"z": 5}

    def test_add_both_have_duration(self):
        """Lines 88-89, branch [88,89]: both durations summed."""
        a = self._m(duration=1.5)
        b = self._m(duration=2.5)
        result = a + b
        assert result.duration == 4.0

    def test_add_only_self_has_duration(self):
        """Lines 90-91, branch [88,90]: only self.duration set."""
        a = self._m(duration=3.0)
        b = self._m()
        result = a + b
        assert result.duration == 3.0

    def test_add_only_other_has_duration(self):
        """Lines 92-93, branch [90,92]: only other.duration set."""
        a = self._m()
        b = self._m(duration=7.0)
        result = a + b
        assert result.duration == 7.0

    def test_add_neither_has_duration(self):
        """Branch [88,90],[90,92]: neither duration → None."""
        a = self._m()
        b = self._m()
        result = a + b
        assert result.duration is None

    def test_add_both_have_time_to_first_token(self):
        """Lines 96-97: both time_to_first_token summed."""
        a = self._m(time_to_first_token=0.5)
        b = self._m(time_to_first_token=0.3)
        result = a + b
        assert abs(result.time_to_first_token - 0.8) < 1e-9

    def test_add_only_self_has_ttft(self):
        """Lines 98-99: only self.time_to_first_token."""
        a = self._m(time_to_first_token=1.2)
        b = self._m()
        result = a + b
        assert result.time_to_first_token == 1.2

    def test_add_only_other_has_ttft(self):
        """Lines 100-101: only other.time_to_first_token."""
        a = self._m()
        b = self._m(time_to_first_token=0.9)
        result = a + b
        assert result.time_to_first_token == 0.9

    def test_add_returns_correct_type(self):
        """Line 57-58: result_class = type(self) so subclass __add__ works."""
        a = self._m(input_tokens=1)
        b = self._m(input_tokens=2)
        result = a + b
        assert type(result).__name__ == "Metrics"

    def test_radd_with_zero(self):
        """Lines 106-107: sum() compatibility — 0 + Metrics returns self."""
        from ii_agent.agents.models.metrics import Metrics

        m = Metrics(input_tokens=5)
        result = m.__radd__(0)
        assert result is m

    def test_radd_with_metrics(self):
        """Line 108: Metrics + Metrics via __radd__."""
        a = self._m(input_tokens=3)
        b = self._m(input_tokens=7)
        result = b.__radd__(a)
        assert result.input_tokens == 10

    def test_sum_multiple_metrics(self):
        """sum() uses __radd__ with zero start value."""
        from ii_agent.agents.models.metrics import Metrics

        items = [Metrics(input_tokens=i) for i in range(1, 4)]
        total = sum(items)
        assert total.input_tokens == 6


class TestMetricsTimerHelpers:
    def _m(self, **kw):
        from ii_agent.agents.models.metrics import Metrics

        return Metrics(**kw)

    def test_start_timer_creates_timer(self):
        """Lines 111-113: creates Timer and starts it."""
        m = self._m()
        assert m.timer is None
        m.start_timer()
        assert m.timer is not None

    def test_start_timer_reuses_existing(self):
        """Branch [111,-115]: timer already exists → reuse."""
        m = self._m()
        m.start_timer()
        t1 = m.timer
        m.start_timer()
        assert m.timer is t1  # same object

    def test_stop_timer_sets_duration(self):
        """Lines 116-119: stop_timer updates duration."""
        m = self._m()
        m.start_timer()
        m.stop_timer()
        assert m.duration is not None
        assert m.duration >= 0.0

    def test_stop_timer_no_duration_update(self):
        """Branch [118,-115]: set_duration=False → duration not updated."""
        m = self._m()
        m.start_timer()
        m.stop_timer(set_duration=False)
        assert m.duration is None

    def test_set_time_to_first_token(self):
        """Lines 122-123: timer elapsed stored."""
        m = self._m()
        m.start_timer()
        m.set_time_to_first_token()
        assert m.time_to_first_token is not None

    def test_stop_timer_when_no_timer(self):
        """Branch [116,-115]: timer is None → no-op."""
        m = self._m()
        m.stop_timer()  # must not raise
        assert m.duration is None

    def test_set_ttft_when_no_timer(self):
        """Branch: timer is None → no-op."""
        m = self._m()
        m.set_time_to_first_token()  # must not raise
        assert m.time_to_first_token is None
