"""
Weekly Brief: pulls 7-day sentiment from Supabase, generates a strategic executive brief via AI, saves to file.

Run manually:
  PYTHONPATH=src python src/weekly_brief.py

Or triggered weekly by GitHub Actions (every Monday).
"""
import logging
import os
import re
import sys
from datetime import datetime, timedelta

_src_dir = os.path.dirname(os.path.abspath(__file__))
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from config import get_supabase, get_model, MAX_PAYLOAD_CHARS_PER_FIELD

logger = logging.getLogger(__name__)

LOOKBACK_DAYS = 7

_default_reports_dir = os.path.normpath(os.path.join(_src_dir, "..", "reports"))
REPORTS_DIR = os.environ.get("REPORTS_DIR") or _default_reports_dir
if not os.path.isabs(REPORTS_DIR):
    REPORTS_DIR = os.path.abspath(REPORTS_DIR)


def _truncate(s: str, max_chars: int) -> str:
    if not s or len(s) <= max_chars:
        return s or ""
    return s[:max_chars].rstrip() + "..."


def _dedupe_sentences(text: str) -> str:
    if not text or not text.strip():
        return text
    parts = re.split(r"(?<=[.!?])\s+", text)
    seen: set = set()
    kept = []
    for p in parts:
        normalized = " ".join(p.split()).strip()
        if not normalized:
            continue
        key = normalized.lower()[:200] if len(normalized) >= 10 else normalized.lower()
        if key not in seen:
            seen.add(key)
            kept.append(p.strip())
    return " ".join(kept) if kept else text


def get_weekly_data() -> list:
    """
    Pull all sentiment from the last 7 days, grouped by (target, event).
    Returns a list of dicts with name, type, description, pros, cons, quotes, sentiment_score.
    """
    supabase = get_supabase()
    targets_resp = supabase.table("targets").select("*").eq("status", "tracking").execute()
    targets = getattr(targets_resp, "data", None) or []
    if not targets:
        return []

    since_dt = datetime.utcnow() - timedelta(days=LOOKBACK_DAYS)
    since_str = since_dt.isoformat()
    full_data = []

    for t in targets:
        t_id = t.get("id")
        t_name = t.get("name") or "Unknown"
        t_type = t.get("target_type") or "target"
        if t_id is None:
            continue

        events_resp = supabase.table("events").select("*").eq("target_id", t_id).execute()
        events_list = getattr(events_resp, "data", None) or []
        if not events_list:
            events_list = [{"id": None, "headline": t.get("description") or ""}]

        for event in events_list:
            event_id = event.get("id")
            headline = (event.get("headline") or "").strip() or "(general)"

            sentiment_q = (
                supabase.table("sentiment")
                .select("id, target_id, event_id, pros, cons, verbatim_quotes, source_url, sentiment_score, created_at")
                .eq("target_id", t_id)
                .gte("created_at", since_str)
            )
            if event_id is not None:
                sentiment_q = sentiment_q.eq("event_id", event_id)
            else:
                sentiment_q = sentiment_q.is_("event_id", None)
            sentiments = getattr(sentiment_q.execute(), "data", None) or []
            if not sentiments:
                continue

            raw_pros = " ".join(
                s.get("pros") or "" for s in sentiments
                if s.get("pros") and s.get("pros") != "None found"
            )
            raw_cons = " ".join(
                s.get("cons") or "" for s in sentiments
                if s.get("cons") and s.get("cons") != "None found"
            )
            scores = [s.get("sentiment_score") for s in sentiments if s.get("sentiment_score") is not None]
            avg_score = round(sum(scores) / len(scores)) if scores else None

            full_data.append({
                "name": t_name,
                "type": t_type,
                "headline": headline,
                "pros": _dedupe_sentences(raw_pros),
                "cons": _dedupe_sentences(raw_cons),
                "sentiment_score": avg_score,
                "row_count": len(sentiments),
            })

    return full_data


def _build_leaderboard_summary(data: list) -> str:
    """Build a short text leaderboard of targets by avg score for the prompt."""
    scored = [(d["name"], d["sentiment_score"]) for d in data if d.get("sentiment_score") is not None]
    # Aggregate by target name (multiple events per target)
    by_name: dict = {}
    for name, score in scored:
        by_name.setdefault(name, []).append(score)
    ranked = sorted(
        [(name, round(sum(scores) / len(scores))) for name, scores in by_name.items()],
        key=lambda x: x[1],
        reverse=True,
    )
    lines = [f"  {i+1}. {name}: {score:+d}/10" for i, (name, score) in enumerate(ranked)]
    return "\n".join(lines) if lines else "  (No scored data this week)"


