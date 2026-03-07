"""
Report: pulls last 24h sentiment from Supabase, generates one master Market Intelligence report via AI, saves to file.
"""
import logging
import os
import re
import sys
from datetime import datetime, timedelta

# Allow importing config when running as python src/report.py from repo root
_src_dir = os.path.dirname(os.path.abspath(__file__))
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from config import get_supabase, get_model, LOOKBACK_DAYS, MAX_PAYLOAD_CHARS_PER_FIELD

logger = logging.getLogger(__name__)

script_dir = os.path.dirname(os.path.abspath(__file__))
_default_reports_dir = os.path.normpath(os.path.join(script_dir, "..", "reports"))
REPORTS_DIR = os.environ.get("REPORTS_DIR") or _default_reports_dir
if not os.path.isabs(REPORTS_DIR):
    REPORTS_DIR = os.path.abspath(REPORTS_DIR)


def _truncate(s: str, max_chars: int) -> str:
    """Truncate string to avoid token limits; append ... if shortened."""
    if not s or len(s) <= max_chars:
        return s or ""
    return s[: max_chars].rstrip() + "..."


def _dedupe_sentences(text: str) -> str:
    """
    Reduce repetition by keeping unique sentences (order preserved).
    Same or near-identical pros/cons from multiple sentiment rows otherwise
    get concatenated and produce repetitive strategic analysis.
    """
    if not text or not text.strip():
        return text
    parts = re.split(r"(?<=[.!?])\s+", text)
    seen = set()
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


def get_cloud_data():
    """
    Pulls targets, their events, and sentiment from the last LOOKBACK_DAYS.
    Returns one report item per (target, event) that has sentiment, so we can show which event caused what.
    """
    supabase = get_supabase()
    targets_response = supabase.table("targets").select("*").eq("status", "tracking").execute()
    targets = getattr(targets_response, "data", None) or []

    if not targets:
        return []

    yesterday_dt = datetime.utcnow() - timedelta(days=LOOKBACK_DAYS)
    yesterday_str = yesterday_dt.isoformat()
    full_data = []

    for t in targets:
        t_id = t.get("id")
        t_name = t.get("name") or "Unknown"
        t_type = t.get("target_type") or "target"
        if t_id is None:
            continue

        # Get events for this target; if none (legacy), use one virtual event from target.description
        events_resp = supabase.table("events").select("*").eq("target_id", t_id).execute()
        events_list = getattr(events_resp, "data", None) or []
        if not events_list:
            events_list = [{"id": None, "headline": t.get("description") or ""}]

        for event in events_list:
            event_id = event.get("id")
            headline = (event.get("headline") or "").strip() or "(general)"

            sentiment_q = (
                supabase.table("sentiment")
                .select("*")
                .eq("target_id", t_id)
                .gte("created_at", yesterday_str)
            )
            if event_id is not None:
                sentiment_q = sentiment_q.eq("event_id", event_id)
            else:
                sentiment_q = sentiment_q.is_("event_id", None)
            sentiment_response = sentiment_q.execute()
            sentiments = getattr(sentiment_response, "data", None) or []
            if not sentiments:
                continue

            raw_pros = " ".join(
                s.get("pros") or ""
                for s in sentiments
                if s.get("pros") and (s.get("pros") != "None found")
            )
            raw_cons = " ".join(
                s.get("cons") or ""
                for s in sentiments
                if s.get("cons") and (s.get("cons") != "None found")
            )
            quotes_with_links = []
            for s in sentiments:
                quote = s.get("verbatim_quotes") or ""
                if not quote:
                    continue
                link = s.get("source_url") or "#"
                quotes_with_links.append(f'"{quote}" - [View Source]({link})')
            raw_quotes = " ".join(quotes_with_links)

            all_pros = _dedupe_sentences(raw_pros)
            all_cons = _dedupe_sentences(raw_cons)
            all_quotes = raw_quotes

            if all_pros or all_cons or all_quotes:
                full_data.append({
                    "name": t_name,
                    "type": t_type,
                    "description": headline,
                    "pros": all_pros,
                    "cons": all_cons,
                    "quotes": all_quotes,
                })

    return full_data


