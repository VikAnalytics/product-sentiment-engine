"""
Unit tests for the pure factor math in sim_trader.

We only exercise functions that don't touch Supabase or OpenAI:
  - _top_cohort
  - _score_candidates (with synthetic inputs)
  - _apply_ev_gate (including strong-signal override)
  - _apply_signal_consensus
  - _check_regime
  - _kelly_size
"""
import sim_trader as st


def _make_candidate(tid, ticker, avg_score=5.0, tag="opportunity", sector="Technology"):
    return {
        "target_id": tid,
        "ticker": ticker,
        "name": ticker,
        "sector": sector,
        "avg_score": avg_score,
        "dominant_tag": tag,
    }


class TestTopCohort:
    def test_empty(self):
        assert st._top_cohort([]) == []

    def test_respects_floor(self):
        scored = [{"composite_score": i} for i in range(3)]
        # divisor 3, min 4 → floor kicks in (3 < 4 → keep all 3, not 1)
        out = st._top_cohort(scored)
        assert len(out) == 3

    def test_takes_top_third_above_floor(self):
        scored = [{"composite_score": -i} for i in range(15)]
        out = st._top_cohort(scored)
        # 15 // 3 = 5, exceeds floor of 4
        assert len(out) == 5


class TestScoreCandidates:
    def test_produces_composite_for_each_candidate(self):
        cands = [
            _make_candidate(1, "AAA"),
            _make_candidate(2, "BBB"),
            _make_candidate(3, "CCC"),
        ]
        daily_returns = {1: [0.01] * 6, 2: [-0.01] * 6, 3: [0.0] * 6}
        reactions = {1: [0.05, 0.04], 2: [-0.05], 3: []}
        sentiment_hist = {1: [], 2: [], 3: []}
        out = st._score_candidates(cands, daily_returns, reactions, sentiment_hist, {})
        assert len(out) == 3
        for c in out:
            assert "composite_score" in c
            assert "factors" in c
            assert set(c["factors"].keys()) == {
                "sentiment_momentum", "price_momentum", "inv_volatility",
                "signal_consistency", "historical_accuracy", "macro_exposure",
            }

    def test_sorts_descending(self):
        cands = [_make_candidate(i, f"T{i}") for i in range(1, 5)]
        daily_returns = {i: [0.01 * i] * 6 for i in range(1, 5)}
        reactions = {i: [0.02 * i] for i in range(1, 5)}
        sentiment_hist = {i: [] for i in range(1, 5)}
        out = st._score_candidates(cands, daily_returns, reactions, sentiment_hist, {})
        comps = [c["composite_score"] for c in out]
        assert comps == sorted(comps, reverse=True)

    def test_macro_exposure_fed_through(self):
        cands = [_make_candidate(1, "AAA"), _make_candidate(2, "BBB")]
        out = st._score_candidates(
            cands, {1: [], 2: []}, {1: [], 2: []}, {1: [], 2: []},
            macro_exposure={1: 5.0, 2: -5.0},
        )
        by_ticker = {c["ticker"]: c for c in out}
        assert by_ticker["AAA"]["raw_factors"]["macro_exposure"] == 5.0
        assert by_ticker["BBB"]["raw_factors"]["macro_exposure"] == -5.0


class TestEvGate:
    def test_passes_with_good_stats(self):
        cands = [_make_candidate(1, "AAA")]
        reactions = {1: [0.05, 0.04, 0.06, 0.05, 0.04, 0.05]}  # all wins
        out = st._apply_ev_gate(cands, reactions)
        assert len(out) == 1
        assert out[0]["ev_stats"]["p_win"] == 1.0
        assert out[0]["ev_reduced"] is False

    def test_rejects_low_win_rate(self):
        cands = [_make_candidate(1, "AAA")]
        # 1 win, 5 losses → p_win = 0.167, below WIN_RATE_MIN=0.55
        reactions = {1: [0.05, -0.02, -0.02, -0.02, -0.02, -0.02]}
        assert st._apply_ev_gate(cands, reactions) == []

    def test_strong_signal_override(self):
        # High avg_score + opportunity tag + <5 reactions → override
        cands = [_make_candidate(1, "AAA", avg_score=8.0, tag="opportunity")]
        out = st._apply_ev_gate(cands, {1: []})
        assert len(out) == 1
        assert out[0]["ev_reduced"] is True
        assert out[0]["ev_stats"]["override"] is True

    def test_override_rejects_monitor_tag(self):
        cands = [_make_candidate(1, "AAA", avg_score=8.0, tag="monitor")]
        assert st._apply_ev_gate(cands, {1: []}) == []

    def test_override_rejects_low_score(self):
        cands = [_make_candidate(1, "AAA", avg_score=5.0, tag="opportunity")]
        assert st._apply_ev_gate(cands, {1: []}) == []


