"""
Tracker: fetches HN/Reddit chatter for each target, filters by vector similarity, extracts pros/cons via AI, saves to Supabase.
"""
import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from typing import Optional

import requests
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
    GOOGLE_NEWS_LIMIT,
    MAX_CHATTER_CHARS,
    EVENT_MAX_AGE_DAYS,
    fetch_all_rows,
    HTTP_USER_AGENT,
)
from events import event_time_iso, sort_by_event_time, within_age

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
    url = f"https://hn.algolia.com/api/v1/search_by_date?query={requests.utils.quote(query)}&tags=comment&numericFilters=created_at_i>{yesterday_timestamp}"
    try:
        response = requests.get(url, timeout=HTTP_TIMEOUT_SEC)
        response.raise_for_status()
        hits = response.json().get("hits", [])[:HN_SEARCH_LIMIT]
        logger.debug("HN query=%r hits=%s", query, len(hits))
        comments = []
        for hit in hits:
            raw_text = (hit.get("comment_text", "") or "")[:300]
            clean_text = raw_text.replace("\n", " ").strip()
            obj_id = hit.get("objectID", "")
            item_url = f"https://news.ycombinator.com/item?id={obj_id}" if obj_id else ""
            comments.append(f"{clean_text} [URL: {item_url}]")
        return " ".join(comments) if comments else ""
    except requests.RequestException as e:
        logger.warning("Hacker News request failed for %s: %s", query, e)
        return ""


def search_reddit(query: str) -> str:
    """Fetch recent Reddit posts via RSS feed (no auth required). Returns combined text or empty string on error."""
    import feedparser
    encoded = requests.utils.quote(query)
    url = f"https://www.reddit.com/search.rss?q={encoded}&sort=new&t=day&limit={REDDIT_SEARCH_LIMIT}"
    headers = {"User-Agent": "ProductSentimentEngine/1.0"}
    try:
        response = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT_SEC)
        if response.status_code != 200:
            logger.warning("Reddit RSS returned %s for query=%r", response.status_code, query)
            return ""
        feed = feedparser.parse(response.text)
        entries = (getattr(feed, "entries", None) or [])[:REDDIT_SEARCH_LIMIT]
        logger.debug("Reddit query=%r entries=%s", query, len(entries))
        parts = []
        for entry in entries:
            title = (getattr(entry, "title", "") or "").strip()
            summary = (getattr(entry, "summary", "") or "")[:200].replace("\n", " ").strip()
            link = (getattr(entry, "link", "") or "").strip()
            parts.append(f"{title} - {summary} [URL: {link}]")
        return " ".join(parts) if parts else ""
    except Exception as e:
        logger.warning("Reddit request failed for %s: %s", query, e)
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


def search_stocktwits(ticker: str) -> str:
    """Fetch latest StockTwits messages for a ticker. No auth required for public streams."""
    if not ticker:
        return ""
    url = f"https://api.stocktwits.com/api/2/streams/symbol/{requests.utils.quote(ticker)}.json"
    try:
        # StockTwits 403s the default requests agent, so send a browser one.
        response = requests.get(
            url, timeout=HTTP_TIMEOUT_SEC, headers={"User-Agent": HTTP_USER_AGENT}
        )
        if response.status_code != 200:
            logger.warning("StockTwits returned %s for ticker=%r", response.status_code, ticker)
            return ""
        messages = response.json().get("messages", [])[:5]
        parts = []
        for m in messages:
            body = (m.get("body") or "").strip()[:200]
            sentiment = m.get("entities", {}).get("sentiment", {})
            label = sentiment.get("basic", "") if sentiment else ""
            parts.append(f"{body} [{label}]" if label else body)
        return " ".join(parts) if parts else ""
    except Exception as e:
        logger.warning("StockTwits request failed for %s: %s", ticker, e)
        return ""


def search_yahoo_finance_ticker(ticker: str) -> str:
    """Fetch Yahoo Finance news RSS for a specific ticker."""
    if not ticker:
        return ""
    import feedparser
    url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={requests.utils.quote(ticker)}&region=US&lang=en-US"
    try:
        feed = feedparser.parse(url)
        entries = (getattr(feed, "entries", None) or [])[:5]
        parts = []
        for entry in entries:
            title = (getattr(entry, "title", "") or "").strip()
            summary = (getattr(entry, "summary", "") or "")[:200].replace("\n", " ").strip()
            link = (getattr(entry, "link", "") or "").strip()
            parts.append(f"{title} - {summary} [URL: {link}]")
        return " ".join(parts) if parts else ""
    except Exception as e:
        logger.warning("Yahoo Finance RSS failed for %s: %s", ticker, e)
        return ""


