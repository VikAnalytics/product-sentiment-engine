"""
Tracker: fetches HN/Reddit chatter for each target, filters by vector similarity, extracts pros/cons via AI, saves to Supabase.
"""
import logging
import os
import sys
import time
from typing import Optional

import requests
from datetime import datetime

# Allow importing config when running as python src/tracker.py from repo root
_src_dir = os.path.dirname(os.path.abspath(__file__))
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from config import (
    get_supabase,
    get_model,
    get_embedding_model_name,
    MATCH_THRESHOLD,
    HTTP_TIMEOUT_SEC,
    REQUEST_DELAY_BETWEEN_TARGETS_SEC,
    HN_SEARCH_LIMIT,
    REDDIT_SEARCH_LIMIT,
)

logger = logging.getLogger(__name__)

# Max extra words from description to add to search query (keeps API queries focused)
SEARCH_CONTEXT_WORDS = 5


def _search_query_from_context(name: str, description: str) -> str:
    """
    Build a search query focused on the headline/context we're tracking.
    Uses name + first few meaningful words from description so results bias toward that topic.
    """
    if not description or not description.strip():
        return name.strip()
    # Take first N words, drop very short/noise words
    stop = {"a", "an", "the", "of", "for", "in", "on", "to", "is", "and", "or", "by"}
    words = [w for w in description.strip().split() if len(w) > 1 and w.lower() not in stop][:SEARCH_CONTEXT_WORDS]
    if not words:
        return name.strip()
    return f"{name.strip()} {' '.join(words)}".strip()


def search_hacker_news(query: str) -> str:
    """Fetch recent HN comments for the query. Returns combined text or empty string on error."""
    yesterday_timestamp = int(time.time()) - (24 * 3600)
    url = f"https://hn.algolia.com/api/v1/search_by_date?query={query}&tags=comment&numericFilters=created_at_i>{yesterday_timestamp}"
    try:
        response = requests.get(url, timeout=HTTP_TIMEOUT_SEC)
        response.raise_for_status()
        hits = response.json().get("hits", [])[:HN_SEARCH_LIMIT]
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
    url = f"https://www.reddit.com/search.json?q={formatted_query}&sort=new&limit={REDDIT_SEARCH_LIMIT}&t=day"
    headers = {"User-Agent": "ProductSentimentEngine/5.0"}
    try:
        response = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT_SEC)
        if response.status_code != 200:
            logger.warning("Reddit returned %s for %s", response.status_code, query)
            return ""
        children = response.json().get("data", {}).get("children", [])
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


def get_embedding(text: str) -> list:
    """Converts text into an embedding vector. Raises on API or format error."""
    import google.generativeai as genai
    model_name = get_embedding_model_name()
    result = genai.embed_content(
        model=model_name,
        content=text,
        task_type="semantic_similarity",
    )
    if not result or "embedding" not in result:
        raise ValueError("Embedding API did not return an 'embedding' field")
    return result["embedding"]


def _parse_ai_sentiment_line(line: str) -> Optional[dict]:
    """
    Parse AI response line: PROS: ... | CONS: ... | QUOTES: ... | URL: ...
    Returns dict with pros, cons, verbatim_quotes, source_url or None.
    """
    line = line.strip().replace("\n", " ")
    if "PROS:" not in line or "CONS:" not in line or "QUOTES:" not in line or "URL:" not in line:
        return None
    parts = [p.strip() for p in line.split("|", 3)]
    if len(parts) < 4:
        return None
    return {
        "pros": parts[0].replace("PROS:", "").strip(),
        "cons": parts[1].replace("CONS:", "").strip(),
        "verbatim_quotes": parts[2].replace("QUOTES:", "").strip(),
        "source_url": parts[3].replace("URL:", "").strip(),
    }