class TestSignalConsensus:
    def test_passes_when_above_min(self):
        cands = [{
            "ticker": "AAA",
            "factors": {
                "sentiment_momentum": 1.0,
                "price_momentum": 1.0,
                "inv_volatility": 1.0,
                "signal_consistency": -1.0,
                "historical_accuracy": -1.0,
                "macro_exposure": -1.0,
            },
        }]
        out = st._apply_signal_consensus(cands)
        assert len(out) == 1
        assert out[0]["signals_aligned"] == 3

    def test_rejects_when_below_min(self):
        cands = [{
            "ticker": "AAA",
            "factors": {
                "sentiment_momentum": 1.0,
                "price_momentum": -1.0,
                "inv_volatility": -1.0,
                "signal_consistency": -1.0,
                "historical_accuracy": -1.0,
                "macro_exposure": -1.0,
            },
        }]
        assert st._apply_signal_consensus(cands) == []


class TestCheckRegime:
    def test_risk_on_by_ratio(self):
        scored = [
            {"raw_factors": {"sentiment_momentum": 1.0}} for _ in range(5)
        ] + [{"raw_factors": {"sentiment_momentum": -1.0}} for _ in range(5)]
        # 5/10 = 50% ≥ 40% threshold
        assert st._check_regime(scored) is True

    def test_risk_on_by_absolute_count(self):
        # Small universe: 3 positives but only 3/10 = 30% below threshold,
        # count floor of 3 saves it
        scored = [
            {"raw_factors": {"sentiment_momentum": 1.0}} for _ in range(3)
        ] + [{"raw_factors": {"sentiment_momentum": -1.0}} for _ in range(7)]
        assert st._check_regime(scored) is True

    def test_risk_off(self):
        scored = [
            {"raw_factors": {"sentiment_momentum": 1.0}} for _ in range(2)
        ] + [{"raw_factors": {"sentiment_momentum": -1.0}} for _ in range(8)]
        assert st._check_regime(scored) is False

    def test_empty(self):
        assert st._check_regime([]) is False


class TestKellySize:
    def test_halves_allocation_when_ev_reduced(self):
        c_normal = {
            "target_id": 1, "ticker": "AAA", "name": "A", "sector": "",
            "composite_score": 1.0,
            "ev_stats": {"p_win": 0.70, "avg_gain": 0.05, "avg_loss": -0.02, "ev": 0.025},
            "ev_reduced": False, "factors": {},
        }
        c_reduced = {**c_normal, "target_id": 2, "ticker": "BBB", "ev_reduced": True}

        mw = {1: 0.25, 2: 0.25}
        allocs = st._kelly_size([c_normal, c_reduced], mw, cash=1000.0)
        by_ticker = {a["ticker"]: a for a in allocs}
        assert by_ticker["BBB"]["usd_amount"] < by_ticker["AAA"]["usd_amount"]

    def test_respects_deploy_multiplier(self):
        c = {
            "target_id": 1, "ticker": "AAA", "name": "A", "sector": "",
            "composite_score": 1.0,
            "ev_stats": {"p_win": 0.70, "avg_gain": 0.05, "avg_loss": -0.02, "ev": 0.025},
            "ev_reduced": False, "factors": {},
        }
        full = st._kelly_size([c], {1: 1.0}, cash=1000.0, deploy_multiplier=1.0)
        partial = st._kelly_size([c], {1: 1.0}, cash=1000.0, deploy_multiplier=0.25)
        assert full[0]["usd_amount"] > partial[0]["usd_amount"]
        assert partial[0]["usd_amount"] == round(full[0]["usd_amount"] * 0.25, 2)