def search_google_news_general(query: str) -> str:
    """Fetch Google News RSS for broad stock-moving events (M&A, regulatory, analyst actions)."""
    import feedparser
    broad_query = requests.utils.quote(
        f"{query} stock OR shares OR analyst OR merger OR acquisition OR FDA OR antitrust OR lawsuit OR recall OR tariff"
    )
    url = f"https://news.google.com/rss/search?q={broad_query}&hl=en-US&gl=US&ceid=US:en"
    try:
        feed = feedparser.parse(url)
        entries = (getattr(feed, "entries", None) or [])[:GOOGLE_NEWS_LIMIT]
        parts = []
        for entry in entries:
            title = (getattr(entry, "title", "") or "").strip()
            summary = (getattr(entry, "summary", "") or "")[:200].replace("\n", " ").strip()
            link = (getattr(entry, "link", "") or "").strip()
            parts.append(f"{title} - {summary} [URL: {link}]")
        return " ".join(parts) if parts else ""
    except Exception as e:
        logger.warning("Google News general failed for %s: %s", query, e)
        return ""


def _build_source_type(hn: bool, reddit: bool, news: bool, stocktwits: bool = False,
                       yahoo: bool = False, gnews_general: bool = False) -> str:
    """Build a pipe-separated source type string from which sources had data."""
    active = []
    if hn:            active.append("hn")
    if reddit:        active.append("reddit")
    if news:          active.append("google_news")
    if stocktwits:    active.append("stocktwits")
    if yahoo:         active.append("yahoo_finance")
    if gnews_general: active.append("gnews_general")
    return "|".join(active) if active else "unknown"


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

    raw_score = data.get("sentiment_score")
    has_score = raw_score is not None and str(raw_score).strip() != ""

    # A reading with a score but no prose is still usable: it drives the feed badge,
    # the rankings and the simulator's sentiment factor. Only reject when the model
    # gave us nothing at all. Headline-only events land here most often, since there
    # is no chatter to quote.
    if not any([pros, cons, quotes]) and not has_score:
        return None

    result = {
        "pros": pros,
        "cons": cons,
        "verbatim_quotes": quotes,
        "source_url": url,
        "sentiment_score": None,
        "implication_tag": None,
    }

    if has_score:
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


