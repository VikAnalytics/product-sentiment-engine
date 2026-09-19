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
from urllib.parse import urlparse
import spacy

from config import get_supabase, get_model, fetch_all_rows, ARTICLES_PER_FEED, HTTP_USER_AGENT
from domain_resolver import resolve_domain
from normalize import normalize_target_name

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
    # Product / company events
    "launch", "announce", "release", "unveil", "beta", "debut",
    "acquire", "merge", "buy", "sell", "earn", "revenue", "profit",
    "layoff", "fire", "resign", "hire", "depart",
    "sue", "settle", "fine", "probe", "ban", "block",
    "partner", "collaborate", "expand", "halt", "delay",
    # Earnings / analyst signals
    "beat", "miss", "guidance", "forecast", "outlook", "quarter",
    "quarterly", "downgrade", "upgrade", "cut", "raise", "lower",
    # M&A / corporate actions
    "takeover", "buyout", "spin", "spinoff", "ipo", "delist", "privatize",
    "tender", "offer", "stake", "divest", "restructure", "bankruptcy",
    # Regulatory / legal
    "approve", "reject", "appeal", "ruling", "verdict", "penalty",
    "recall", "investigate", "subpoena", "antitrust", "sanction",
    "regulate", "compliance", "violation", "enforcement",
    # Macro / market signals
    "tariff", "inflation", "rate", "interest", "recession", "gdp",
    "supply", "shortage", "demand", "inventory", "margin",
    # Management / strategy
    "ceo", "cfo", "cto", "chairman", "appoint", "replace", "succession",
    "strategy", "pivot", "restructure", "reorganize",
    # Geopolitics — conflict / security
    "war", "invasion", "invade", "conflict", "ceasefire", "armistice",
    "strike", "missile", "drone", "nuclear", "escalate", "escalation",
    "retaliate", "retaliation", "truce", "hostage", "refugee",
    # Geopolitics — trade / policy
    "embargo", "export-control", "protectionism", "reshore", "reshoring",
    "onshore", "chip-ban", "tech-ban", "decouple", "decoupling",
    "nearshore", "subsidy", "stimulus",
    # Geopolitics — blocs / orgs
    "nato", "brics", "opec", "eu", "un", "wto", "g7", "g20", "asean",
    # Geopolitics — diplomacy / actors
    "summit", "treaty", "accord", "alliance", "diplomat", "envoy",
    "election", "coup", "regime", "dictator", "president", "premier",
    "prime-minister", "chancellor", "parliament", "congress",
    "espionage", "cyberattack", "cybersecurity", "infiltrate",
}

