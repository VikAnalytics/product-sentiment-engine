"""
Tracker: fetches HN/Reddit chatter for each target, filters by vector similarity, extracts pros/cons via AI, saves to Supabase.
"""
import json
import logging
import os
import sys
import time
from typing import Optional

import requests
from datetime import datetime
from logging.handlers import RotatingFileHandler
from sentence_transformers import SentenceTransformer

# Allow importing config when running as python src/tracker.py from repo root
_src_dir = os.path.dirname(os.path.abspath(__file__))
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from config import (
    get_supabase,
    get_json_model,
    MATCH_THRESHOLD,
    HTTP_TIMEOUT_SEC,
    REQUEST_DELAY_BETWEEN_TARGETS_SEC,
    HN_SEARCH_LIMIT,
    REDDIT_SEARCH_LIMIT,
    STACKOVERFLOW_SEARCH_LIMIT,
    GOOGLE_NEWS_LIMIT,
)

logger = logging.getLogger(__name__)

# When set to "1", run_tracker will not write new sentiment rows to the database.
DRY_RUN = os.getenv("TRACKER_DRY_RUN") == "1"

# Optional logging controls (useful for cron)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FILE = os.getenv("LOG_FILE", "").strip()  # e.g. logs/tracker.log


def _configure_logging() -> None:
    level = getattr(logging, LOG_LEVEL, logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)

    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    # Avoid duplicate handlers if module reloaded
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        sh.setLevel(level)
        root.addHandler(sh)

    if LOG_FILE:
        try:
            os.makedirs(os.path.dirname(LOG_FILE) or ".", exist_ok=True)
            fh = RotatingFileHandler(LOG_FILE, maxBytes=2_000_000, backupCount=3)
            fh.setFormatter(fmt)
            fh.setLevel(level)
            root.addHandler(fh)
        except Exception as e:
            # Fall back to console only
            root.warning("Failed to set LOG_FILE=%s (%s). Continuing with console logging.", LOG_FILE, e)

# Max extra words from description to add to search query (keeps API queries focused)
SEARCH_CONTEXT_WORDS = 5

# Local embedding model (used instead of Gemini for semantic dedupe)
_EMBED_MODEL_NAME = os.getenv("EMBED_MODEL_NAME", "all-mpnet-base-v2")
_embed_model: Optional[SentenceTransformer] = None


def _search_query_from_context(name: str, target_type: str, description: str) -> str:
    """
    Build a search query focused on the headline/context we're tracking.
    - For products: just use the product name.
    - For companies: use name + one meaningful keyword from the event/headline when available.
    """
    name = (name or "").strip()
    ttype = (target_type or "").strip().lower()
    if ttype == "product":
        return name
    if not description or not description.strip():
        return name
    # Take first meaningful word (non-stopword) from description/headline
    stop = {"a", "an", "the", "of", "for", "in", "on", "to", "is", "and", "or", "by"}
    words = [w for w in description.strip().split() if len(w) > 1 and w.lower() not in stop][:SEARCH_CONTEXT_WORDS]
    if not words:
        return name
    keyword = words[0]
    return f"{name} {keyword}".strip()


def search_hacker_news(query: str) -> str:
    """Fetch recent HN comments for the query. Returns combined text or empty string on error."""
    yesterday_timestamp = int(time.time()) - (24 * 3600)
    url = f"https://hn.algolia.com/api/v1/search_by_date?query={query}&tags=comment&numericFilters=created_at_i>{yesterday_timestamp}"
    try:
        response = requests.get(url, timeout=HTTP_TIMEOUT_SEC)
        response.raise_for_status()
        hits = response.json().get("hits", [])[:HN_SEARCH_LIMIT]
        logger.debug("HN query=%r hits=%s", query, len(hits))
        comments = []
        for hit in hits:
            raw_text = hit.get("comment_text", "") or ""
            clean_text = raw_text.replace("\n", " ").strip()
            obj_id = hit.get("objectID", "")
            item_url = f"https://news.ycombinator.com/item?id={obj_id}" if obj_id else ""
            comments.append(f"{clean_text} [URL: {item_url}]")
        return " ".join(comments) if comments else ""
    except requests.RequestException as e:
        logger.warning("Hacker News request failed for %s: %s", query, e)
        return ""


