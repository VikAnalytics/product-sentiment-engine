"""
Tests for the backtest harness's as-of slicing.

A backtest that can see the future is worse than no backtest, because it produces
a confident number that is wrong in the flattering direction. price_reactions is
the dangerous table: each row describes how a stock moved *after* an event, so
reading the whole table hands the EV gate the answers.

These exercise the slicing directly, with a hand-built history and no database.
"""
import os
import sys
from datetime import date, datetime, timezone

import pytest

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_root, "scripts"))

bt = pytest.importorskip("backtest")


class FakeHistory(bt.History):
    """Builds a History without touching Supabase."""

    def __init__(self, sentiment=None, reactions=None, closes=None, targets=None):
        self.targets = targets or {
            1: {"id": 1, "name": "Acme", "ticker": "ACME", "sector": "Technology",
                "target_type": "COMPANY", "status": "tracking"},
            2: {"id": 2, "name": "Beta", "ticker": "BETA", "sector": "Retail",
                "target_type": "COMPANY", "status": "tracking"},
        }
        self.sentiment = sorted(sentiment or [], key=lambda r: r["created_at"])
        self.reactions = sorted(reactions or [], key=lambda r: r["computed_at"] or "")
        self.closes = closes or {}
        self.opens = {}
        self.trading_days = sorted({d for days in self.closes.values() for d in days})
        self.macro_exposure_rows = []


def _sent(tid, day, score, tag="opportunity"):
    return {"target_id": tid, "sentiment_score": score, "implication_tag": tag,
            "created_at": f"{day}T12:00:00+00:00"}


def _reaction(tid, computed_day, pct):
    return {"target_id": tid, "reaction_7d": pct, "confidence": "high",
            "computed_at": f"{computed_day}T12:00:00+00:00"}


class TestReactionsAsOf:
    def test_excludes_reactions_computed_after_the_decision(self):
        hist = FakeHistory(reactions=[
            _reaction(1, "2026-04-01", 5.0),
            _reaction(1, "2026-04-20", 9.0),   # after the decision date
        ])
        out = hist.reactions_as_of(date(2026, 4, 10), [1])
        assert out[1] == [0.05, 0.05]          # only the earlier one, weighted x2 for high

    def test_excludes_a_reaction_computed_the_same_day(self):
        """Same-day is still the future: the decision is made before the day's close."""
        hist = FakeHistory(reactions=[_reaction(1, "2026-04-10", 5.0)])
        assert hist.reactions_as_of(date(2026, 4, 10), [1]) == {}

    def test_converts_percentages_to_fractions(self):
        hist = FakeHistory(reactions=[_reaction(1, "2026-04-01", 5.88)])
        assert hist.reactions_as_of(date(2026, 4, 10), [1])[1][0] == pytest.approx(0.0588)

    def test_ignores_targets_not_asked_for(self):
        hist = FakeHistory(reactions=[_reaction(2, "2026-04-01", 5.0)])
        assert hist.reactions_as_of(date(2026, 4, 10), [1]) == {}


class TestCandidatesAsOf:
    def test_excludes_sentiment_from_the_future(self):
        hist = FakeHistory(sentiment=[_sent(1, "2026-04-20", 8)])
        assert hist.candidates(date(2026, 4, 10), 3) == []

    def test_includes_sentiment_inside_the_lookback(self):
        hist = FakeHistory(sentiment=[_sent(1, "2026-04-09", 8)])
        out = hist.candidates(date(2026, 4, 10), 3)
        assert len(out) == 1 and out[0]["ticker"] == "ACME"

    def test_excludes_sentiment_older_than_the_lookback(self):
        hist = FakeHistory(sentiment=[_sent(1, "2026-03-01", 8)])
        assert hist.candidates(date(2026, 4, 10), 3) == []

    def test_applies_the_minimum_score(self):
        hist = FakeHistory(sentiment=[_sent(1, "2026-04-09", 2)])
        assert hist.candidates(date(2026, 4, 10), 3) == []

    def test_skips_targets_with_no_ticker(self):
        targets = {1: {"id": 1, "name": "Private Co", "ticker": None, "sector": "Technology",
                       "target_type": "COMPANY", "status": "tracking"}}
        hist = FakeHistory(sentiment=[_sent(1, "2026-04-09", 8)], targets=targets)
        assert hist.candidates(date(2026, 4, 10), 3) == []

    def test_skips_macro_themes(self):
        targets = {1: {"id": 1, "name": "US-China", "ticker": "XX", "sector": None,
                       "target_type": "MACRO", "status": "tracking"}}
        hist = FakeHistory(sentiment=[_sent(1, "2026-04-09", 8)], targets=targets)
        assert hist.candidates(date(2026, 4, 10), 3) == []

    def test_averages_multiple_readings(self):
        hist = FakeHistory(sentiment=[_sent(1, "2026-04-09", 4), _sent(1, "2026-04-09", 8)])
        assert hist.candidates(date(2026, 4, 10), 3)[0]["avg_score"] == 6.0

    def test_dominant_tag_prefers_threat(self):
        hist = FakeHistory(sentiment=[
            _sent(1, "2026-04-09", 8, "monitor"),
            _sent(1, "2026-04-09", 8, "threat"),
        ])
        assert hist.candidates(date(2026, 4, 10), 3)[0]["dominant_tag"] == "threat"


