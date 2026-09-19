"""
Replay the simulator's strategy over historical data.

The live simulator has run since 2026-04-13 and returned +9.9%, against SPY
+11.6% and QQQ +17.0% over the same window, with 80% of its profit coming from a
single DELL trade. That is not enough evidence to say whether the six-factor
funnel has an edge, because a strategy that trades 22 times cannot be told apart
from luck. This replays it day by day so parameters can be varied and compared
against simply holding an index.

Fidelity
    The strategy functions are imported from sim_trader rather than reimplemented,
    so the scoring, gates and sizing are the same code that trades live. Only the
    data access is replaced, because the live versions read "now" from the database
    and a replay must read "as of the simulated day".

No look-ahead
    Every input is filtered to strictly before the decision date: sentiment by
    created_at, price bars by ts, and past price reactions by computed_at. That
    last one matters most. price_reactions describes how a stock moved after an
    event, so a replay that reads the whole table is grading the strategy on
    answers it could not have had, and the EV gate would look far better than it is.

Usage
    PYTHONPATH=src python scripts/backtest.py
    PYTHONPATH=src python scripts/backtest.py --start 2026-04-13 --end 2026-06-12
    PYTHONPATH=src python scripts/backtest.py --set EV_MIN=0.03 --set SIM_MIN_SCORE=5
    PYTHONPATH=src python scripts/backtest.py --sweep EV_MIN=0.0,0.015,0.03,0.05
"""
import argparse
import logging
import math
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_src = os.path.join(_root, "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

import sim_trader as st  # noqa: E402
from config import (  # noqa: E402
    SIM_BENCHMARKS, SIM_MIN_SCORE, SIM_STARTING_CAPITAL,
    SIM_SENTIMENT_LOOKBACK_HOURS, fetch_all_rows, get_supabase,
)

log = logging.getLogger("backtest")

TAG_PRIORITY = {"threat": 1, "opportunity": 2, "monitor": 3, "no_action": 4}


# ── Data loaded once, sliced per simulated day ──────────────────────────────

class History:
    """Every input the strategy needs, held in memory and sliceable by date."""

    def __init__(self, sb):
        log.info("loading history...")
        self.targets = {
            t["id"]: t for t in fetch_all_rows(
                lambda: sb.table("targets").select("id, name, ticker, sector, target_type, status").order("id")
            )
        }

        self.sentiment = sorted(
            fetch_all_rows(
                lambda: sb.table("sentiment")
                .select("target_id, sentiment_score, implication_tag, created_at")
                .not_.is_("sentiment_score", "null").order("id")
            ),
            key=lambda r: r["created_at"],
        )

        self.reactions = sorted(
            fetch_all_rows(
                lambda: sb.table("price_reactions")
                .select("target_id, reaction_7d, confidence, computed_at")
                .not_.is_("reaction_7d", "null").order("event_id")
            ),
            key=lambda r: r["computed_at"] or "",
        )

        # Daily closes per target. 5-minute bars collapse to the last close of each
        # day, matching what _fetch_daily_returns does live.
        bars = fetch_all_rows(lambda: sb.table("stock_prices").select("target_id, ts, close, open").order("id"))
        closes: Dict[int, Dict[str, float]] = defaultdict(dict)
        opens: Dict[int, Dict[str, float]] = defaultdict(dict)
        for b in bars:
            day = b["ts"][:10]
            closes[b["target_id"]][day] = float(b["close"])
            if day not in opens[b["target_id"]]:
                opens[b["target_id"]][day] = float(b["open"] or b["close"])
        self.closes = {tid: dict(sorted(d.items())) for tid, d in closes.items()}
        self.opens = {tid: d for tid, d in opens.items()}

        self.trading_days = sorted({d for d in
                                    (day for days in self.closes.values() for day in days)})

        try:
            self.macro_exposure_rows = fetch_all_rows(
                lambda: sb.table("macro_sector_exposure").select("macro_target_id, sector, exposure_weight").order("id")
            )
        except Exception:
            self.macro_exposure_rows = []

        log.info(
            "  %d targets, %d sentiment rows, %d reactions, %d tickers with bars, %d trading days",
            len(self.targets), len(self.sentiment), len(self.reactions),
            len(self.closes), len(self.trading_days),
        )

    # ── as-of slices ────────────────────────────────────────────────────────

    def candidates(self, as_of: date, min_score: float) -> List[dict]:
        """Sentiment-derived buy candidates known before `as_of`, as run_analyze builds them."""
        hi = f"{as_of.isoformat()}T00:00:00+00:00"
        lo = (datetime.combine(as_of, datetime.min.time(), timezone.utc)
              - timedelta(hours=SIM_SENTIMENT_LOOKBACK_HOURS)).isoformat()
        grouped: Dict[int, dict] = {}
        for r in self.sentiment:
            if r["created_at"] >= hi:
                break          # sorted, so nothing later can qualify
            if r["created_at"] < lo:
                continue
            t = self.targets.get(r["target_id"])
            if not t or not (t.get("ticker") or "").strip() or t.get("target_type") == "MACRO":
                continue
            g = grouped.setdefault(r["target_id"], {"scores": [], "tags": [], "target": t})
            g["scores"].append(r["sentiment_score"])
            if r.get("implication_tag"):
                g["tags"].append(r["implication_tag"])

        out = []
        for tid, g in grouped.items():
            avg = round(sum(g["scores"]) / len(g["scores"]), 1)
            if avg < min_score:
                continue
            t = g["target"]
            out.append({
                "target_id": tid, "ticker": t["ticker"], "name": t.get("name") or "",
                "sector": t.get("sector"), "avg_score": avg,
                "dominant_tag": (min(g["tags"], key=lambda x: TAG_PRIORITY.get(x, 99))
                                 if g["tags"] else "monitor"),
            })
        return out

    def daily_returns(self, as_of: date, target_ids: List[int]) -> Dict[int, List[float]]:
        """Log returns from closes strictly before `as_of`."""
        cutoff = as_of.isoformat()
        window = st.PRICE_MOMENTUM_DAYS + 10
        out: Dict[int, List[float]] = {}
        for tid in target_ids:
            series = [(d, c) for d, c in self.closes.get(tid, {}).items() if d < cutoff][-window:]
            rets = [math.log(series[i][1] / series[i - 1][1])
                    for i in range(1, len(series))
                    if series[i - 1][1] > 0 and series[i][1] > 0]
            if rets:
                out[tid] = rets
        return out

    def reactions_as_of(self, as_of: date, target_ids: List[int]) -> Dict[int, List[float]]:
        """Past reactions known before `as_of`, weighted by confidence as the live gate does."""
        cutoff = f"{as_of.isoformat()}T00:00:00+00:00"
        wanted = set(target_ids)
        out: Dict[int, List[float]] = defaultdict(list)
        for r in self.reactions:
            if (r["computed_at"] or "") >= cutoff:
                break
            if r["target_id"] not in wanted:
                continue
            weight = {"high": 2, "medium": 1, "low": 0.5}.get(r.get("confidence") or "low", 1)
            out[r["target_id"]].extend([float(r["reaction_7d"]) / 100.0] * int(weight))
        return dict(out)

    def sentiment_history(self, as_of: date, target_ids: List[int]) -> Dict[int, list]:
        """14 days of scored sentiment before `as_of`, shaped as the live fetcher returns it."""
        hi = f"{as_of.isoformat()}T00:00:00+00:00"
        lo = (datetime.combine(as_of, datetime.min.time(), timezone.utc) - timedelta(days=14)).isoformat()
        wanted = set(target_ids)
        out: Dict[int, list] = defaultdict(list)
        for r in self.sentiment:
            if r["created_at"] >= hi:
                break
            if r["created_at"] < lo or r["target_id"] not in wanted:
                continue
            out[r["target_id"]].append((r["created_at"], r["sentiment_score"], r.get("implication_tag")))
        return dict(out)

    def macro_exposure(self, as_of: date, candidates: List[dict]) -> Dict[int, float]:
        """Sector-weighted macro backdrop per candidate, from macro sentiment before `as_of`."""
        if not candidates or not self.macro_exposure_rows:
            return {c["target_id"]: 0.0 for c in candidates}
        hi = f"{as_of.isoformat()}T00:00:00+00:00"
        lo = (datetime.combine(as_of, datetime.min.time(), timezone.utc) - timedelta(days=7)).isoformat()

        macro_scores: Dict[int, List[float]] = defaultdict(list)
        macro_ids = {t["id"] for t in self.targets.values() if t.get("target_type") == "MACRO"}
        for r in self.sentiment:
            if r["created_at"] >= hi:
                break
            if r["created_at"] >= lo and r["target_id"] in macro_ids:
                macro_scores[r["target_id"]].append(r["sentiment_score"])

        by_sector: Dict[str, List[tuple]] = defaultdict(list)
        for row in self.macro_exposure_rows:
            scores = macro_scores.get(row["macro_target_id"])
            if scores:
                by_sector[row["sector"]].append((float(row["exposure_weight"]),
                                                 sum(scores) / len(scores)))

        out = {}
        for c in candidates:
            pairs = by_sector.get(c.get("sector") or "", [])
            total_w = sum(w for w, _ in pairs)
            out[c["target_id"]] = (sum(w * s for w, s in pairs) / total_w) if total_w else 0.0
        return out

    # ── prices ──────────────────────────────────────────────────────────────

    def open_price(self, tid: int, day: str) -> Optional[float]:
        return self.opens.get(tid, {}).get(day)

    def close_price(self, tid: int, day: str) -> Optional[float]:
        """Close on `day`, else the most recent close before it."""
        series = self.closes.get(tid) or {}
        if day in series:
            return series[day]
        prior = [d for d in series if d <= day]
        return series[prior[-1]] if prior else None

    def peak_close_since(self, tid: int, since: str, until: str) -> Optional[float]:
        series = self.closes.get(tid) or {}
        vals = [c for d, c in series.items() if since <= d <= until]
        return max(vals) if vals else None


# ── The replay ──────────────────────────────────────────────────────────────

class Portfolio:
    def __init__(self, cash: float):
        self.cash = cash
        self.positions: Dict[int, dict] = {}   # target_id -> {ticker, shares, cost, avg, first_day}
        self.peak = cash
        self.trades: List[dict] = []

    def value(self, hist: History, day: str) -> float:
        held = 0.0
        for tid, p in self.positions.items():
            price = hist.close_price(tid, day) or p["avg"]
            held += p["shares"] * price
        return self.cash + held

    def buy(self, tid: int, ticker: str, price: float, usd: float, day: str) -> None:
        if price <= 0 or usd <= 0 or usd > self.cash:
            return
        shares = usd / price
        p = self.positions.get(tid)
        if p:
            p["shares"] += shares
            p["cost"] += usd
            p["avg"] = p["cost"] / p["shares"]
        else:
            self.positions[tid] = {"ticker": ticker, "shares": shares, "cost": usd,
                                   "avg": price, "first_day": day}
        self.cash -= usd
        self.trades.append({"day": day, "action": "BUY", "ticker": ticker, "usd": usd})

    def sell(self, tid: int, price: float, day: str, reason: str) -> None:
        p = self.positions.pop(tid, None)
        if not p or price <= 0:
            return
        proceeds = p["shares"] * price
        self.cash += proceeds
        self.trades.append({"day": day, "action": "SELL", "ticker": p["ticker"],
                            "usd": proceeds, "pnl": proceeds - p["cost"], "reason": reason})


def run_backtest(hist: History, start: date, end: date, verbose: bool = False) -> dict:
    """Replay the strategy across [start, end]. Returns a result summary."""
    days = [d for d in hist.trading_days if start.isoformat() <= d <= end.isoformat()]
    if len(days) < 2:
        raise SystemExit(f"not enough trading days between {start} and {end} (found {len(days)})")

    pf = Portfolio(SIM_STARTING_CAPITAL)
    pending: List[dict] = []
    equity: List[tuple] = []
    gate_stops: Dict[str, int] = defaultdict(int)

    for day in days:
        as_of = date.fromisoformat(day)

        # ── execute what yesterday queued, at today's open ──
        for order in pending:
            tid = order["target_id"]
            price = hist.open_price(tid, day)
            if price is None:
                continue                      # no bar for this name today; order lapses
            if order["action"] == "SELL":
                pf.sell(tid, price, day, "rotation")
            else:
                pf.buy(tid, order["ticker"], price, min(order["usd"], pf.cash), day)
        pending = []

        # ── risk rules on open positions ──
        total = pf.value(hist, day)
        pf.peak = max(pf.peak, total)
        if pf.peak > 0 and (total - pf.peak) / pf.peak <= -st.MAX_DRAWDOWN_PCT:
            for tid in list(pf.positions):
                price = hist.close_price(tid, day)
                if price:
                    pf.sell(tid, price, day, "max_drawdown")
            equity.append((day, pf.value(hist, day)))
            continue

        for tid in list(pf.positions):
            p = pf.positions[tid]
            price = hist.close_price(tid, day)
            if not price:
                continue
            change = (price - p["avg"]) / p["avg"]
            peak = hist.peak_close_since(tid, p["first_day"], day) or price
            trail = (price - peak) / peak if peak else 0.0
            reason = None
            if change <= -st.STOP_LOSS_PCT:
                reason = "stop_loss"
            elif change >= st.TAKE_PROFIT_PCT:
                reason = "take_profit"
            elif change > st.TRAILING_STOP_MIN_GAIN and trail <= -st.TRAILING_STOP_PCT:
                reason = "trailing_stop"
            if reason:
                pf.sell(tid, price, day, reason)

        # ── analyze: queue for the next session, using only what was known ──
        raw = hist.candidates(as_of, SIM_MIN_SCORE)
        held_ids = set(pf.positions)
        for tid in held_ids:
            if not any(c["target_id"] == tid for c in raw):
                t = hist.targets.get(tid) or {}
                raw.append({"target_id": tid, "ticker": t.get("ticker") or "",
                            "name": t.get("name") or "", "sector": t.get("sector"),
                            "avg_score": 0.0, "dominant_tag": "monitor"})
        if not raw:
            gate_stops["no_candidates"] += 1
            equity.append((day, pf.value(hist, day)))
            continue

        ids = [c["target_id"] for c in raw]
        returns = hist.daily_returns(as_of, ids)
        reactions = hist.reactions_as_of(as_of, ids)
        sent_hist = hist.sentiment_history(as_of, ids)
        macro = hist.macro_exposure(as_of, raw)

        as_of_dt = datetime.combine(as_of, datetime.min.time(), timezone.utc)
        scored_all = st._score_candidates(raw, returns, reactions, sent_hist, macro, as_of=as_of_dt)
        new_scored = [c for c in scored_all if c["target_id"] not in held_ids]
        top_new = st._top_cohort(new_scored)
        regime_ok = st._check_regime(scored_all)
        ev_passed = st._apply_ev_gate(top_new, reactions)
        final = st._apply_signal_consensus(ev_passed)

        slots = max(0, st.SIM_MAX_POSITIONS - len(pf.positions))
        final = final[:slots]
        deploy_multiplier = 1.0
        if not regime_ok:
            final = final[:1]
            deploy_multiplier = (st.RISK_OFF_DEPLOY_FRAC / st.MAX_DEPLOY_FRACTION
                                 if st.MAX_DEPLOY_FRACTION else 1.0)

        if not final:
            stage = ("no_slots" if slots == 0 else
                     "consensus" if ev_passed else
                     "ev_gate" if top_new else
                     "top_cohort")
            gate_stops[stage] += 1
            equity.append((day, pf.value(hist, day)))
            continue

        weights = st._markowitz_optimize(final, {c["target_id"]: returns.get(c["target_id"], []) for c in final})
        allocations = st._kelly_size(final, weights, pf.cash, deploy_multiplier)
        for a in allocations:
            pending.append({"target_id": a["target_id"], "ticker": a["ticker"],
                            "action": "BUY", "usd": float(a["usd_amount"])})
        if not allocations:
            gate_stops["kelly"] += 1

        equity.append((day, pf.value(hist, day)))
        if verbose and allocations:
            log.info("  %s queued %s", day, ", ".join(a["ticker"] for a in allocations))

    final_value = equity[-1][1] if equity else SIM_STARTING_CAPITAL
    sells = [t for t in pf.trades if t["action"] == "SELL" and "pnl" in t]
    wins = [t for t in sells if t["pnl"] > 0]

    return {
        "days": len(days),
        "start": days[0], "end": days[-1],
        "final_value": final_value,
        "return_pct": (final_value - SIM_STARTING_CAPITAL) / SIM_STARTING_CAPITAL * 100,
        "trades": len(pf.trades),
        "closed": len(sells),
        "win_rate": (len(wins) / len(sells) * 100) if sells else 0.0,
        "best": max((t["pnl"] for t in sells), default=0.0),
        "worst": min((t["pnl"] for t in sells), default=0.0),
        "gate_stops": dict(gate_stops),
        "equity": equity,
        "trade_log": pf.trades,
    }


def benchmark_return(symbol: str, start: date, end: date) -> Optional[float]:
    """Percent return of a buy-and-hold over the same window."""
    try:
        import yfinance as yf
        h = yf.Ticker(symbol).history(start=(start - timedelta(days=5)).isoformat(),
                                      end=(end + timedelta(days=1)).isoformat())
        if h is None or h.empty:
            return None
        closes = h["Close"].dropna()
        on_or_after = closes[[d.date() >= start for d in closes.index]]
        base = on_or_after if not on_or_after.empty else closes
        return (float(closes.iloc[-1]) - float(base.iloc[0])) / float(base.iloc[0]) * 100
    except Exception as exc:
        log.warning("benchmark %s failed: %s", symbol, exc)
        return None


def apply_overrides(pairs: List[str]) -> None:
    """Override strategy constants on the sim_trader module, e.g. EV_MIN=0.03."""
    for pair in pairs:
        name, _, raw = pair.partition("=")
        name = name.strip()
        target = st if hasattr(st, name) else None
        if target is None:
            raise SystemExit(f"unknown parameter: {name}")
        current = getattr(target, name)
        value = type(current)(raw) if not isinstance(current, bool) else raw.lower() == "true"
        setattr(target, name, value)
        log.info("override: %s = %s (was %s)", name, value, current)


def report(result: dict, start: date, end: date) -> None:
    log.info("\n%s", "=" * 62)
    log.info("%s to %s   (%d trading days)", result["start"], result["end"], result["days"])
    log.info("  strategy      %8.2f   %+6.2f%%", result["final_value"], result["return_pct"])
    for sym in SIM_BENCHMARKS:
        r = benchmark_return(sym, start, end)
        if r is not None:
            delta = result["return_pct"] - r
            verdict = "ahead" if delta >= 0 else "behind"
            log.info("  %-12s %8.2f   %+6.2f%%   strategy %s by %.2f points",
                     sym, SIM_STARTING_CAPITAL * (1 + r / 100), r, verdict, abs(delta))
    log.info("  trades %d (%d closed), win rate %.0f%%, best %+.2f worst %+.2f",
             result["trades"], result["closed"], result["win_rate"], result["best"], result["worst"])
    if result["gate_stops"]:
        stops = ", ".join(f"{k} {v}" for k, v in sorted(result["gate_stops"].items(),
                                                        key=lambda kv: -kv[1]))
        log.info("  days queuing nothing, by gate: %s", stops)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default="2026-03-20")
    ap.add_argument("--end", default="2026-06-12")
    ap.add_argument("--set", action="append", default=[], metavar="NAME=VALUE",
                    help="override a strategy constant, e.g. --set EV_MIN=0.03")
    ap.add_argument("--sweep", metavar="NAME=V1,V2,...",
                    help="run once per value of one constant and compare")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    hist = History(get_supabase())

    if args.sweep:
        name, _, values = args.sweep.partition("=")
        originals = getattr(st, name.strip())
        rows = []
        for raw in values.split(","):
            apply_overrides([f"{name}={raw}"])
            res = run_backtest(hist, start, end)
            rows.append((raw, res))
            log.info("  %s=%-8s -> %+6.2f%%  (%d trades)", name, raw, res["return_pct"], res["trades"])
        setattr(st, name.strip(), originals)
        log.info("\n%s", "=" * 62)
        best = max(rows, key=lambda r: r[1]["return_pct"])
        log.info("best %s=%s at %+.2f%%", name, best[0], best[1]["return_pct"])
        for sym in SIM_BENCHMARKS:
            r = benchmark_return(sym, start, end)
            if r is not None:
                log.info("  %s over the same window: %+.2f%%", sym, r)
        return 0

    apply_overrides(args.set)
    result = run_backtest(hist, start, end, verbose=args.verbose)
    report(result, start, end)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