def search_reddit(query: str) -> str:
    """Fetch recent Reddit posts for the query. Returns combined text or empty string on error."""
    formatted_query = query.replace(" ", "%20")
    # Use api.reddit.com with a browser-like User-Agent; anonymous requests to www.reddit.com/search.json
    # are often rate-limited or blocked with 403.
    url = f"https://api.reddit.com/search?q={formatted_query}&sort=new&limit={REDDIT_SEARCH_LIMIT}&t=day&raw_json=1"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36",
        "Accept": "application/json",
    }
    try:
        response = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT_SEC)
        if response.status_code != 200:
            logger.warning("Reddit returned %s for query=%r", response.status_code, query)
            return ""
        children = response.json().get("data", {}).get("children", [])
        logger.debug("Reddit query=%r children=%s", query, len(children))
        comments = []
        for p in children:
            data = p.get("data", {}) or {}
            title = data.get("title", "") or ""
            raw_body = (data.get("selftext", "") or "")[:150]
            clean_body = raw_body.replace("\n", " ").strip()
            permalink = data.get("permalink", "") or ""
            post_url = f"https://www.reddit.com{permalink}"
            comments.append(f"{title} - {clean_body} [URL: {post_url}]")
        return " ".join(comments) if comments else ""
    except requests.RequestException as e:
        logger.warning("Reddit request failed for %s: %s", query, e)
        return ""


def search_stackoverflow(query: str) -> str:
    """Fetch recent Stack Overflow questions for the query. No API key needed for basic use.
    Returns combined title+body text or empty string on error."""
    url = (
        f"https://api.stackexchange.com/2.3/search"
        f"?order=desc&sort=creation&intitle={requests.utils.quote(query)}"
        f"&site=stackoverflow&pagesize={STACKOVERFLOW_SEARCH_LIMIT}&filter=withbody"
    )
    try:
        response = requests.get(url, timeout=HTTP_TIMEOUT_SEC)
        response.raise_for_status()
        items = response.json().get("items", [])[:STACKOVERFLOW_SEARCH_LIMIT]
        logger.debug("StackOverflow query=%r hits=%s", query, len(items))
        parts = []
        for item in items:
            title = (item.get("title") or "").strip()
            body = (item.get("body") or "")[:300].replace("\n", " ").strip()
            link = item.get("link") or ""
            parts.append(f"{title} - {body} [URL: {link}]")
        return " ".join(parts) if parts else ""
    except requests.RequestException as e:
        logger.warning("Stack Overflow request failed for %s: %s", query, e)
        return ""


def search_google_news_financial(query: str) -> str:
    """Fetch Google News RSS for financial/earnings context. Returns combined text or empty string."""
    import feedparser
    financial_query = requests.utils.quote(f"{query} earnings OR revenue OR quarterly results")
    url = f"https://news.google.com/rss/search?q={financial_query}&hl=en-US&gl=US&ceid=US:en"
    try:
        feed = feedparser.parse(url)
        entries = (getattr(feed, "entries", None) or [])[:GOOGLE_NEWS_LIMIT]
        logger.debug("GoogleNews query=%r hits=%s", query, len(entries))
        parts = []
        for entry in entries:
            title = (getattr(entry, "title", "") or "").strip()
            summary = (getattr(entry, "summary", "") or "")[:200].replace("\n", " ").strip()
            link = (getattr(entry, "link", "") or "").strip()
            parts.append(f"{title} - {summary} [URL: {link}]")
        return " ".join(parts) if parts else ""
    except Exception as e:
        logger.warning("Google News request failed for %s: %s", query, e)
        return ""


def _build_source_type(hn: bool, reddit: bool, so: bool, news: bool) -> str:
    """Build a pipe-separated source type string from which sources had data."""
    active = []
    if hn:
        active.append("hn")
    if reddit:
        active.append("reddit")
    if so:
        active.append("stackoverflow")
    if news:
        active.append("google_news")
    if not active:
        return "unknown"
    return "|".join(active)


