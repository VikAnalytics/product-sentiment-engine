"""
sim_trader.py — Quantitative AI Portfolio Simulation.

Five-layer strategy:
  1. Multi-Factor Ranking (sentiment momentum, price momentum, volatility,
     signal consistency, historical accuracy) — Z-scored and composited
  2. EV Gate: only invest when p_win > 55% AND EV > 3% (from price_reactions history)
  3. Signal Consensus: 4/5 factors must agree directionally
  4. Regime Filter: ≥50% of universe positive before any new buys
  5. Mean-Variance Optimization (Markowitz max-Sharpe) with Kelly position caps

Risk management in execute:
  - Stop-loss: -8% from avg cost
  - Take-profit: +25%
  - Sentiment stop: tag='threat' or today's score < -3
  - Max drawdown: -15% from portfolio peak → liquidate all

AI role: narrator only — explains quant decisions, does not pick stocks.

Usage:
    PYTHONPATH=src python src/sim_trader.py --action execute
    PYTHONPATH=src python src/sim_trader.py --action analyze
    PYTHONPATH=src python src/sim_trader.py --action snapshot
"""

import argparse
import json
import logging
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import numpy as np

_src_dir = os.path.dirname(os.path.abspath(__file__))
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from config import (
    get_supabase,
    get_json_model,
    SIM_STARTING_CAPITAL,
    SIM_MAX_POSITIONS,
    SIM_MIN_SCORE,
    SIM_SENTIMENT_LOOKBACK_HOURS,
)

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO"), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger(__name__)

# ── Strategy constants ─────────────────────────────────────────────────────
STOP_LOSS_PCT          = 0.08   # sell if down 8% from avg cost
TAKE_PROFIT_PCT        = 0.25   # sell if up 25%
SENTIMENT_STOP_SCORE   = -3     # sell if today's avg score drops below this
MAX_DRAWDOWN_PCT       = 0.15   # liquidate all if portfolio down 15% from peak
REGIME_THRESHOLD       = 0.50   # 50% of universe must have positive sentiment momentum
EV_MIN               = 0.03   # 3% minimum expected value to deploy capital
WIN_RATE_MIN           = 0.55   # 55% minimum historical win rate
MIN_REACTIONS_SAMPLE   = 5     # minimum past reactions needed for EV gate
SIGNAL_CONSENSUS_MIN   = 4     # need 4 of 5 factors aligned positively
MAX_POSITION_WEIGHT    = 0.30   # Markowitz upper bound per stock
KELLY_CAP              = 0.25   # cap individual Kelly fraction at 25%
MAX_DEPLOY_FRACTION    = 0.80   # deploy at most 80% of available cash
PRICE_MOMENTUM_DAYS    = 20    # lookback for price momentum + covariance
SENTIMENT_MOMENTUM_DAYS = 7    # days for sentiment momentum window

# Factor weights (must sum to 1.0)
FACTOR_WEIGHTS = {
    "sentiment_momentum":  0.30,
    "price_momentum":      0.25,
    "inv_volatility":      0.15,
    "signal_consistency":  0.15,
    "historical_accuracy": 0.15,
}


# ── Shared helpers ─────────────────────────────────────────────────────────

def _parse_ts(s: str) -> datetime:
    s = re.sub(r"(\.\d+)", lambda m: m.group(1).ljust(7, "0")[:7], s)
    return datetime.fromisoformat(s)


