"""
Tests for the telemetry step handle.

The point of the degraded state is that "the step did not raise" and "the step
worked" are different claims. Every one of 601 recorded runs was a success while
a source was returning 403 and a third of events were being dropped.
"""
import pipeline_telemetry
from pipeline_telemetry import step


class TestStepHandle:
    def test_records_rows_and_notes(self):
        with step("unit-test") as s:
            s.rows(12)
            s.note(alpha=1, beta="two")
        assert s._rows == 12
        assert s._extra == {"alpha": 1, "beta": "two"}

    def test_ignores_a_missing_row_count(self):
        with step("unit-test") as s:
            s.rows(None)
        assert s._rows is None

    def test_coerces_a_numeric_string(self):
        with step("unit-test") as s:
            s.rows("7")
        assert s._rows == 7

    def test_ignores_an_uncountable_row_value(self):
        with step("unit-test") as s:
            s.rows("not a number")
        assert s._rows is None

    def test_notes_merge_across_calls(self):
        with step("unit-test") as s:
            s.note(a=1)
            s.note(b=2)
        assert s._extra == {"a": 1, "b": 2}

    def test_a_clean_run_is_not_degraded(self):
        with step("unit-test") as s:
            s.rows(3)
        assert s._degraded == []

    def test_degrade_records_a_reason(self):
        with step("unit-test") as s:
            s.degrade("source returned nothing")
        assert s._degraded == ["source returned nothing"]

    def test_degrade_accumulates_reasons(self):
        with step("unit-test") as s:
            s.degrade("first")
            s.degrade("second")
        assert s._degraded == ["first", "second"]

    def test_degrade_ignores_an_empty_reason(self):
        with step("unit-test") as s:
            s.degrade("")
        assert s._degraded == []

    def test_check_degrades_only_when_true(self):
        with step("unit-test") as s:
            s.check(False, "should not appear")
            s.check(True, "should appear")
        assert s._degraded == ["should appear"]


class TestStepContext:
    def test_body_runs_and_exceptions_propagate(self):
        ran = []
        try:
            with step("unit-test"):
                ran.append(True)
                raise ValueError("boom")
        except ValueError as exc:
            assert str(exc) == "boom"
        else:
            raise AssertionError("exception should propagate")
        assert ran == [True]

    def test_telemetry_failure_never_breaks_the_work(self, monkeypatch):
        """Supabase being unreachable must not stop the pipeline."""
        def explode(*a, **k):
            raise RuntimeError("supabase down")

        monkeypatch.setattr(pipeline_telemetry, "_insert_start", explode)
        done = []
        with step("unit-test") as s:
            s.rows(1)
            done.append(True)
        assert done == [True]