def get_embedding(text: str) -> list:
    """Converts text into an embedding vector using a local model (no external API).

    Uses a SentenceTransformer model (`all-mpnet-base-v2` by default, 768-dim) so it
    remains compatible with the existing `vector(768)` column in Supabase.
    """
    global _embed_model
    if _embed_model is None:
        logger.info("Loading local embedding model: %s", _EMBED_MODEL_NAME)
        _embed_model = SentenceTransformer(_EMBED_MODEL_NAME)
    vec = _embed_model.encode(text, normalize_embeddings=False)
    return vec.tolist()


_VALID_TAGS = {"threat", "opportunity", "monitor", "no_action"}


def _parse_json_sentiment(text: str) -> Optional[dict]:
    """
    Parse Gemini JSON-mode response into a sentiment dict.
    Expected keys: pros, cons, verbatim_quotes, source_url, sentiment_score, implication_tag.
    Returns None if the JSON is missing required keys or is unparseable.
    """
    text = text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning("JSON parse error: %s | raw=%r", e, text[:200])
        return None

    if not isinstance(data, dict):
        return None

    pros = str(data.get("pros") or "").strip()
    cons = str(data.get("cons") or "").strip()
    quotes = str(data.get("verbatim_quotes") or "").strip()
    url = str(data.get("source_url") or "").strip()

    if not any([pros, cons, quotes]):
        return None

    result = {
        "pros": pros,
        "cons": cons,
        "verbatim_quotes": quotes,
        "source_url": url,
        "sentiment_score": None,
        "implication_tag": None,
    }

    raw_score = data.get("sentiment_score")
    if raw_score is not None:
        try:
            result["sentiment_score"] = max(-10, min(10, int(raw_score)))
        except (TypeError, ValueError):
            pass

    raw_tag = str(data.get("implication_tag") or "").strip().lower()
    if raw_tag in _VALID_TAGS:
        result["implication_tag"] = raw_tag

    return result


def _parse_ai_sentiment_line(line: str) -> Optional[dict]:
    """
    Parse AI response line: PROS: ... | CONS: ... | QUOTES: ... | URL: ... | SCORE: N | TAG: tag
    SCORE and TAG are optional for backward compatibility with old rows.
    Returns dict with pros, cons, verbatim_quotes, source_url, sentiment_score, implication_tag or None.
    """
    line = line.strip().replace("\n", " ")
    if "PROS:" not in line or "CONS:" not in line or "QUOTES:" not in line or "URL:" not in line:
        return None
    parts = [p.strip() for p in line.split("|", 5)]
    if len(parts) < 4:
        return None
    result = {
        "pros": parts[0].replace("PROS:", "").strip(),
        "cons": parts[1].replace("CONS:", "").strip(),
        "verbatim_quotes": parts[2].replace("QUOTES:", "").strip(),
        "source_url": parts[3].replace("URL:", "").strip(),
        "sentiment_score": None,
        "implication_tag": None,
    }
    if len(parts) >= 5:
        raw_score = parts[4].replace("SCORE:", "").strip()
        try:
            score = int(raw_score)
            result["sentiment_score"] = max(-10, min(10, score))
        except (ValueError, TypeError):
            pass
    if len(parts) >= 6:
        raw_tag = parts[5].replace("TAG:", "").strip().lower()
        if raw_tag in _VALID_TAGS:
            result["implication_tag"] = raw_tag
    return result