def run_tracker() -> dict:
    """
    For each tracking target and each of its events, fetch chatter, vector-filter,
    extract sentiment, and save if net-new.

    Returns a metrics dict for telemetry. The counters matter as much as the work:
    a run that writes nothing looks identical to a healthy one from the outside.
    """
    logger.info("Starting tracker (per-event). dry_run=%s max_events=%s", DRY_RUN, os.getenv("TRACKER_MAX_EVENTS", "0"))
    supabase = get_supabase()
    metrics = {
        "targets": 0, "events_seen": 0, "scored": 0, "headline_only": 0,
        "skipped_stale": 0, "skipped_already_scanned": 0, "skipped_duplicate": 0,
        "ai_errors": 0, "source_hits": {k: 0 for k in
                                        ("hn", "reddit", "google_news", "gnews_general",
                                         "stocktwits", "yahoo_finance")},
    }
    targets = fetch_all_rows(
        lambda: supabase.table("targets").select("*").eq("status", "tracking").order("id")
    )
    metrics["targets"] = len(targets)
    if not targets:
        return metrics

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
        ticker = (t.get("ticker") or "").strip()
        target_type = (t.get("target_type") or "").strip()
        if name is None or t_id is None:
            logger.warning("Skipping target with missing name or id: %s", t)
            continue

        # Load events for this target; if none (legacy), use one virtual event from target.description
        events_resp = supabase.table("events").select("*").eq("target_id", t_id).order("created_at", desc=True).execute()
        events_list = getattr(events_resp, "data", None) or []
        if not events_list:
            events_list = [{"id": None, "headline": (t.get("description") or "").strip() or "(general)"}]
        # Newest news first, by when it broke rather than when it was ingested.
        events_list = sort_by_event_time(events_list, reverse=True)

        cutoff_dt = datetime.now(timezone.utc) - timedelta(days=EVENT_MAX_AGE_DAYS)

        for event in events_list:
            if max_events and events_processed >= max_events:
                logger.info("Reached TRACKER_MAX_EVENTS=%s. Stopping early.", max_events)
                return metrics

            metrics["events_seen"] += 1
            event_id = event.get("id")
            headline = (event.get("headline") or "").strip() or "(general)"

            # E: skip events older than EVENT_MAX_AGE_DAYS (avoids dead HTTP calls on stale news).
            # Measured from publication, so a late-ingested story is judged by its own age.
            if event_id is not None and not within_age(event, cutoff_dt):
                logger.debug("   -> Event too old (%s), skipping: %s [%s]",
                             event_time_iso(event)[:10], name, headline[:40])
                metrics["skipped_stale"] += 1
                continue

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
                metrics["skipped_already_scanned"] += 1
                continue

            search_query = _search_query_from_context(name, target_type, headline)
            logger.info("📡 %s | %s | query=%r", name, headline[:80], search_query)

            # A: fetch all sources concurrently (6 workers: 3 existing + 3 new)
            with ThreadPoolExecutor(max_workers=6) as pool:
                fut_hn          = pool.submit(search_hacker_news, search_query)
                fut_reddit      = pool.submit(search_reddit, search_query)
                fut_news_fin    = pool.submit(search_google_news_financial, name)
                fut_news_gen    = pool.submit(search_google_news_general, name)
                fut_stocktwits  = pool.submit(search_stocktwits, ticker)
                fut_yahoo       = pool.submit(search_yahoo_finance_ticker, ticker)
                hn_data         = fut_hn.result()
                reddit_data     = fut_reddit.result()
                news_data       = fut_news_fin.result()
                gnews_data      = fut_news_gen.result()
                stocktwits_data = fut_stocktwits.result()
                yahoo_data      = fut_yahoo.result()

            for key, hit in (
                ("hn", hn_data), ("reddit", reddit_data), ("google_news", news_data),
                ("gnews_general", gnews_data), ("stocktwits", stocktwits_data),
                ("yahoo_finance", yahoo_data),
            ):
                if hit:
                    metrics["source_hits"][key] += 1

            combined_chatter = ""
            if hn_data:
                combined_chatter += f"[SOURCE: Hacker News] {hn_data} "
            if reddit_data:
                combined_chatter += f"[SOURCE: Reddit] {reddit_data} "
            if news_data:
                combined_chatter += f"[SOURCE: Google News Financial] {news_data} "
            if gnews_data:
                combined_chatter += f"[SOURCE: Google News General] {gnews_data} "
            if stocktwits_data:
                combined_chatter += f"[SOURCE: StockTwits] {stocktwits_data} "
            if yahoo_data:
                combined_chatter += f"[SOURCE: Yahoo Finance] {yahoo_data}"

            # C: truncate chatter before sending to AI
            if len(combined_chatter) > MAX_CHATTER_CHARS:
                combined_chatter = combined_chatter[:MAX_CHATTER_CHARS]

            source_type = _build_source_type(
                bool(hn_data), bool(reddit_data), bool(news_data),
                bool(stocktwits_data), bool(yahoo_data), bool(gnews_data),
            )

            # No community chatter does not mean no signal. The headline itself is
            # market information ("Buffett steps down as chairman" needs no Reddit
            # thread to be readable), and obscure products simply have no forum
            # presence. Dropping these events left roughly a third of the feed with
            # no score at all, so fall back to scoring the headline on its own and
            # mark the row so headline-only readings stay distinguishable.
            headline_only = False
            if not combined_chatter.strip():
                if not headline or headline.strip() == "(general)":
                    logger.info("   -> No chatter and no usable headline. Skipping.")
                    continue
                combined_chatter = f"[SOURCE: Headline] {headline}"
                source_type = "headline_only"
                headline_only = True
                metrics["headline_only"] += 1
                logger.info(
                    "   -> No fresh chatter (hn=%s reddit=%s news=%s) — scoring headline alone.",
                    bool(hn_data), bool(reddit_data), bool(news_data),
                )

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
                    metrics["skipped_duplicate"] += 1
                    continue

            tracking_context = headline
            # With only a headline there is nothing to quote and no source to cite,
            # so say so rather than letting the model invent either.
            mode_note = (
                "\nThere is no community chatter for this event, only the headline. "
                "Judge it on the headline alone, leave verbatim_quotes and source_url "
                "as empty strings, and keep the score conservative.\n"
                if headline_only else ""
            )
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
{mode_note}
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
                        metrics["scored"] += 1
                else:
                    logger.warning("   ⚠️ AI output format error for %s.", name)
                    metrics["ai_errors"] += 1
            except Exception as e:
                logger.error("⚠️ AI API Error: %s", e)
                metrics["ai_errors"] += 1

            if REQUEST_DELAY_BETWEEN_TARGETS_SEC > 0:
                time.sleep(REQUEST_DELAY_BETWEEN_TARGETS_SEC)

    logger.info(
        "Tracker run finished. events_seen=%d scored=%d headline_only=%d duplicates=%d ai_errors=%d",
        metrics["events_seen"], metrics["scored"], metrics["headline_only"],
        metrics["skipped_duplicate"], metrics["ai_errors"],
    )
    return metrics


if __name__ == "__main__":
    from logging_setup import setup_logging
    from pipeline_telemetry import step

    setup_logging()
    _configure_logging()  # no-op: setup_logging has already installed a handler
    with step("tracker") as s:
        m = run_tracker()
        s.rows(m["scored"])
        s.note(**m)

        # Health rules. These exist because the pipeline reported success for
        # months while StockTwits answered 403 to every call and a third of
        # events were being dropped.
        attempted = m["events_seen"] - m["skipped_stale"] - m["skipped_already_scanned"]
        silent = [name for name, hits in m["source_hits"].items() if hits == 0]
        if silent and attempted > 0:
            s.degrade(f"sources returned nothing all run: {', '.join(sorted(silent))}")
        s.check(attempted > 0 and m["scored"] == 0, "no sentiment written despite events to score")
        s.check(
            attempted >= 20 and m["headline_only"] / attempted > 0.5,
            f"over half of readings came from headlines alone ({m['headline_only']}/{attempted})",
        )
        s.check(
            attempted >= 10 and m["ai_errors"] / attempted > 0.2,
            f"AI failed on {m['ai_errors']} of {attempted} events",
        )