def run_tracker() -> None:
    """For each tracking target and each of its events, fetch chatter, vector-filter, extract sentiment, and save if net-new."""
    logger.info("Starting the V5 Enterprise Vector Engine (per-event)...\n")
    supabase = get_supabase()
    targets_result = supabase.table("targets").select("*").eq("status", "tracking").execute()
    targets = getattr(targets_result, "data", None) or []
    if not targets:
        return

    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    model = get_model()

    for t in targets:
        name = t.get("name")
        t_id = t.get("id")
        if name is None or t_id is None:
            logger.warning("Skipping target with missing name or id: %s", t)
            continue

        # Load events for this target; if none (legacy), use one virtual event from target.description
        events_resp = supabase.table("events").select("*").eq("target_id", t_id).order("created_at", desc=True).execute()
        events_list = getattr(events_resp, "data", None) or []
        if not events_list:
            events_list = [{"id": None, "headline": (t.get("description") or "").strip() or "(general)"}]

        for event in events_list:
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

            search_query = _search_query_from_context(name, headline)
            logger.info("📡 Fetching intelligence for: %s | Event: %s (query: %s)...", name, headline[:50], search_query)
            hn_data = search_hacker_news(search_query)
            reddit_data = search_reddit(search_query)

            combined_chatter = ""
            if hn_data:
                combined_chatter += f"[SOURCE: Hacker News] {hn_data} "
            if reddit_data:
                combined_chatter += f"[SOURCE: Reddit] {reddit_data}"

            if not combined_chatter.strip():
                logger.info("   -> No fresh chatter for this event.")
                if REQUEST_DELAY_BETWEEN_TARGETS_SEC > 0:
                    time.sleep(REQUEST_DELAY_BETWEEN_TARGETS_SEC)
                continue

            try:
                chatter_vector = get_embedding(combined_chatter)
            except Exception as e:
                logger.warning("   ⚠️ Embedding API Error for %s: %s", name, e)
                if REQUEST_DELAY_BETWEEN_TARGETS_SEC > 0:
                    time.sleep(REQUEST_DELAY_BETWEEN_TARGETS_SEC)
                continue

            rpc_params = {
                "query_embedding": chatter_vector,
                "match_threshold": MATCH_THRESHOLD,
                "p_target_id": t_id,
            }
            if event_id is not None:
                rpc_params["p_event_id"] = event_id
            match_response = supabase.rpc("match_sentiment", rpc_params).execute()

            match_data = getattr(match_response, "data", None)
            if match_data and len(match_data) > 0:
                first = match_data[0]
                similarity = first.get("similarity", 0)
                logger.info("   🛑 Vector Match (Score: %.2f): %s [%s] redundant. Discarding.", similarity, name, headline[:40])
                if REQUEST_DELAY_BETWEEN_TARGETS_SEC > 0:
                    time.sleep(REQUEST_DELAY_BETWEEN_TARGETS_SEC)
                continue

            tracking_context = headline
            prompt = f"""
        You are a Principal Market Intelligence Analyst.
        We are tracking this target in the context of: "{tracking_context}".
        Focus your analysis on market sentiment related to THIS specific topic. Prioritize pros, cons, and quotes that speak to this context. If the chatter mentions other themes about {name}, note them only briefly; the main output must be intelligence about the tracking context above.

        Target: {name}
        Format EXACTLY like this (use | to separate):
        PROS: [summary] | CONS: [summary] | QUOTES: "[Quote]" | URL: [URL]

        Chatter data:
        {combined_chatter}
        """

            try:
                ai_response = model.generate_content(prompt)
                line = (ai_response.text or "").strip().replace("\n", " ")
                parsed = _parse_ai_sentiment_line(line)
                if parsed:
                    insert_row = {
                        "target_id": t_id,
                        "pros": parsed["pros"],
                        "cons": parsed["cons"],
                        "verbatim_quotes": parsed["verbatim_quotes"],
                        "source_url": parsed["source_url"],
                        "embedding": chatter_vector,
                    }
                    if event_id is not None:
                        insert_row["event_id"] = event_id
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
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    run_tracker()
