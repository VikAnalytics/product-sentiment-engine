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
from sentiment_dedupe import normalize_for_dedupe

logger = logging.getLogger(__name__)

_default_reports_dir = os.path.normpath(os.path.join(_src_dir, "..", "reports"))
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
                .select("id, target_id, event_id, pros, cons, verbatim_quotes, source_url, created_at, sentiment_score")
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

            # Compute average sentiment score for this event (skip nulls from old rows)
            scores = [s.get("sentiment_score") for s in sentiments if s.get("sentiment_score") is not None]
            avg_score = round(sum(scores) / len(scores)) if scores else None

            if all_pros or all_cons or all_quotes:
                full_data.append({
                    "name": t_name,
                    "type": t_type,
                    "description": headline,
                    "pros": all_pros,
                    "cons": all_cons,
                    "quotes": all_quotes,
                    "event_id": event_id,
                    "sentiment_score": avg_score,
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
        score = item.get("sentiment_score")
        score_str = f"SENTIMENT SCORE: {score:+d}/10\n" if score is not None else ""
        # Each item is one (target, event); description is the event headline
        payload_lines.append(
            f"[{item.get('type', '')}] {item.get('name', '')} | Event: {item.get('description', '')}\n"
            f"{score_str}"
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
    * **Sentiment Score:** (If a SENTIMENT SCORE is provided, repeat it here and interpret what it means strategically, e.g. "Score: +6/10 — Strong positive reception.")
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



def _build_event_lookup(supabase):
    """Build normalized (target_name, headline) -> event_id; norm_target -> [event_id]; norm_target -> target_id."""
    targets_resp = supabase.table("targets").select("id, name").execute()
    targets_list = getattr(targets_resp, "data", None) or []
    targets = {t["id"]: (t.get("name") or "").strip() for t in targets_list}
    name_to_target_id = {normalize_for_dedupe(t.get("name") or ""): t["id"] for t in targets_list if t.get("id")}
    events_resp = supabase.table("events").select("id, target_id, headline").execute()
    events = getattr(events_resp, "data", None) or []
    lookup = {}
    by_target = {}
    for e in events:
        t_name = targets.get(e.get("target_id"), "").strip()
        headline = (e.get("headline") or "").strip()
        if t_name and e.get("id"):
            key = (normalize_for_dedupe(t_name), normalize_for_dedupe(headline))
            lookup[key] = e["id"]
            nt = normalize_for_dedupe(t_name)
            by_target.setdefault(nt, []).append(e["id"])
    return lookup, by_target, name_to_target_id


def parse_report_and_store_analyses(report_content: str) -> int:
    """
    Parse the generated report markdown, extract Strategic Analysis per target/event,
    and write to events.cached_analysis so the dashboard can show it without calling Gemini.
    Uses normalized (target, headline) so small formatting differences (e.g. NetChoice vs netchoice) still match.
    Returns number of events updated.
    """
    supabase = get_supabase()
    lookup, by_target, name_to_target_id = _build_event_lookup(supabase)
    # Sections: ### Target | Event: headline or ### Target - Event: headline
    section_re = re.compile(r"^###\s+(.+?)\s+[|\-]\s+Event:\s+(.+?)\s*$", re.MULTILINE)
    analysis_re = re.compile(r"\*\s*\*\*Strategic Analysis:\*\*\s*(.+?)(?=\n\s*\*\s*\*\*|\n###|\n##|\Z)", re.DOTALL)
    updated = 0
    for m in section_re.finditer(report_content):
        target_name = (m.group(1) or "").strip()
        headline = (m.group(2) or "").strip()
        start = m.end()
        next_section = report_content.find("\n### ", start)
        block = report_content[start : next_section] if next_section > 0 else report_content[start:]
        am = analysis_re.search(block)
        if not am:
            continue
        analysis_text = (am.group(1) or "").strip()
        if not analysis_text:
            continue
        key = (normalize_for_dedupe(target_name), normalize_for_dedupe(headline))
        event_id = lookup.get(key)
        if not event_id and key[0]:
            candidates = by_target.get(key[0], [])
            if len(candidates) == 1:
                event_id = candidates[0]
        # If still no event (e.g. sentiment was event_id=null / "virtual" event), use existing or create one
        if not event_id and key[0]:
            target_id = name_to_target_id.get(key[0])
            if target_id:
                all_for_target = supabase.table("events").select("id, headline").eq("target_id", target_id).execute()
                events_list = getattr(all_for_target, "data", None) or []
                # Prefer exact headline match
                for e in events_list:
                    if (e.get("headline") or "").strip() == headline:
                        event_id = e["id"]
                        break
                if not event_id and len(events_list) == 1:
                    # Single event for this target: reuse it instead of creating a duplicate
                    event_id = events_list[0]["id"]
                elif not event_id and len(events_list) == 0:
                    ins = supabase.table("events").insert({"target_id": target_id, "headline": headline}).execute()
                    new_data = getattr(ins, "data", None) or []
                    event_id = new_data[0]["id"] if new_data else None
                    if event_id:
                        logger.info("   Created event for %s (no event row existed); storing analysis.", target_name)
                # If 2+ events and no headline match, we don't create another; skip to avoid more duplicates
        if not event_id:
            logger.debug("   Skipped section %s: no matching event or target.", target_name)
            continue
        try:
            supabase.table("events").update({
                "cached_analysis": analysis_text,
                "cached_analysis_at": datetime.utcnow().isoformat(),
            }).eq("id", event_id).execute()
            updated += 1
        except Exception as e:
            logger.warning("   Failed to store analysis for event %s: %s", event_id, e)
    if updated:
        logger.info("   💾 Stored strategic analysis for %d event(s) (dashboard will use these).", updated)
    return updated


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
    # Always parse and store analyses from whatever we saved (real or mock; mock format just matches nothing)
    parse_report_and_store_analyses(report_content)
    if is_mock:
        logger.info("(Mock report used due to AI limit.)")
    logger.info("✅ Reporter completed successfully.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if len(sys.argv) > 1:
        # Backfill: re-parse an existing report file and store analyses into events (no Gemini call)
        path = sys.argv[1]
        if not os.path.isfile(path):
            logging.error("Report file not found: %s", path)
            sys.exit(1)
        with open(path, "r") as f:
            content = f.read()
        logging.info("Re-parsing report and storing strategic analyses: %s", path)
        n = parse_report_and_store_analyses(content)
        logging.info("✅ Stored strategic analysis for %d event(s). Refresh the dashboard.", n)
    else:
        run_reporter()