RSS_FEEDS = [
    # Tech news
    "https://techcrunch.com/feed/",
    "https://www.theverge.com/rss/index.xml",
    "https://www.wired.com/feed/rss",
    "https://www.engadget.com/rss.xml",
    "https://www.zdnet.com/news/rss.xml",
    # Financial / market news
    # Reuters retired its public RSS feeds, so reach its reporting through a
    # site-scoped Google News query instead. Same for AP further down.
    "https://news.google.com/rss/search?q=when:1d+site:reuters.com+business&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=when:1d+site:reuters.com+markets&hl=en-US&gl=US&ceid=US:en",
    "https://finance.yahoo.com/news/rssindex",
    "https://feeds.marketwatch.com/marketwatch/topstories/",
    "https://feeds.marketwatch.com/marketwatch/marketpulse/",
    "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "https://www.cnbc.com/id/10000664/device/rss/rss.html",
    # Analyst / investing commentary
    "https://www.benzinga.com/feed",
    "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
    "https://news.google.com/rss/search?q=when:1d+site:apnews.com+business&hl=en-US&gl=US&ceid=US:en",
    "https://fortune.com/feed/",
    "https://www.theguardian.com/uk/business/rss",
    # Regulatory / government
    "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&company=&dateb=&owner=include&count=40&output=atom",
    "https://www.ftc.gov/feeds/press-release.xml",
    "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/press-releases/rss.xml",
    # Geopolitics / global policy
    "https://news.google.com/rss/search?q=when:1d+site:reuters.com+world&hl=en-US&gl=US&ceid=US:en",
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://news.google.com/rss/search?q=when:1d+site:apnews.com+world&hl=en-US&gl=US&ceid=US:en",
    "https://www.aljazeera.com/xml/rss/all.xml",
    "https://www.politico.eu/feed/",
    "https://foreignpolicy.com/feed/",
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


def _resolve_parent_id(supabase, parent_company_name: str) -> Optional[int]:
    """Look up a company target by name and return its id, or None if not found."""
    if not parent_company_name or parent_company_name.upper() == "NONE":
        return None
    resp = supabase.table("targets").select("id").eq("target_type", "COMPANY").eq("name", parent_company_name).limit(1).execute()
    rows = getattr(resp, "data", None) or []
    if rows:
        return rows[0].get("id")
    # Fuzzy fallback: normalized name match
    all_companies = fetch_all_rows(
        lambda: supabase.table("targets").select("id, name").eq("target_type", "COMPANY").order("id")
    )
    norm_parent = normalize_target_name(parent_company_name)
    for c in all_companies:
        if normalize_target_name(c.get("name") or "") == norm_parent:
            return c.get("id")
    return None


def _save_macro_event(name: str, headline: str) -> None:
    """
    Append an event to an existing MACRO target. Never creates new MACRO rows —
    themes are seeded via scripts/seed_macro_targets.py so the AI can only
    attach news to known themes.
    """
    supabase = get_supabase()
    try:
        tgt = (
            supabase.table("targets")
            .select("id")
            .eq("target_type", "MACRO")
            .eq("name", name)
            .limit(1)
            .execute()
            .data
            or []
        )
        if not tgt:
            logger.info("   -> [MACRO] %s not in seeded themes. Skipping.", name)
            return
        target_id = tgt[0]["id"]
        headline = (headline or "").strip()
        if not headline:
            return
        dup = (
            supabase.table("events")
            .select("id")
            .eq("target_id", target_id)
            .eq("headline", headline)
            .execute()
            .data
            or []
        )
        if dup:
            logger.info("   -> [MACRO] %s already has event: \"%s\". Skipping.", name, headline[:50])
            return
        supabase.table("events").insert({"target_id": target_id, "headline": headline}).execute()
        logger.info("   🌐 New event for [MACRO] %s: %s", name, headline[:60])
    except Exception as e:
        logger.exception("Database error for MACRO %s", name)
        logger.error("   ❌ Database Error for MACRO %s: %s", name, e)


def save_target_to_db(target_type: str, name: str, description: str, parent_company_name: str = "") -> None:
    """Saves the extracted company, product, or macro-theme event to Supabase."""
    target_type = target_type.strip().upper()
    name = name.strip()
    if target_type == "MACRO":
        _save_macro_event(name, description)
        return
    if target_type not in ("COMPANY", "PRODUCT"):
        return

    supabase = get_supabase()
    try:
        new_headline = (description or "").strip()
        existing = supabase.table("targets").select("*").eq("name", name).execute()
        data_list = getattr(existing, "data", None)

        if data_list and len(data_list) > 0:
            # Exact name match: add event to existing target
            target_id = data_list[0].get("id")
            # Also backfill parent_target_id if not yet set
            if target_type == "PRODUCT" and parent_company_name and not data_list[0].get("parent_target_id"):
                parent_id = _resolve_parent_id(supabase, parent_company_name)
                if parent_id:
                    supabase.table("targets").update({"parent_target_id": parent_id}).eq("id", target_id).execute()
                    logger.info("   🔗 Linked %s → %s", name, parent_company_name)
            if not target_id or not new_headline:
                logger.info("   -> [%s] %s is already in the database. Skipping.", target_type, name)
                return
            events_resp = supabase.table("events").select("id").eq("target_id", target_id).eq("headline", new_headline).execute()
            events_data = getattr(events_resp, "data", None) or []
            if events_data:
                logger.info("   -> [%s] %s already has event: \"%s\". Skipping.", target_type, name, new_headline[:50])
                return
            supabase.table("events").insert({"target_id": target_id, "headline": new_headline}).execute()
            logger.info("   📌 New event for [%s] %s: %s", target_type, name, new_headline[:60])
            return

        # No exact match: check normalized name to avoid "M4 iPad Air" vs "iPad Air M4" duplicates
        same_type_list = fetch_all_rows(
            lambda: supabase.table("targets").select("id, name").eq("target_type", target_type).order("id")
        )
        norm_new = normalize_target_name(name)
        for t in same_type_list:
            if normalize_target_name(t.get("name") or "") == norm_new:
                target_id = t.get("id")
                if target_id and new_headline:
                    events_resp = supabase.table("events").select("id").eq("target_id", target_id).eq("headline", new_headline).execute()
                    if not (getattr(events_resp, "data", None) or []):
                        supabase.table("events").insert({"target_id": target_id, "headline": new_headline}).execute()
                        logger.info("   📌 New event for [%s] %s (matched normalized %s): %s", target_type, t.get("name"), name, new_headline[:60])
                else:
                    logger.info("   -> [%s] %s matches existing %s. Skipping new target.", target_type, name, t.get("name"))
                return

        # New target: insert target then one event. Only companies get domain/logo; products do not.
        row = {
            "name": name,
            "target_type": target_type,
            "description": new_headline,
            "status": "tracking",
        }
        if target_type == "COMPANY":
            domain = resolve_domain(name, target_type="company", use_ai=True)
            if domain:
                row["domain"] = domain
                row["logo_url"] = f"https://logo.clearbit.com/{domain}"
        if target_type == "PRODUCT" and parent_company_name:
            parent_id = _resolve_parent_id(supabase, parent_company_name)
            if parent_id:
                row["parent_target_id"] = parent_id
                logger.info("   🔗 Linking %s → %s (id=%d)", name, parent_company_name, parent_id)
        insert_result = supabase.table("targets").insert(row).execute()
        inserted = getattr(insert_result, "data", None)
        target_id = inserted[0].get("id") if inserted and len(inserted) > 0 else None
        if target_id and new_headline:
            supabase.table("events").insert({"target_id": target_id, "headline": new_headline}).execute()
        logger.info("   💾 SAVED: [%s] %s (event: %s)", target_type, name, new_headline[:50] if new_headline else "")
    except Exception as e:
        logger.exception("Database error for %s", name)
        logger.error("   ❌ Database Error for %s: %s", name, e)


def _parse_ai_extraction_line(line: str) -> Optional[Tuple[str, str, str, str]]:
    """
    Parse a single line of AI output.
      COMPANY | Name | Description
      PRODUCT | Name | Description | Parent Company (or NONE)
      MACRO   | Theme Name | Description
    Returns (target_type, name, description, parent_company) or None if invalid.
    """
    line = line.strip()
    if "|" not in line:
        return None
    parts = line.split("|", 3)
    if len(parts) < 3:
        return None
    target_type = parts[0].strip().upper()
    if target_type not in ("COMPANY", "PRODUCT", "MACRO"):
        return None
    name = parts[1].strip()
    description = parts[2].strip()
    parent_company = parts[3].strip() if len(parts) > 3 else ""
    if not name:
        return None
    return (target_type, name, description, parent_company)


def _fetch_macro_theme_names() -> list:
    """Load seeded MACRO theme names so the prompt can constrain output."""
    try:
        resp = (
            get_supabase()
            .table("targets")
            .select("name")
            .eq("target_type", "MACRO")
            .eq("status", "tracking")
            .execute()
        )
        return [r["name"] for r in (resp.data or [])]
    except Exception as e:
        logger.warning("Could not load MACRO themes: %s", e)
        return []


# sec.gov and ftc.gov reject feedparser's default agent outright, which is how
# four feeds came to return nothing without ever raising. The SEC additionally
# asks automated clients to identify themselves with a contact address.
SEC_USER_AGENT = "Market Intelligence Engine (contact: indivikrant@gmail.com)"


def _agent_for(feed_url: str) -> str:
    return SEC_USER_AGENT if "sec.gov" in feed_url else HTTP_USER_AGENT


def run_scout() -> dict:
    """
    Gather RSS articles, filter by concepts, then batch-extract targets via AI and save to DB.

    Returns a metrics dict for telemetry, including how many feeds actually
    yielded entries: a feed that quietly stops serving looks like slow news.
    """
    logger.info("Gathering articles from %d sources...\n", len(RSS_FEEDS))
    articles_to_analyze = []
    metrics = {
        "feeds": len(RSS_FEEDS), "feeds_with_entries": 0, "feeds_failed": 0,
        "articles_seen": 0, "articles_relevant": 0, "lines_parsed": 0, "ai_error": False,
        "silent_feeds": [],
    }

    for feed_url in RSS_FEEDS:
        try:
            logger.info("📡 Scanning: %s", feed_url)
            feed = feedparser.parse(feed_url, agent=_agent_for(feed_url))
            entries = getattr(feed, "entries", [])[:ARTICLES_PER_FEED]
            if entries:
                metrics["feeds_with_entries"] += 1
            else:
                # Name them: a feed that stops serving looks exactly like a quiet
                # news day unless you can see which one went silent.
                metrics["silent_feeds"].append(urlparse(feed_url).netloc or feed_url[:60])
            metrics["articles_seen"] += len(entries)
            for entry in entries:
                title = getattr(entry, "title", "") or ""
                summary = entry.get("summary", "") or ""
                if passes_filter(title + " " + summary):
                    articles_to_analyze.append(f"Title: {title}\nSummary: {summary}\n")
        except Exception as e:
            logger.warning("Could not read %s: %s", feed_url, e)
            metrics["feeds_failed"] += 1
            metrics["silent_feeds"].append(urlparse(feed_url).netloc or feed_url[:60])

    metrics["articles_relevant"] = len(articles_to_analyze)
    if not articles_to_analyze:
        logger.info("No market-moving articles found today.")
        return metrics

    logger.info(
        "Filtered raw articles down to %d highly relevant ones. Sending ONE batch request to the AI...\n",
        len(articles_to_analyze),
    )
    batch_text = "\n---\n".join(articles_to_analyze)

    macro_themes = _fetch_macro_theme_names()
    macro_list = "\n".join(f"  - {t}" for t in macro_themes) if macro_themes else "  (none seeded)"

    prompt = f"""
    You are an expert market and geopolitics analyst. Read the following batch of news articles.
    Extract EVERY COMPANY event, EVERY new PRODUCT launch, AND attach relevant MACRO themes.

    Rules:
    1. One article can produce MULTIPLE lines — extract every affected company, product, and macro theme.
    2. FAN OUT geopolitics news to ALL plausibly-affected public companies.
       Example: "US expands chip export ban to China" → emit COMPANY lines for NVIDIA, AMD, TSMC, ASML, Intel, Applied Materials, AND a MACRO line for "Semiconductor Export Controls".
       Example: "OPEC cuts production 2M bpd" → COMPANY lines for ExxonMobil, Chevron, Delta Air Lines, United Airlines, AND a MACRO line for "OPEC & Energy Policy".
    3. MACRO themes MUST match one of these seeded names EXACTLY (or omit — do not invent new themes):
{macro_list}
    4. Format your response with one entity per line, using '|' as separator:
       COMPANY | [Company Name] | [1-sentence summary of the event for this company]
       PRODUCT | [Product Name] | [1-sentence summary of launch] | [Parent Company Name or NONE]
       MACRO   | [Exact theme name from the list above] | [1-sentence summary of the geopolitical/policy event]

    5. For PRODUCT lines, always include the parent company name as the 4th field.
    6. Do not include conversational text, headers, or markdown fences.
    7. If absolutely nothing is found, output NONE.

    Articles:
    {batch_text}
    """

    try:
        model = get_model()
        response = model.generate_content(prompt)
        raw_text = (response.text or "").strip()
        if raw_text.upper() == "NONE":
            logger.info("AI found no entities to extract.")
            return metrics
        for line in raw_text.split("\n"):
            parsed = _parse_ai_extraction_line(line)
            if parsed:
                metrics["lines_parsed"] += 1
                save_target_to_db(parsed[0], parsed[1], parsed[2], parsed[3])
        logger.info("✅ Scout completed successfully.")
    except Exception as e:
        logger.error("⚠️ AI API Error (You might still be out of quota!): %s", e)
        metrics["ai_error"] = True

    return metrics


if __name__ == "__main__":
    from logging_setup import setup_logging
    from pipeline_telemetry import step

    setup_logging()
    logging.basicConfig(level=logging.INFO, format="%(message)s")  # no-op if handlers exist
    with step("scout") as s:
        m = run_scout()
        s.rows(m["lines_parsed"])
        s.note(**m)
        # Feeds rot silently: a dead one returns an empty list, not an error.
        s.check(m["feeds_with_entries"] == 0, "no RSS feed returned any entries")
        # All 26 feeds return entries as of this change, so a quarter going quiet
        # means rot rather than a slow news day. silent_feeds names which.
        s.check(m["feeds_with_entries"] / max(1, m["feeds"]) < 0.75,
                f"only {m['feeds_with_entries']} of {m['feeds']} feeds returned entries: "
                f"{', '.join(m['silent_feeds'][:6])}")
        s.check(m["ai_error"], "extraction call failed, no targets or events created")
        s.check(m["articles_relevant"] > 0 and m["lines_parsed"] == 0,
                "relevant articles found but nothing extracted from them")