def run_tracker() -> None:
    """For each tracking target and each of its events, fetch chatter, vector-filter, extract sentiment, and save if net-new."""
    logger.info("Starting tracker (per-event). dry_run=%s max_events=%s", DRY_RUN, os.getenv("TRACKER_MAX_EVENTS", "0"))
    supabase = get_supabase()
    targets_result = supabase.table("targets").select("*").eq("status", "tracking").execute()
    targets = getattr(targets_result, "data", None) or []
    if not targets:
        return

    today_str = datetime.utcnow().strftime("%Y-%m-%d")

    # Optional cap: limit how many (target,event) searches we perform in a run.
    # Useful for quick tests: set TRACKER_MAX_EVENTS=5 to only process the first 5 events.
    try:
        max_events = int(os.getenv("TRACKER_MAX_EVENTS", "0"))
    except ValueError:
        max_events = 0
    events_processed = 0

    for t in targets:
        name = t.get("name")
        t_id = t.get("id")
        target_type = (t.get("target_type") or "").strip()
        if name is None or t_id is None:
            logger.warning("Skipping target with missing name or id: %s", t)
            continue

        # Load events for this target; if none (legacy), use one virtual event from target.description
        events_resp = supabase.table("events").select("*").eq("target_id", t_id).order("created_at", desc=True).execute()
        events_list = getattr(events_resp, "data", None) or []
        if not events_list:
            events_list = [{"id": None, "headline": (t.get("description") or "").strip() or "(general)"}]

        for event in events_list:
            if max_events and events_processed >= max_events:
                logger.info("Reached TRACKER_MAX_EVENTS=%s. Stopping early.", max_events)
                return

            event_id = event.get("id")
            headline = (event.get("headline") or "").strip() or "(general)"

            # Daily idempotency per event
            existing_q = supabase.table("sentiment").select("id").eq("target_id", t_id).gte("created_at", today_str)
            if event_id is not None:
                existing_q = existing_q.eq("event_id", event_id)
            else:
                existing_q = existing_q.is_("event_id", None)
            existing = existing_q.execute()
            existing_data = getattr(existing, "data", None)
            if existing_data and len(existing_data) > 0:
                logger.info("   -> Already scanned %s [%s] today. Skipping.", name, headline[:40])
                if REQUEST_DELAY_BETWEEN_TARGETS_SEC > 0:
                    time.sleep(REQUEST_DELAY_BETWEEN_TARGETS_SEC)
                continue

            search_query = _search_query_from_context(name, target_type, headline)
            logger.info("📡 %s | %s | query=%r", name, headline[:80], search_query)
            hn_data = search_hacker_news(search_query)
            reddit_data = search_reddit(search_query)
            so_data = search_stackoverflow(search_query)
            news_data = search_google_news_financial(name)  # use bare name for financial news

            combined_chatter = ""
            if hn_data:
                combined_chatter += f"[SOURCE: Hacker News] {hn_data} "
            if reddit_data:
                combined_chatter += f"[SOURCE: Reddit] {reddit_data} "
            if so_data:
                combined_chatter += f"[SOURCE: Stack Overflow] {so_data} "
            if news_data:
                combined_chatter += f"[SOURCE: Google News Financial] {news_data}"

            source_type = _build_source_type(bool(hn_data), bool(reddit_data), bool(so_data), bool(news_data))

            if not combined_chatter.strip():
                logger.info(
                    "   -> No fresh chatter (hn=%s reddit=%s so=%s news=%s).",
                    bool(hn_data), bool(reddit_data), bool(so_data), bool(news_data),
                )
                if REQUEST_DELAY_BETWEEN_TARGETS_SEC > 0:
                    time.sleep(REQUEST_DELAY_BETWEEN_TARGETS_SEC)
                continue

            events_processed += 1

            chatter_vector = None
            try:
                chatter_vector = get_embedding(combined_chatter)
            except Exception as e:
                logger.warning(
                    "   ⚠️ Embedding API Error for %s (skipping vector dedupe but continuing): %s",
                    name,
                    e,
                )

            # If we have an embedding, use match_sentiment for vector dedupe; otherwise skip dedupe and proceed.
            if chatter_vector is not None:
                rpc_params = {
                    "query_embedding": chatter_vector,
                    "match_threshold": MATCH_THRESHOLD,
                    "p_target_id": t_id,
                    # Always send p_event_id (can be None) so PostgREST can disambiguate
                    # between the 3-arg and 4-arg match_sentiment overloads.
                    "p_event_id": event_id,
                }
                match_response = supabase.rpc("match_sentiment", rpc_params).execute()

                match_data = getattr(match_response, "data", None)
                if match_data and len(match_data) > 0:
                    first = match_data[0]
                    similarity = first.get("similarity", 0)
                    logger.info(
                        "   🛑 Vector Match (Score: %.2f): %s [%s] redundant. Discarding.",
                        similarity,
                        name,
                        headline[:40],
                    )
                    if REQUEST_DELAY_BETWEEN_TARGETS_SEC > 0:
                        time.sleep(REQUEST_DELAY_BETWEEN_TARGETS_SEC)
                    continue

            tracking_context = headline
            prompt = f"""
You are a Principal Market Intelligence Analyst.
We are tracking: "{name}" in the context of: "{tracking_context}".
Focus on market sentiment related to THIS specific topic. If chatter mentions other themes, note them only briefly.

Analyze the chatter below and return a single JSON object with exactly these keys:
{{
  "pros": "brief summary of positive market sentiment (or empty string if none)",
  "cons": "brief summary of negative market sentiment (or empty string if none)",
  "verbatim_quotes": "one direct quote from the chatter that best captures the mood",
  "source_url": "URL of the most relevant source from the chatter",
  "sentiment_score": <integer from -10 to 10; -10=very negative, 0=neutral, +10=very positive>,
  "implication_tag": "<one of: threat, opportunity, monitor, no_action>"
}}

implication_tag rules:
- threat: negative sentiment indicating a competitor gaining ground or risk to our position
- opportunity: positive signal about a gap or weakness we could exploit
- monitor: ambiguous/early signal worth watching but not yet actionable
- no_action: neutral noise with no clear strategic implication

Chatter data:
{combined_chatter}
"""

            try:
                json_model = get_json_model()
                ai_response = json_model.generate_content(prompt)
                raw_text = (ai_response.text or "").strip()
                parsed = _parse_json_sentiment(raw_text)
                if parsed is None:
                    # Fallback: try legacy pipe format in case JSON mode returned plain text
                    parsed = _parse_ai_sentiment_line(raw_text.replace("\n", " "))
                if parsed:
                    insert_row = {
                        "target_id": t_id,
                        "pros": parsed["pros"],
                        "cons": parsed["cons"],
                        "verbatim_quotes": parsed["verbatim_quotes"],
                        "source_url": parsed["source_url"],
                        "embedding": chatter_vector,
                    }
                    if parsed.get("sentiment_score") is not None:
                        insert_row["sentiment_score"] = parsed["sentiment_score"]
                    if parsed.get("implication_tag") is not None:
                        insert_row["implication_tag"] = parsed["implication_tag"]
                    insert_row["source_type"] = source_type
                    if event_id is not None:
                        insert_row["event_id"] = event_id
                    # Text-exact guard: if we already have an identical pros/cons/quotes triple
                    # for this target/event, skip inserting (regardless of date).
                    dup_query = (
                        supabase.table("sentiment")
                        .select("id")
                        .eq("target_id", t_id)
                        .eq("pros", insert_row["pros"])
                        .eq("cons", insert_row["cons"])
                        .eq("verbatim_quotes", insert_row["verbatim_quotes"])
                    )
                    if event_id is not None:
                        dup_query = dup_query.eq("event_id", event_id)
                    dup_resp = dup_query.execute()
                    dup_data = getattr(dup_resp, "data", None) or []
                    if dup_data:
                        logger.info(
                            "   ↩️ Identical sentiment already exists for %s [%s]. Skipping insert.",
                            name,
                            headline[:50],
                        )
                    else:
                        if DRY_RUN:
                            logger.info(
                                "   💾 [DRY RUN] Would save net-new intelligence for %s [%s]",
                                name,
                                headline[:50],
                            )
                        else:
                            supabase.table("sentiment").insert(insert_row).execute()
                            logger.info("   💾 SAVED NET-NEW INTELLIGENCE: %s [%s]", name, headline[:50])
                else:
                    logger.warning("   ⚠️ AI output format error for %s.", name)
            except Exception as e:
                logger.error("⚠️ AI API Error: %s", e)

            if REQUEST_DELAY_BETWEEN_TARGETS_SEC > 0:
                time.sleep(REQUEST_DELAY_BETWEEN_TARGETS_SEC)

    logger.info("Tracker run finished.")


if __name__ == "__main__":
    _configure_logging()
    run_tracker()