def generate_weekly_brief(data: list) -> tuple:
    """Generate the strategic weekly brief via Gemini. Returns (content, is_mock)."""
    if not data:
        return ("# Weekly Executive Brief\n\n*No data for this week.*\n", True)

    week_str = datetime.utcnow().strftime("Week %W, %Y")
    date_range_start = (datetime.utcnow() - timedelta(days=LOOKBACK_DAYS)).strftime("%b %d")
    date_range_end = datetime.utcnow().strftime("%b %d, %Y")
    leaderboard = _build_leaderboard_summary(data)

    # Build payload (briefer than daily report — focus on patterns not per-event detail)
    payload_lines = []
    for item in data:
        score = item.get("sentiment_score")
        score_str = f"Score: {score:+d}/10 | " if score is not None else ""
        pros = _truncate(item.get("pros") or "", MAX_PAYLOAD_CHARS_PER_FIELD // 2)
        cons = _truncate(item.get("cons") or "", MAX_PAYLOAD_CHARS_PER_FIELD // 2)
        payload_lines.append(
            f"[{item['type']}] {item['name']} | {item['headline']}\n"
            f"{score_str}Readings: {item['row_count']}\n"
            f"PROS: {pros}\nCONS: {cons}\n---"
        )
    batch_text = "\n".join(payload_lines)

    prompt = f"""
You are a Chief Market Intelligence Officer preparing a WEEKLY EXECUTIVE BRIEF for a strategy leadership team.
Period: {date_range_start} – {date_range_end} ({week_str}).

This brief is STRATEGIC, not tactical. Do not repeat daily event details. Focus on:
- Patterns that emerged across the full week
- Which companies/products won or lost market perception
- Actionable implications for strategy

Sentiment leaderboard (avg score this week, -10 to +10):
{leaderboard}

Structure the brief EXACTLY as follows:

# 📋 Weekly Executive Brief — {date_range_start}–{date_range_end}

## 🏁 Week in Review
(2-3 sentences: the single most important market narrative this week. Be specific, not generic.)

## 🟢 Top 3 Opportunities
(Three bullet points. Each = one company/product + the specific opportunity signal + why it matters strategically.)

## 🔴 Top 3 Risks
(Three bullet points. Each = one company/product + the specific risk signal + what could go wrong.)

## ⚡ Competitive Shifts
(2-3 bullet points on notable momentum changes: who gained ground, who lost it, any emerging pattern across multiple targets.)

## ✅ Recommended Actions
(Three concrete, actionable bullets a strategy team could act on this week. Be specific — not "monitor X" but "evaluate partnership with X given Y signal".)

## 📊 Full Score Breakdown
(Reproduce the leaderboard above as a formatted table with score and a one-sentence interpretation per company.)

Raw intelligence (7-day window):
{batch_text}
"""

    try:
        model = get_model()
        response = model.generate_content(prompt)
        return (response.text or "", False)
    except Exception as e:
        logger.warning("AI limit hit, generating mock weekly brief: %s", e)
        mock = (
            f"# 📋 Weekly Executive Brief — {date_range_start}–{date_range_end} (MOCK)\n\n"
            "*AI quota reached. Displaying raw data summary.*\n\n"
            f"## Score Breakdown\n{leaderboard}\n\n"
            "## Raw Data\n"
        )
        for item in data:
            mock += f"- **{item['name']}** | {item['headline'][:60]} | Score: {item.get('sentiment_score')}\n"
        return (mock, True)


def save_weekly_brief(content: str) -> str:
    """Save brief to reports/weekly_brief_YYYY-WXX.md. Returns file path."""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    week_label = datetime.utcnow().strftime("%Y-W%W")
    file_path = os.path.join(REPORTS_DIR, f"weekly_brief_{week_label}.md")
    with open(file_path, "w") as f:
        f.write(content)
    logger.info("📋 WEEKLY BRIEF SAVED: %s", file_path)
    return file_path


def run_weekly_brief() -> None:
    logger.info("Starting weekly brief generator (last %d days)...", LOOKBACK_DAYS)
    data = get_weekly_data()
    if not data:
        logger.info("No data found for the past %d days.", LOOKBACK_DAYS)
        return
    logger.info("Generating weekly brief across %d target/event pairs...", len(data))
    content, is_mock = generate_weekly_brief(data)
    path = save_weekly_brief(content)
    if is_mock:
        logger.info("(Mock brief — AI quota reached.)")
    logger.info("✅ Weekly brief complete: %s", path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    run_weekly_brief()