def generate_batch_report(data):
    """Asks AI to write one master intelligence report for all targets. Returns (content, is_mock)."""
    max_chars = MAX_PAYLOAD_CHARS_PER_FIELD
    report_date = datetime.utcnow().strftime("%Y-%m-%d")
    payload_lines = []
    for item in data:
        pros = _truncate(item.get("pros", ""), max_chars)
        cons = _truncate(item.get("cons", ""), max_chars)
        quotes = _truncate(item.get("quotes", ""), max_chars)
        # Each item is one (target, event); description is the event headline
        payload_lines.append(
            f"[{item.get('type', '')}] {item.get('name', '')} | Event: {item.get('description', '')}\n"
            f"PROS: {pros}\n"
            f"CONS: {cons}\n"
            f"VOICE OF CUSTOMER: {quotes}\n"
            f"---"
        )
    batch_text = "\n".join(payload_lines)

    prompt = f"""
    You are a Principal Market Intelligence Analyst. Write a highly professional "Market Intelligence Report"
    based on the following raw sentiment data. Report date: {report_date}.

    CRITICAL INSTRUCTIONS TO AVOID REPETITION:
    - Focus on what is NEW or CHANGED in sentiment; avoid repeating the same strategic points from prior reports.
    - If multiple targets refer to the same company or product (e.g. "MacBook Neo" and "MacBook Neo and iPhone 17e"), give ONE consolidated strategic analysis and note the overlap; do not repeat the same narrative for each.
    - Vary headlines and phrasing. Do not use the same sentence structures or conclusions across targets.
    - In the Executive Summary, highlight the most newsworthy or differentiated developments only; avoid generic summaries that could apply every day.

    Structure the report precisely with these sections:
    # 🌐 Daily Market Intelligence Report (as of {report_date})

    ## 📊 Executive Summary
    (A brief 2-paragraph macro view emphasizing today's notable developments and what has changed; avoid generic filler.)

    ## 🎯 Target Deep Dives
    (For EVERY item provided, create a sub-section. Each item is a target + event (the headline we tracked). Use the section heading: ### [Target Name] - Event: [event headline]. So readers see which event caused which sentiment.)
    ### [Target Name] - Event: [event headline]
    * **Strategic Analysis:** (Your expert synthesis for this specific event.)
    * **Voice of the Customer:** (Present the provided verbatim user quotes as bulleted blockquotes. YOU MUST KEEP THE [View Source](URL) MARKDOWN LINK INTACT AT THE END OF THE QUOTE.)

    ## 🔭 Forward Outlook
    (2-3 bullet points predicting where this sentiment might lead).

    Raw Intelligence:
    {batch_text}
    """

    try:
        model = get_model()
        response = model.generate_content(prompt)
        return (response.text or "", False)
    except Exception as e:
        logger.warning("   ⚠️ AI Limit Hit. Generating Mock Intelligence Report instead: %s", e)
        mock = "# 🌐 Daily Market Intelligence Report (MOCK)\n\n*Data pending AI quota reset.*\n\n## Raw Intelligence Summary\n\n"
        for item in data:
            pros = (item.get("pros") or "")[:75]
            cons = (item.get("cons") or "")[:75]
            quotes = item.get("quotes") or ""
            mock += f"### {item.get('name', '')} ({item.get('type', '')})\n* **Pros:** {pros}...\n* **Cons:** {cons}...\n* **Quotes:** {quotes}\n\n"
        return (mock, True)


def save_report(report_content: str) -> str:
    """Saves the markdown report to a file with today's date. Returns the file path."""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    file_path = os.path.join(REPORTS_DIR, f"market_intelligence_{date_str}.md")
    with open(file_path, "w") as f:
        f.write(report_content)
    logger.info("   📄 MASTER REPORT GENERATED: %s", file_path)
    return file_path


def run_reporter() -> None:
    """Load cloud data, generate report, save to file."""
    logger.info("Starting the V3 Intelligence Reporter...\n")
    data = get_cloud_data()

    if not data:
        logger.info("No fresh intelligence data found for today.")
        return

    logger.info("Drafting comprehensive intelligence report for %d targets...", len(data))
    report_content, is_mock = generate_batch_report(data)
    save_report(report_content)
    if is_mock:
        logger.info("(Mock report used due to AI limit.)")
    logger.info("✅ Reporter completed successfully.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    run_reporter()