def _fetch_open_price(sb, target_id: int, for_date: date) -> Optional[float]:
    """First 5-min bar price (open → close fallback) for target on date."""
    day_start = f"{for_date.isoformat()}T00:00:00+00:00"
    day_end = f"{(for_date + timedelta(days=1)).isoformat()}T00:00:00+00:00"
    try:
        resp = (
            sb.table("stock_prices")
            .select("open, close")
            .eq("target_id", target_id)
            .gte("ts", day_start)
            .lt("ts", day_end)
            .order("ts")
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            return None
        row = rows[0]
        val = row.get("open") or row.get("close")
        return float(val) if val is not None else None
    except Exception as exc:
        log.error("_fetch_open_price(%s, %s): %s", target_id, for_date, exc)
        return None


def _get_portfolio(sb) -> dict:
    resp = sb.table("sim_portfolio").select("id, cash_usd, peak_value").limit(1).execute()
    rows = resp.data or []
    if not rows:
        raise RuntimeError("sim_portfolio empty — apply migration 015_simulator.sql first")
    return rows[0]


def _get_holding(sb, ticker: str) -> Optional[dict]:
    resp = (
        sb.table("sim_holdings")
        .select("id, target_id, ticker, shares, avg_buy_price, total_cost")
        .eq("ticker", ticker)
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    return rows[0] if rows else None


def _get_all_holdings(sb) -> list:
    resp = sb.table("sim_holdings").select("*").execute()
    return resp.data or []


def _update_peak_value(sb, portfolio: dict, total_value: float) -> None:
    """Update peak_value if total_value is a new high."""
    current_peak = float(portfolio.get("peak_value") or SIM_STARTING_CAPITAL)
    if total_value > current_peak:
        sb.table("sim_portfolio").update({
            "peak_value": total_value,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", portfolio["id"]).execute()


def _liquidate_all(sb, portfolio: dict, today: date, reason: str) -> float:
    """Force-sell all holdings. Returns updated cash balance."""
    holdings = _get_all_holdings(sb)
    cash = float(portfolio["cash_usd"])
    for h in holdings:
        ticker = h["ticker"]
        price = _fetch_open_price(sb, h["target_id"], today)
        if price is None:
            price = float(h["avg_buy_price"])  # fallback to cost
        shares = float(h["shares"])
        proceeds = round(shares * price, 2)
        pnl = round(proceeds - float(h["total_cost"]), 2)
        cash = round(cash + proceeds, 2)
        sb.table("sim_trades").insert({
            "trade_date": today.isoformat(),
            "target_id": h["target_id"],
            "ticker": ticker,
            "action": "SELL",
            "shares": shares,
            "price": round(price, 4),
            "usd_value": proceeds,
            "pnl_usd": pnl,
            "status": "executed",
            "ai_rationale": f"FORCED: {reason}",
        }).execute()
        sb.table("sim_holdings").delete().eq("ticker", ticker).execute()
        log.info("liquidate: SELL %s @ $%.2f (reason: %s, P&L: $%.2f)", ticker, price, reason, pnl)
    if holdings:
        sb.table("sim_portfolio").update({
            "cash_usd": cash,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", portfolio["id"]).execute()
    return cash


# ── Data fetchers for analysis ─────────────────────────────────────────────

def _fetch_daily_returns(sb, target_ids: list) -> dict:
    """
    Fetch daily close prices for each target (last PRICE_MOMENTUM_DAYS+2 trading days)
    and compute daily log returns. Returns {target_id: [returns]}.
    """
    since = (date.today() - timedelta(days=PRICE_MOMENTUM_DAYS + 10)).isoformat() + "T00:00:00+00:00"
    result = {}

    for tid in target_ids:
        rows = []
        offset = 0
        while True:
            resp = (
                sb.table("stock_prices")
                .select("ts, close")
                .eq("target_id", tid)
                .gte("ts", since)
                .order("ts")
                .range(offset, offset + 999)
                .execute()
            )
            batch = resp.data or []
            rows.extend(batch)
            if len(batch) < 1000:
                break
            offset += 1000

        # Collapse to daily closes (last bar of each day)
        daily: dict = {}
        for row in rows:
            try:
                dt = _parse_ts(row["ts"]).date()
                daily[dt] = float(row["close"])
            except Exception:
                continue

        dates = sorted(daily.keys())
        closes = [daily[d] for d in dates]
        if len(closes) < 3:
            result[tid] = []
            continue

        # Log returns
        returns = [np.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
        result[tid] = returns[-PRICE_MOMENTUM_DAYS:]  # keep last N days

    return result


def _fetch_price_reactions_history(sb, target_ids: list) -> dict:
    """
    Fetch historical price_reactions for each target.
    Returns {target_id: [reaction_7d values]}.
    """
    result = defaultdict(list)
    for tid in target_ids:
        resp = (
            sb.table("price_reactions")
            .select("reaction_7d, confidence")
            .eq("target_id", tid)
            .not_.is_("reaction_7d", "null")
            .execute()
        )
        for row in (resp.data or []):
            val = row.get("reaction_7d")
            if val is not None:
                # Weight high-confidence reactions more
                weight = {"high": 2, "medium": 1, "low": 0.5}.get(row.get("confidence", "low"), 1)
                result[tid].extend([float(val)] * int(weight))
    return dict(result)


def _fetch_sentiment_history(sb, target_ids: list) -> dict:
    """
    Fetch sentiment scores for last 14 days per target.
    Returns {target_id: [(created_at, score, tag)]}.
    """
    since_str = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
    result = defaultdict(list)

    rows = []
    offset = 0
    while True:
        resp = (
            sb.table("sentiment")
            .select("target_id, sentiment_score, implication_tag, created_at")
            .in_("target_id", target_ids)
            .gte("created_at", since_str)
            .not_.is_("sentiment_score", "null")
            .range(offset, offset + 999)
            .execute()
        )
        batch = resp.data or []
        rows.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000

    for row in rows:
        tid = row["target_id"]
        result[tid].append((row["created_at"], row["sentiment_score"], row.get("implication_tag")))

    return dict(result)


def _fetch_todays_sentiment_tags(sb, tickers: list) -> dict:
    """
    Fetch today's dominant implication_tag and avg score per ticker (for sentiment stop).
    Returns {ticker: {"tag": str, "avg_score": float}}.
    """
    if not tickers:
        return {}
    since_str = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

    # Map tickers to target_ids
    resp = (
        sb.table("targets")
        .select("id, ticker")
        .in_("ticker", tickers)
        .execute()
    )
    ticker_to_id = {r["ticker"]: r["id"] for r in (resp.data or [])}
    if not ticker_to_id:
        return {}

    target_ids = list(ticker_to_id.values())
    rows = []
    offset = 0
    while True:
        resp2 = (
            sb.table("sentiment")
            .select("target_id, sentiment_score, implication_tag")
            .in_("target_id", target_ids)
            .gte("created_at", since_str)
            .not_.is_("sentiment_score", "null")
            .range(offset, offset + 999)
            .execute()
        )
        batch = resp2.data or []
        rows.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000

    id_to_ticker = {v: k for k, v in ticker_to_id.items()}
    by_target: dict = defaultdict(lambda: {"scores": [], "tags": []})
    for row in rows:
        tid = row["target_id"]
        by_target[tid]["scores"].append(row["sentiment_score"])
        if row.get("implication_tag"):
            by_target[tid]["tags"].append(row["implication_tag"])

    tag_priority = {"threat": 0, "opportunity": 1, "monitor": 2, "no_action": 3}
    result = {}
    for tid, data in by_target.items():
        ticker = id_to_ticker.get(tid)
        if not ticker:
            continue
        avg_score = sum(data["scores"]) / len(data["scores"]) if data["scores"] else 0
        dominant_tag = min(data["tags"], key=lambda t: tag_priority.get(t, 99)) if data["tags"] else "monitor"
        result[ticker] = {"tag": dominant_tag, "avg_score": avg_score}
    return result


# ── Layer 1: Multi-Factor Scoring ──────────────────────────────────────────

def _compute_factors(candidates: list, daily_returns: dict,
                     reactions: dict, sentiment_hist: dict) -> list:
    """
    Compute 5 raw factors for each candidate, Z-score normalize, compute composite.
    Returns candidates enriched with factor scores, sorted by composite_score desc.
    """
    now = datetime.now(timezone.utc)
    cutoff_recent = now - timedelta(days=SENTIMENT_MOMENTUM_DAYS)
    cutoff_prior  = now - timedelta(days=SENTIMENT_MOMENTUM_DAYS * 2)

    raw: list = []
    for c in candidates:
        tid = c["target_id"]

        # F1: Sentiment momentum — trend (recent avg - prior avg)
        hist = sentiment_hist.get(tid, [])
        recent_scores = [s for ts_str, s, _ in hist
                         if _parse_ts(ts_str).replace(tzinfo=timezone.utc) >= cutoff_recent]
        prior_scores  = [s for ts_str, s, _ in hist
                         if cutoff_prior <= _parse_ts(ts_str).replace(tzinfo=timezone.utc) < cutoff_recent]
        f1 = (sum(recent_scores) / len(recent_scores)) - (sum(prior_scores) / len(prior_scores)) \
             if recent_scores and prior_scores else (sum(recent_scores) / len(recent_scores) if recent_scores else 0.0)

        # F2: Price momentum — total return over PRICE_MOMENTUM_DAYS
        rets = daily_returns.get(tid, [])
        f2 = float(np.sum(rets)) if rets else 0.0  # sum of log returns ≈ total log return

        # F3: Inverse realized volatility (low vol = safer = higher score)
        f3 = -float(np.std(rets)) if len(rets) >= 5 else 0.0  # negative std so low vol = high score

        # F4: Signal consistency — fraction of recent sentiment rows that are positive
        all_scores = [s for _, s, _ in hist]
        f4 = sum(1 for s in all_scores if s > 0) / len(all_scores) if all_scores else 0.0

        # F5: Historical accuracy — confidence-weighted avg reaction_7d
        rxns = reactions.get(tid, [])
        f5 = float(np.mean(rxns)) if rxns else 0.0

        raw.append({**c, "_f1": f1, "_f2": f2, "_f3": f3, "_f4": f4, "_f5": f5})

    if not raw:
        return []

    # Z-score normalize each factor across the universe
    def _zscore(vals: list) -> list:
        arr = np.array(vals, dtype=float)
        std = arr.std()
        if std < 1e-9:
            return [0.0] * len(vals)
        return list((arr - arr.mean()) / std)

    keys = ["_f1", "_f2", "_f3", "_f4", "_f5"]
    factor_names = ["sentiment_momentum", "price_momentum", "inv_volatility",
                    "signal_consistency", "historical_accuracy"]
    z_matrix = {k: _zscore([r[k] for r in raw]) for k in keys}

    for i, r in enumerate(raw):
        composite = sum(
            FACTOR_WEIGHTS[name] * z_matrix[k][i]
            for k, name in zip(keys, factor_names)
        )
        r["composite_score"] = round(composite, 4)
        r["factors"] = {name: round(z_matrix[k][i], 3) for k, name in zip(keys, factor_names)}
        r["raw_factors"] = {name: round(r[k], 4) for k, name in zip(keys, factor_names)}

    # Top quintile only (top 20%)
    raw.sort(key=lambda x: x["composite_score"], reverse=True)
    cutoff_idx = max(1, len(raw) // 5)
    return raw[:cutoff_idx]


# ── Layer 2: EV Gate ───────────────────────────────────────────────────────

def _apply_ev_gate(candidates: list, reactions: dict) -> list:
    """
    Filter to only candidates where:
      - ≥ MIN_REACTIONS_SAMPLE historical reactions
      - p_win > WIN_RATE_MIN
      - EV > EV_MIN
    Enriches passing candidates with ev_stats.
    """
    passed = []
    for c in candidates:
        tid = c["target_id"]
        rxns = reactions.get(tid, [])

        if len(rxns) < MIN_REACTIONS_SAMPLE:
            log.debug("EV gate: %s skipped — only %d samples (need %d)",
                      c["ticker"], len(rxns), MIN_REACTIONS_SAMPLE)
            continue

        wins   = [r for r in rxns if r > 0]
        losses = [r for r in rxns if r <= 0]
        p_win  = len(wins) / len(rxns)
        avg_gain = float(np.mean(wins))   if wins   else 0.0
        avg_loss = float(np.mean(losses)) if losses else 0.0  # negative number

        ev = p_win * avg_gain + (1 - p_win) * avg_loss

        if p_win < WIN_RATE_MIN:
            log.info("EV gate: %s rejected — p_win=%.2f < %.2f", c["ticker"], p_win, WIN_RATE_MIN)
            continue
        if ev < EV_MIN:
            log.info("EV gate: %s rejected — EV=%.3f < %.3f", c["ticker"], ev, EV_MIN)
            continue

        passed.append({
            **c,
            "ev_stats": {
                "p_win": round(p_win, 3),
                "avg_gain": round(avg_gain, 4),
                "avg_loss": round(avg_loss, 4),
                "ev": round(ev, 4),
                "n_samples": len(rxns),
            },
        })
        log.info("EV gate: %s PASSED — p_win=%.2f, EV=%.3f, n=%d",
                 c["ticker"], p_win, ev, len(rxns))
    return passed


# ── Layer 3: Signal Consensus ──────────────────────────────────────────────

def _apply_signal_consensus(candidates: list) -> list:
    """
    Require SIGNAL_CONSENSUS_MIN of 5 factors to be positively aligned (z-score > 0).
    """
    passed = []
    factor_names = ["sentiment_momentum", "price_momentum", "inv_volatility",
                    "signal_consistency", "historical_accuracy"]
    for c in candidates:
        factors = c.get("factors", {})
        positive_count = sum(1 for name in factor_names if factors.get(name, 0) > 0)
        if positive_count >= SIGNAL_CONSENSUS_MIN:
            c["signals_aligned"] = positive_count
            passed.append(c)
            log.info("Consensus: %s PASSED — %d/5 signals aligned", c["ticker"], positive_count)
        else:
            log.info("Consensus: %s rejected — only %d/5 signals aligned (need %d)",
                     c["ticker"], positive_count, SIGNAL_CONSENSUS_MIN)
    return passed


# ── Layer 4: Regime Filter ─────────────────────────────────────────────────

def _check_regime(all_candidates_raw: list) -> bool:
    """
    True if ≥ REGIME_THRESHOLD fraction of the full universe has positive
    sentiment momentum (F1 > 0 before z-scoring).
    """
    if not all_candidates_raw:
        return False
    positive = sum(1 for c in all_candidates_raw if c.get("raw_factors", {}).get("sentiment_momentum", 0) > 0)
    ratio = positive / len(all_candidates_raw)
    log.info("Regime: %.0f%% of universe positive (threshold %.0f%%)",
             ratio * 100, REGIME_THRESHOLD * 100)
    return ratio >= REGIME_THRESHOLD


# ── Layer 5a: Markowitz Max-Sharpe Optimization ────────────────────────────

def _markowitz_optimize(candidates: list, daily_returns: dict) -> dict:
    """
    Maximum Sharpe ratio portfolio using scipy.optimize.
    Returns {target_id: weight} — weights sum to 1 over passing assets.
    Falls back to equal-weight if optimization fails or insufficient data.
    """
    try:
        from scipy.optimize import minimize
    except ImportError:
        log.warning("scipy not installed — falling back to equal-weight allocation")
        n = len(candidates)
        return {c["target_id"]: 1.0 / n for c in candidates}

    tids = [c["target_id"] for c in candidates]
    n = len(tids)
    if n == 0:
        return {}
    if n == 1:
        return {tids[0]: 1.0}

    # Build returns matrix (rows=days, cols=assets)
    ret_lists = [daily_returns.get(tid, []) for tid in tids]
    min_len = min(len(r) for r in ret_lists)

    if min_len < 5:
        log.warning("Markowitz: insufficient return history (%d days) — equal-weight fallback", min_len)
        return {tid: 1.0 / n for tid in tids}

    R = np.array([r[-min_len:] for r in ret_lists], dtype=float)  # shape (n, min_len)

    # Expected returns: blend historical mean + composite_score signal
    mu_hist = R.mean(axis=1)
    comp_scores = np.array([c["composite_score"] for c in candidates])
    # Scale composite scores to return units (~2% per z-score unit, weekly)
    mu_signal = comp_scores * 0.02
    mu = 0.5 * mu_hist + 0.5 * mu_signal

    # Covariance with Ledoit-Wolf-style shrinkage toward diagonal
    cov_raw = np.cov(R)
    if cov_raw.ndim == 0:  # single asset edge case
        cov_raw = np.array([[float(cov_raw)]])
    diag_mean = np.trace(cov_raw) / n
    alpha_shrink = 0.1  # 10% shrink toward diagonal
    cov = (1 - alpha_shrink) * cov_raw + alpha_shrink * diag_mean * np.eye(n)
    # Small regularization to ensure positive definite
    cov += np.eye(n) * 1e-8

    rf = 0.0  # risk-free rate (0 for simplicity)

    def neg_sharpe(w):
        port_ret = np.dot(w, mu)
        port_var = w @ cov @ w
        port_std = np.sqrt(max(port_var, 1e-12))
        return -(port_ret - rf) / port_std

    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    bounds = [(0.0, MAX_POSITION_WEIGHT)] * n
    w0 = np.ones(n) / n  # equal-weight starting point

    try:
        result = minimize(neg_sharpe, w0, method="SLSQP",
                          bounds=bounds, constraints=constraints,
                          options={"maxiter": 500, "ftol": 1e-9})
        if result.success or result.fun < neg_sharpe(w0):
            weights = np.clip(result.x, 0, MAX_POSITION_WEIGHT)
            weights /= weights.sum()
        else:
            log.warning("Markowitz: optimizer did not converge — equal-weight fallback")
            weights = np.ones(n) / n
    except Exception as exc:
        log.warning("Markowitz: optimization error (%s) — equal-weight fallback", exc)
        weights = np.ones(n) / n

    return {tid: float(w) for tid, w in zip(tids, weights)}


# ── Layer 5b: Kelly Position Sizing ───────────────────────────────────────

def _kelly_size(candidates: list, markowitz_weights: dict, cash: float) -> list:
    """
    Apply Kelly Criterion as an upper cap on each Markowitz weight.
    Kelly f* = (p_win * b - (1 - p_win)) / b  where b = avg_gain / |avg_loss|
    Final allocation = min(Markowitz_weight, Kelly_cap, MAX_POSITION_WEIGHT)
    Deploy at most MAX_DEPLOY_FRACTION of cash.
    Returns list of {target_id, ticker, usd_amount, allocation_pct, rationale_context}.
    """
    deployable = cash * MAX_DEPLOY_FRACTION
    allocations = []

    for c in candidates:
        tid = c["target_id"]
        mw = markowitz_weights.get(tid, 0.0)
        if mw < 0.01:
            continue

        ev_stats = c.get("ev_stats", {})
        p_win  = ev_stats.get("p_win",  WIN_RATE_MIN)
        avg_gain = abs(ev_stats.get("avg_gain", 0.02))
        avg_loss = abs(ev_stats.get("avg_loss", 0.01))

        if avg_loss < 1e-6:
            kelly_f = KELLY_CAP
        else:
            b = avg_gain / avg_loss  # odds ratio
            kelly_f = (p_win * b - (1 - p_win)) / b
            kelly_f = max(0.0, min(kelly_f, KELLY_CAP))  # clamp [0, KELLY_CAP]

        final_weight = min(mw, kelly_f, MAX_POSITION_WEIGHT)
        usd_amount = round(deployable * final_weight, 2)

        if usd_amount < 10.0:
            continue

        allocations.append({
            "target_id": tid,
            "ticker": c["ticker"],
            "name": c.get("name", ""),
            "sector": c.get("sector", ""),
            "usd_amount": usd_amount,
            "allocation_pct": round(final_weight * 100, 1),
            "markowitz_weight": round(mw, 3),
            "kelly_cap": round(kelly_f, 3),
            "composite_score": c.get("composite_score", 0),
            "ev_stats": ev_stats,
            "factors": c.get("factors", {}),
            "signals_aligned": c.get("signals_aligned", 0),
        })

    # Renormalize so we don't accidentally exceed deployable cash
    total_alloc = sum(a["usd_amount"] for a in allocations)
    if total_alloc > deployable and total_alloc > 0:
        scale = deployable / total_alloc
        for a in allocations:
            a["usd_amount"] = round(a["usd_amount"] * scale, 2)

    return allocations


# ── AI Rationale Generator ─────────────────────────────────────────────────

def _generate_rationale(allocations: list, regime_ok: bool, cash: float) -> str:
    """
    Ask AI to narrate the quant decision. AI explains — does not pick stocks.
    Returns overall reasoning string.
    """
    if not allocations:
        return "Quantitative filters found no qualifying opportunities today. Holding cash."

    summary = []
    for a in allocations:
        ev = a["ev_stats"]
        summary.append(
            f"{a['ticker']} ({a['name']}, {a['sector']}): "
            f"composite={a['composite_score']:+.3f}, "
            f"p_win={ev.get('p_win', 0):.0%}, EV={ev.get('ev', 0):.1%}, "
            f"Kelly={a['kelly_cap']:.0%}, Markowitz={a['markowitz_weight']:.0%}, "
            f"final_alloc={a['allocation_pct']:.0f}% (${a['usd_amount']:.0f}), "
            f"signals_aligned={a['signals_aligned']}/5"
        )

    prompt = f"""You are a portfolio analyst explaining a quantitative trading decision to an executive.

Today's quant system selected the following positions (all passed EV gate >{EV_MIN:.0%}, signal consensus {SIGNAL_CONSENSUS_MIN}/5, regime filter, Markowitz optimization, and Kelly sizing):

{chr(10).join(summary)}

Available cash: ${cash:.2f}
Regime: {"RISK-ON" if regime_ok else "RISK-OFF (new buys suppressed)"}

Write 3-4 sentences explaining: why these specific stocks were selected today, what the sentiment + price signals indicate, and the key risk. Be concise and factual. No jargon beyond what's already above.

Output JSON only: {{"rationale": "your explanation here"}}"""

    try:
        resp = get_json_model().generate_content(prompt)
        parsed = json.loads(resp.text or "{}")
        return parsed.get("rationale", "")
    except Exception as exc:
        log.warning("AI rationale generation failed: %s", exc)
        return f"Quant system selected {len(allocations)} position(s) based on multi-factor scoring, EV gate, and Markowitz optimization."


# ── execute ────────────────────────────────────────────────────────────────

def run_execute():
    """
    1. Risk management checks on existing holdings (stop-loss, take-profit,
       sentiment stop, max drawdown).
    2. Execute pending BUY trades from yesterday's analyze.
    """
    sb = get_supabase()
    today = date.today()
    portfolio = _get_portfolio(sb)
    cash = float(portfolio["cash_usd"])
    holdings = _get_all_holdings(sb)

    # ── Portfolio value + peak tracking ──
    held_tickers = [h["ticker"] for h in holdings]
    today_tags = _fetch_todays_sentiment_tags(sb, held_tickers) if held_tickers else {}

    total_holdings_value = 0.0
    for h in holdings:
        price = _fetch_open_price(sb, h["target_id"], today) or float(h["avg_buy_price"])
        total_holdings_value += float(h["shares"]) * price
    total_value = round(cash + total_holdings_value, 2)
    _update_peak_value(sb, portfolio, total_value)

    peak = float(portfolio.get("peak_value") or SIM_STARTING_CAPITAL)
    peak = max(peak, total_value)

    # ── Max drawdown guard ──
    drawdown = (total_value - peak) / peak if peak > 0 else 0
    if drawdown <= -MAX_DRAWDOWN_PCT:
        log.warning("execute: MAX DRAWDOWN %.1f%% — liquidating entire portfolio", drawdown * 100)
        cash = _liquidate_all(sb, portfolio, today, f"max_drawdown_{drawdown:.1%}")
        # Clear pending queue too — no new buys after drawdown stop
        sb.table("sim_pending_trades").delete().neq("id", 0).execute()
        log.info("execute: portfolio liquidated. Cash: $%.2f", cash)
        return

    # ── Per-position risk rules ──
    for h in holdings:
        ticker = h["ticker"]
        price = _fetch_open_price(sb, h["target_id"], today)
        if price is None:
            continue

        avg_cost = float(h["avg_buy_price"])
        pct_change = (price - avg_cost) / avg_cost

        trigger = None
        if pct_change <= -STOP_LOSS_PCT:
            trigger = f"stop_loss_{pct_change:.1%}"
        elif pct_change >= TAKE_PROFIT_PCT:
            trigger = f"take_profit_{pct_change:.1%}"
        else:
            tag_info = today_tags.get(ticker, {})
            if tag_info.get("tag") == "threat" or tag_info.get("avg_score", 0) < SENTIMENT_STOP_SCORE:
                trigger = f"sentiment_stop_tag={tag_info.get('tag')}_score={tag_info.get('avg_score', 0):.1f}"

        if trigger:
            shares = float(h["shares"])
            proceeds = round(shares * price, 2)
            pnl = round(proceeds - float(h["total_cost"]), 2)
            cash = round(cash + proceeds, 2)
            sb.table("sim_portfolio").update({
                "cash_usd": cash,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", portfolio["id"]).execute()
            sb.table("sim_holdings").delete().eq("ticker", ticker).execute()
            sb.table("sim_trades").insert({
                "trade_date": today.isoformat(),
                "target_id": h["target_id"],
                "ticker": ticker,
                "action": "SELL",
                "shares": shares,
                "price": round(price, 4),
                "usd_value": proceeds,
                "pnl_usd": pnl,
                "status": "executed",
                "ai_rationale": f"FORCED: {trigger}",
            }).execute()
            log.info("execute: FORCED SELL %s @ $%.2f (%s, P&L: $%.2f)", ticker, price, trigger, pnl)
            portfolio = _get_portfolio(sb)  # refresh after update
            cash = float(portfolio["cash_usd"])

    # ── Execute pending BUY trades ──
    pending = sb.table("sim_pending_trades").select("*").execute().data or []
    if not pending:
        log.info("execute: no pending trades. Cash: $%.2f", cash)
        return

    log.info("execute: processing %d pending BUY(s)", len(pending))
    portfolio = _get_portfolio(sb)
    cash = float(portfolio["cash_usd"])

    for trade in pending:
        ticker = trade["ticker"]
        target_id = trade.get("target_id")
        action = trade["action"]
        rationale = trade.get("ai_rationale", "")

        if action != "BUY":
            continue  # only BUYs are queued by the quant system

        price = _fetch_open_price(sb, target_id, today)
        if price is None:
            log.warning("execute: no price for %s — skipping", ticker)
            sb.table("sim_trades").insert({
                "trade_date": today.isoformat(),
                "target_id": target_id,
                "ticker": ticker,
                "action": "BUY",
                "status": "skipped",
                "skip_reason": f"no_price_{today}",
                "ai_rationale": rationale,
            }).execute()
            continue

        usd_amount = float(trade.get("usd_amount") or 0)
        usd_amount = min(usd_amount, cash)
        if usd_amount < 1.0:
            log.warning("execute: insufficient cash for BUY %s — skipping", ticker)
            continue

        # Check position limit
        current_holdings = _get_all_holdings(sb)
        if len(current_holdings) >= SIM_MAX_POSITIONS:
            log.info("execute: max positions reached, skipping BUY %s", ticker)
            break

        shares = round(usd_amount / price, 6)
        usd_value = round(shares * price, 2)

        existing = _get_holding(sb, ticker)
        if existing:
            new_shares = float(existing["shares"]) + shares
            new_cost = float(existing["total_cost"]) + usd_value
            new_avg = round(new_cost / new_shares, 4)
            sb.table("sim_holdings").update({
                "shares": new_shares,
                "avg_buy_price": new_avg,
                "total_cost": new_cost,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("ticker", ticker).execute()
        else:
            sb.table("sim_holdings").insert({
                "target_id": target_id,
                "ticker": ticker,
                "shares": shares,
                "avg_buy_price": round(price, 4),
                "total_cost": usd_value,
            }).execute()

        cash = round(cash - usd_value, 2)
        sb.table("sim_portfolio").update({
            "cash_usd": cash,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", portfolio["id"]).execute()
        portfolio = _get_portfolio(sb)

        sb.table("sim_trades").insert({
            "trade_date": today.isoformat(),
            "target_id": target_id,
            "ticker": ticker,
            "action": "BUY",
            "shares": shares,
            "price": round(price, 4),
            "usd_value": usd_value,
            "status": "executed",
            "ai_rationale": rationale,
        }).execute()
        log.info("execute: BUY %s — %.4f shares @ $%.2f = $%.2f (cash: $%.2f)",
                 ticker, shares, price, usd_value, cash)

    sb.table("sim_pending_trades").delete().neq("id", 0).execute()
    log.info("execute: done. Cash: $%.2f", cash)


# ── analyze ────────────────────────────────────────────────────────────────

def run_analyze():
    """
    Full quant pipeline:
    Factor Ranking → EV Gate → Signal Consensus → Regime Filter →
    Markowitz Optimization → Kelly Sizing → AI Rationale → Queue Trades
    """
    sb = get_supabase()
    portfolio = _get_portfolio(sb)
    cash = float(portfolio["cash_usd"])
    holdings = _get_all_holdings(sb)

    log.info("analyze: cash=$%.2f, open_positions=%d", cash, len(holdings))

    # ── Fetch sentiment candidates (last 24h, ticker-enabled) ──
    since_str = (datetime.now(timezone.utc) - timedelta(hours=SIM_SENTIMENT_LOOKBACK_HOURS)).isoformat()
    rows = []
    offset = 0
    while True:
        resp = (
            sb.table("sentiment")
            .select("target_id, sentiment_score, implication_tag, pros, cons, targets(id, name, ticker, sector)")
            .gte("created_at", since_str)
            .not_.is_("sentiment_score", "null")
            .range(offset, offset + 999)
            .execute()
        )
        batch = resp.data or []
        rows.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000

    rows = [r for r in rows if r.get("targets") and r["targets"].get("ticker")]

    # Group into candidate dicts
    grouped: dict = defaultdict(lambda: {"scores": [], "tags": [], "pros": [], "cons": []})
    for r in rows:
        tgt = r["targets"]
        tid = r["target_id"]
        g = grouped[tid]
        g["target_id"] = tid
        g["ticker"] = tgt["ticker"]
        g["name"] = tgt["name"]
        g["sector"] = tgt.get("sector") or ""
        if r.get("sentiment_score") is not None:
            g["scores"].append(r["sentiment_score"])
        if r.get("implication_tag"):
            g["tags"].append(r["implication_tag"])
        if r.get("pros"):
            g["pros"].append(r["pros"][:200])
        if r.get("cons"):
            g["cons"].append(r["cons"][:100])

    tag_priority = {"threat": 0, "opportunity": 1, "monitor": 2, "no_action": 3}
    candidates_raw = []
    for g in grouped.values():
        if not g.get("scores"):
            continue
        avg_score = round(sum(g["scores"]) / len(g["scores"]), 1)
        if avg_score < SIM_MIN_SCORE:
            continue
        dominant_tag = min(g["tags"], key=lambda t: tag_priority.get(t, 99)) if g["tags"] else "monitor"
        candidates_raw.append({
            "target_id": g["target_id"],
            "ticker": g["ticker"],
            "name": g["name"],
            "sector": g["sector"],
            "avg_score": avg_score,
            "dominant_tag": dominant_tag,
        })

    log.info("analyze: %d raw candidates after sentiment filter", len(candidates_raw))
    if not candidates_raw:
        log.info("analyze: no candidates — holding cash")
        sb.table("sim_pending_trades").delete().neq("id", 0).execute()
        return

    # ── Fetch data for all candidates ──
    target_ids = [c["target_id"] for c in candidates_raw]
    daily_returns   = _fetch_daily_returns(sb, target_ids)
    reactions       = _fetch_price_reactions_history(sb, target_ids)
    sentiment_hist  = _fetch_sentiment_history(sb, target_ids)

    # ── Layer 1: Factor Scoring + top quintile ──
    scored = _compute_factors(candidates_raw, daily_returns, reactions, sentiment_hist)
    log.info("analyze: %d candidates after factor scoring (top quintile)", len(scored))

    # ── Regime check (uses full universe pre-filtering) ──
    regime_ok = _check_regime(scored if scored else candidates_raw)
    if not regime_ok:
        log.info("analyze: RISK-OFF regime — no new buys queued")
        sb.table("sim_pending_trades").delete().neq("id", 0).execute()
        return

    # ── Layer 2: EV Gate ──
    ev_passed = _apply_ev_gate(scored, reactions)
    log.info("analyze: %d candidates after EV gate", len(ev_passed))

    # ── Layer 3: Signal Consensus ──
    final_candidates = _apply_signal_consensus(ev_passed)
    log.info("analyze: %d candidates after signal consensus", len(final_candidates))

    if not final_candidates:
        log.info("analyze: no candidates cleared all gates — holding cash")
        sb.table("sim_pending_trades").delete().neq("id", 0).execute()
        return

    # Cap to remaining position slots
    current_positions = len(holdings)
    slots = max(0, SIM_MAX_POSITIONS - current_positions)
    final_candidates = final_candidates[:slots]
    if not final_candidates:
        log.info("analyze: no position slots available (held: %d / max: %d)", current_positions, SIM_MAX_POSITIONS)
        return

    # ── Layer 4: Markowitz Optimization ──
    final_tids = [c["target_id"] for c in final_candidates]
    markowitz_weights = _markowitz_optimize(final_candidates, {tid: daily_returns.get(tid, []) for tid in final_tids})

    # ── Layer 5: Kelly Sizing ──
    allocations = _kelly_size(final_candidates, markowitz_weights, cash)
    log.info("analyze: %d allocations from Kelly sizing", len(allocations))

    if not allocations:
        log.info("analyze: Kelly sizing returned no allocations — holding cash")
        sb.table("sim_pending_trades").delete().neq("id", 0).execute()
        return

    # ── AI Rationale ──
    overall_rationale = _generate_rationale(allocations, regime_ok, cash)

    # ── Queue trades ──
    sb.table("sim_pending_trades").delete().neq("id", 0).execute()
    for alloc in allocations:
        per_trade_rationale = (
            f"{overall_rationale[:300]} | "
            f"composite={alloc['composite_score']:+.3f}, "
            f"p_win={alloc['ev_stats'].get('p_win', 0):.0%}, "
            f"EV={alloc['ev_stats'].get('ev', 0):.1%}, "
            f"Kelly={alloc['kelly_cap']:.0%}"
        )
        sb.table("sim_pending_trades").insert({
            "target_id": alloc["target_id"],
            "ticker": alloc["ticker"],
            "action": "BUY",
            "usd_amount": alloc["usd_amount"],
            "sell_all": False,
            "ai_rationale": per_trade_rationale[:500],
        }).execute()
        log.info("analyze: queued BUY %s $%.2f (composite=%+.3f, p_win=%.0f%%, EV=%.1f%%)",
                 alloc["ticker"], alloc["usd_amount"],
                 alloc["composite_score"],
                 alloc["ev_stats"].get("p_win", 0) * 100,
                 alloc["ev_stats"].get("ev", 0) * 100)

    log.info("analyze: done. %s", overall_rationale[:100])


# ── snapshot ───────────────────────────────────────────────────────────────

def run_snapshot():
    """Compute and store a fortnightly performance snapshot (idempotent)."""
    sb = get_supabase()
    today = date.today()

    existing = (
        sb.table("sim_snapshots")
        .select("id")
        .eq("snapshot_date", today.isoformat())
        .limit(1)
        .execute()
    )
    if existing.data:
        log.info("snapshot: already exists for %s — skipping", today)
        return

    portfolio = _get_portfolio(sb)
    cash = float(portfolio["cash_usd"])
    holdings = _get_all_holdings(sb)

    holdings_details = []
    total_holdings_value = 0.0
    for h in holdings:
        price = _fetch_open_price(sb, h["target_id"], today) or float(h["avg_buy_price"])
        market_value = round(float(h["shares"]) * price, 2)
        total_holdings_value += market_value
        pnl = round(market_value - float(h["total_cost"]), 2)
        pnl_pct = round(pnl / float(h["total_cost"]) * 100, 2) if float(h["total_cost"]) else 0
        holdings_details.append({"ticker": h["ticker"], "market_value": market_value, "pnl": pnl, "pnl_pct": pnl_pct})

    total_value = round(cash + total_holdings_value, 2)
    pnl_usd = round(total_value - SIM_STARTING_CAPITAL, 2)
    pnl_pct = round(pnl_usd / SIM_STARTING_CAPITAL * 100, 4)

    sorted_h = sorted(holdings_details, key=lambda x: x["pnl"], reverse=True)
    winners = [f"{h['ticker']} +${h['pnl']:.2f}" for h in sorted_h if h["pnl"] > 0]
    losers  = [f"{h['ticker']} -${abs(h['pnl']):.2f}" for h in sorted_h if h["pnl"] < 0]
    cash_pct = round(cash / total_value * 100, 1) if total_value else 100

    summary_parts = [f"Total: ${total_value:.2f} (P&L: ${pnl_usd:+.2f}, {pnl_pct:+.2f}%)"]
    summary_parts.append(f"Cash: ${cash:.2f} ({cash_pct}%)")
    if winners:
        summary_parts.append("Winners: " + ", ".join(winners[:3]))
    if losers:
        summary_parts.append("Losers: " + ", ".join(losers[:3]))

    sb.table("sim_snapshots").insert({
        "snapshot_date": today.isoformat(),
        "cash_usd": cash,
        "holdings_value": round(total_holdings_value, 2),
        "total_value": total_value,
        "pnl_usd": pnl_usd,
        "pnl_pct": pnl_pct,
        "summary_text": " | ".join(summary_parts),
    }).execute()

    log.info("snapshot: %s — total=$%.2f P&L=$%+.2f (%+.2f%%)", today, total_value, pnl_usd, pnl_pct)


# ── CLI ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Quantitative AI stock simulation trader")
    parser.add_argument("--action", choices=["execute", "analyze", "snapshot"], required=True)
    args = parser.parse_args()

    if args.action == "execute":
        run_execute()
    elif args.action == "analyze":
        run_analyze()
    elif args.action == "snapshot":
        run_snapshot()