class TestDailyReturns:
    def test_uses_only_closes_before_the_decision_day(self):
        hist = FakeHistory(closes={1: {
            "2026-04-08": 100.0, "2026-04-09": 110.0, "2026-04-10": 500.0,
        }})
        rets = hist.daily_returns(date(2026, 4, 10), [1])
        # One return, from the 8th to the 9th. The spike on the 10th is the future.
        assert len(rets[1]) == 1
        assert rets[1][0] == pytest.approx(0.0953, abs=1e-3)

    def test_no_history_yields_no_entry(self):
        hist = FakeHistory(closes={1: {"2026-04-10": 100.0}})
        assert hist.daily_returns(date(2026, 4, 10), [1]) == {}


class TestSentimentHistory:
    def test_excludes_the_future_and_keeps_the_window(self):
        hist = FakeHistory(sentiment=[
            _sent(1, "2026-04-01", 5),
            _sent(1, "2026-04-20", 9),
        ])
        out = hist.sentiment_history(date(2026, 4, 10), [1])
        assert len(out[1]) == 1 and out[1][0][1] == 5


class TestClosePrice:
    def test_falls_back_to_the_most_recent_earlier_close(self):
        hist = FakeHistory(closes={1: {"2026-04-08": 100.0, "2026-04-09": 110.0}})
        assert hist.close_price(1, "2026-04-10") == 110.0

    def test_returns_none_when_nothing_is_known_yet(self):
        hist = FakeHistory(closes={1: {"2026-04-20": 100.0}})
        assert hist.close_price(1, "2026-04-10") is None


class TestScoringClock:
    def test_score_candidates_accepts_an_as_of_time(self):
        """Without this the replay scores April data against today's clock, every
        reading falls outside the momentum window, and the regime filter calls
        every day risk-off."""
        import sim_trader as st
        candidate = {"target_id": 1, "ticker": "ACME", "name": "Acme",
                     "sector": "Technology", "avg_score": 8.0, "dominant_tag": "opportunity"}
        hist = {1: [("2026-04-09T12:00:00+00:00", 8, "opportunity"),
                    ("2026-04-02T12:00:00+00:00", 2, "monitor")]}
        as_of = datetime(2026, 4, 10, tzinfo=timezone.utc)
        scored = st._score_candidates([candidate], {}, {}, hist, {1: 0.0}, as_of=as_of)
        assert scored[0]["raw_factors"]["sentiment_momentum"] > 0

    def test_todays_clock_sees_no_momentum_in_old_data(self):
        """The failure this guards against: with the default clock, months-old
        readings sit outside both momentum windows and read as flat."""
        import sim_trader as st
        candidate = {"target_id": 1, "ticker": "ACME", "name": "Acme",
                     "sector": "Technology", "avg_score": 8.0, "dominant_tag": "opportunity"}
        hist = {1: [("2026-04-09T12:00:00+00:00", 8, "opportunity"),
                    ("2026-04-02T12:00:00+00:00", 2, "monitor")]}
        scored = st._score_candidates([candidate], {}, {}, hist, {1: 0.0})
        assert scored[0]["raw_factors"]["sentiment_momentum"] == 0
