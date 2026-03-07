"""
Scout: gathers RSS articles, filters by NLP concepts, and extracts companies/products via AI into Supabase.
"""
import logging
import os
import sys
from typing import Optional, Tuple

# Allow importing config when running as python src/scout.py from repo root
_src_dir = os.path.dirname(os.path.abspath(__file__))
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

import feedparser
import spacy

from config import get_supabase, get_model, ARTICLES_PER_FEED

logger = logging.getLogger(__name__)

# --- Setup Local NLP (scout-only) ---
_nlp = None


def _get_nlp():
    """Lazy-load spaCy model so other scripts don't need it."""
    global _nlp
    if _nlp is None:
        _nlp = spacy.load("en_core_web_sm")
    return _nlp


# The NLP "Lemmas" (Root Concepts)
CORE_LEMMAS = {
    "launch", "announce", "release", "unveil", "beta", "debut",
    "acquire", "merge", "buy", "sell", "earn", "revenue", "profit",
    "layoff", "fire", "resign", "hire", "depart",
    "sue", "settle", "fine", "probe", "ban", "block",
    "partner", "collaborate", "expand", "halt", "delay",
}

RSS_FEEDS = [
    "https://techcrunch.com/feed/",
    "https://www.theverge.com/rss/index.xml",
    "https://www.wired.com/feed/rss",
    "https://www.engadget.com/rss.xml",
    "https://www.zdnet.com/news/rss.xml",
]


def passes_filter(text: str, nlp=None, lemmas=None):
    """
    Uses NLP to break the article into root words and check our concepts.
    Optional nlp/lemmas allow tests to inject dependencies.
    """
    if nlp is None:
        nlp = _get_nlp()
    if lemmas is None:
        lemmas = CORE_LEMMAS
    doc = nlp(text.lower())
    for token in doc:
        if token.lemma_ in lemmas:
            return True
    return False


def save_target_to_db(target_type: str, name: str, description: str) -> None:
    """Saves the extracted company or product to Supabase."""
    target_type = target_type.strip().upper()
    name = name.strip()
    if target_type not in ("COMPANY", "PRODUCT"):
        return

    supabase = get_supabase()
    try:
        existing = supabase.table("targets").select("*").eq("name", name).execute()
        data_list = getattr(existing, "data", None)
        new_headline = (description or "").strip()

        if data_list and len(data_list) > 0:
            # Already tracking: add a new event (multiple events per target)
            target_id = data_list[0].get("id")
            if not target_id or not new_headline:
                logger.info("   -> [%s] %s is already in the database. Skipping.", target_type, name)
                return
            # Avoid duplicate event: same target + same headline
            events_resp = supabase.table("events").select("id").eq("target_id", target_id).eq("headline", new_headline).execute()
            events_data = getattr(events_resp, "data", None) or []
            if events_data:
                logger.info("   -> [%s] %s already has event: \"%s\". Skipping.", target_type, name, new_headline[:50])
                return
            supabase.table("events").insert({"target_id": target_id, "headline": new_headline}).execute()
            logger.info("   📌 New event for [%s] %s: %s", target_type, name, new_headline[:60])
            return

        # New target: insert target then one event
        row = {
            "name": name,
            "target_type": target_type,
            "description": new_headline,
            "status": "tracking",
        }
        insert_result = supabase.table("targets").insert(row).execute()
        inserted = getattr(insert_result, "data", None)
        target_id = inserted[0].get("id") if inserted and len(inserted) > 0 else None
        if target_id and new_headline:
            supabase.table("events").insert({"target_id": target_id, "headline": new_headline}).execute()
        logger.info("   💾 SAVED: [%s] %s (event: %s)", target_type, name, new_headline[:50] if new_headline else "")
    except Exception as e:
        logger.exception("Database error for %s", name)
        logger.error("   ❌ Database Error for %s: %s", name, e)


def _parse_ai_extraction_line(line: str) -> Optional[Tuple[str, str, str]]:
    """
    Parse a single line of AI output: TYPE | Name | Description (description may contain |).
    Returns (target_type, name, description) or None if invalid.
    """
    line = line.strip()
    if "|" not in line:
        return None
    parts = line.split("|", 2)  # max 3 parts: type, name, rest is description
    if len(parts) < 3:
        return None
    target_type = parts[0].strip().upper()
    if target_type not in ("COMPANY", "PRODUCT"):
        return None
    name = parts[1].strip()
    description = parts[2].strip()
    if not name:
        return None
    return (target_type, name, description)


def run_scout() -> None:
    """Gather RSS articles, filter by concepts, then batch-extract targets via AI and save to DB."""
    logger.info("Gathering articles from %d sources...\n", len(RSS_FEEDS))
    articles_to_analyze = []

    for feed_url in RSS_FEEDS:
        try:
            logger.info("📡 Scanning: %s", feed_url)
            feed = feedparser.parse(feed_url)
            entries = getattr(feed, "entries", [])[:ARTICLES_PER_FEED]
            for entry in entries:
                title = getattr(entry, "title", "") or ""
                summary = entry.get("summary", "") or ""
                if passes_filter(title + " " + summary):
                    articles_to_analyze.append(f"Title: {title}\nSummary: {summary}\n")
        except Exception as e:
            logger.warning("Could not read %s: %s", feed_url, e)

    if not articles_to_analyze:
        logger.info("No market-moving articles found today.")
        return

    logger.info(
        "Filtered raw articles down to %d highly relevant ones. Sending ONE batch request to the AI...\n",
        len(articles_to_analyze),
    )
    batch_text = "\n---\n".join(articles_to_analyze)

    prompt = f"""
    You are an expert tech market analyst. Read the following batch of news articles.
    Extract EVERY major COMPANY event and EVERY new PRODUCT launch mentioned across all articles.

    Rules:
    1. A single article might mention multiple companies and products. Extract all of them.
    2. Format your response exactly like this, with one entity per line:
    COMPANY | [Company Name] | [1-sentence summary of event]
    PRODUCT | [Product Name] | [1-sentence summary of launch]

    Do not include any other conversational text, headers, or markdown.
    If absolutely nothing is found, output NONE.

    Articles:
    {batch_text}
    """

    try:
        model = get_model()
        response = model.generate_content(prompt)
        raw_text = (response.text or "").strip()
        if raw_text.upper() == "NONE":
            logger.info("AI found no entities to extract.")
            return
        for line in raw_text.split("\n"):
            parsed = _parse_ai_extraction_line(line)
            if parsed:
                save_target_to_db(parsed[0], parsed[1], parsed[2])
        logger.info("✅ Scout completed successfully.")
    except Exception as e:
        logger.error("⚠️ AI API Error (You might still be out of quota!): %s", e)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    run_scout()
