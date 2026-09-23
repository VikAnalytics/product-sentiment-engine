"""
Scout: gathers RSS articles, filters by NLP concepts, and extracts companies/products via AI into Supabase.

An event keeps the article it came from: headline is the publication's own title,
summary is the model's read of it, and published_at is when it was published.
The model decides which targets an article touches; it does not write the headline.
"""
import calendar
import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from typing import NamedTuple, Optional

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

DRY_RUN = os.getenv("SCOUT_DRY_RUN", "").strip() in ("1", "true", "True")

# Feeds occasionally serve years-old items (MarketWatch offered a 2024 Cadillac
# story in today's pull). Now that events carry publish time, an old article
# would create an event the tracker immediately skips as stale, so drop it here.
ARTICLE_MAX_AGE_DAYS = int(os.getenv("ARTICLE_MAX_AGE_DAYS", "14"))

# --- Name guards -----------------------------------------------------------
# Every name the model emits becomes a permanently tracked target, and the
# tracker then searches HN, Reddit and Google News for it daily. Four junk
# targets arrived in one run ("New Treadmills", "New Fitness Tracker",
# "Texture and Grain Controls", "Smart Circuit Breaker"), plus a COMPANY
# literally named "None". These guards apply to target *creation* only —
# an existing target still receives its event.

# What the model says when it means "nothing here".
JUNK_NAME_SENTINELS = {
    "none", "n/a", "na", "null", "unknown", "tbd", "various", "multiple",
    "multiple companies", "other", "others", "misc", "miscellaneous", "-",
}

# Head nouns that describe a category, not a product. Rejected only when the
# name carries no model number or distinctive token, so "Snapdragon 8 Elite
# Gen 6" and "Pixel Watch 3" survive while "New Fitness Tracker" does not.
GENERIC_PRODUCT_HEADS = {
    "app", "apps", "breaker", "breakers", "camera", "cameras", "car", "cars",
    "chip", "chips", "control", "controls", "device", "devices", "earbuds",
    "feature", "features", "headphones", "laptop", "laptops", "model", "models",
    "phone", "phones", "platform", "processor", "processors", "product",
    "service", "services", "software", "speaker", "speakers", "tablet",
    "tablets", "tool", "tools", "tracker", "trackers", "treadmill",
    "treadmills", "update", "updates", "vehicle", "vehicles", "watch", "watches",
}

# Countries, blocs and armed groups are not companies. Geopolitics belongs on a
# MACRO theme; before this guard the scout created COMPANY rows for Germany,
# Denmark, NATO and the Houthis. spaCy's NER is no help here — on a bare name it
# labels Verizon a GPE and misses the Houthis entirely — so the list is explicit.
# Comma-separated so multi-word names survive; splitting on whitespace would
# leave fragments like "emirates", which would then reject the airline.
_COUNTRIES = """
afghanistan, albania, algeria, angola, argentina, armenia, australia, austria,
azerbaijan, bahrain, bangladesh, belarus, belgium, bolivia, bosnia, botswana,
brazil, bulgaria, burkina faso, cambodia, cameroon, canada, chad, chile, china,
colombia, congo, costa rica, croatia, cuba, cyprus, czechia, czech republic,
denmark, dominican republic, ecuador, egypt, el salvador, estonia, ethiopia,
finland, france, gabon, georgia, germany, ghana, greece, guatemala, guinea,
haiti, honduras, hungary, iceland, india, indonesia, iran, iraq, ireland,
israel, italy, ivory coast, jamaica, japan, jordan, kazakhstan, kenya, kosovo,
kuwait, kyrgyzstan, laos, latvia, lebanon, libya, lithuania, luxembourg,
madagascar, malaysia, mali, malta, mexico, moldova, mongolia, montenegro,
morocco, mozambique, myanmar, namibia, nepal, netherlands, new zealand,
nicaragua, niger, nigeria, north korea, north macedonia, norway, oman,
pakistan, palestine, panama, papua new guinea, paraguay, peru, philippines,
poland, portugal, qatar, romania, russia, rwanda, saudi arabia, senegal,
serbia, singapore, slovakia, slovenia, somalia, south africa, south korea,
south sudan, spain, sri lanka, sudan, sweden, switzerland, syria, taiwan,
tajikistan, tanzania, thailand, tunisia, turkey, turkmenistan, uganda, ukraine,
united arab emirates, united kingdom, united states, uruguay, uzbekistan,
venezuela, vietnam, yemen, zambia, zimbabwe,
uk, usa, us, u.s., u.s.a., eu, uae, britain, great britain, america, holland
"""
_BLOCS_AND_GROUPS = """
nato, european union, united nations, opec, opec+, brics, g7, g20, wto, imf,
world bank, asean, african union, mercosur, commonwealth,
hamas, hezbollah, houthis, taliban, isis, islamic state, al-qaeda, wagner group,
white house, kremlin, pentagon, congress, parliament, european commission,
federal reserve, ecb, european central bank, bank of england, bank of japan
"""
NON_COMPANY_NAMES = frozenset(
    entry.strip()
    for block in (_COUNTRIES, _BLOCS_AND_GROUPS)
    for entry in block.replace("\n", " ").split(",")
    if entry.strip()
)


def _is_junk_name(name: str, target_type: str, macro_themes=None) -> Optional[str]:
    """
    Return a reason to refuse creating a target with this name, or None to allow it.

    Only consulted before a *new* target is created. Existing targets keep
    receiving events regardless, so a rule tightened later cannot orphan them.
    """
    cleaned = (name or "").strip()
    if not cleaned:
        return "empty name"
    lowered = cleaned.lower()
    if lowered in JUNK_NAME_SENTINELS:
        return "sentinel value, not a name"
    if not any(ch.isalnum() for ch in cleaned):
        return "punctuation, not a name"
    # No minimum length: X is a company.

    if target_type == "COMPANY":
        if lowered in NON_COMPANY_NAMES:
            return "country, bloc or armed group — belongs on a MACRO theme"
        for theme in (macro_themes or []):
            if lowered == theme.strip().lower():
                return f"matches seeded MACRO theme '{theme}'"

    if target_type == "PRODUCT":
        if lowered.startswith("new "):
            return "starts with 'New' — a description, not a product name"
        words = re.findall(r"[\w.\-]+", lowered)
        if words and words[-1] in GENERIC_PRODUCT_HEADS:
            # A model number or version makes it specific enough to keep.
            if not any(any(ch.isdigit() for ch in w) for w in words):
                return f"generic category name ending in '{words[-1]}'"
    return None


_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "its", "his", "her",
    "their", "have", "has", "been", "will", "would", "could", "should", "may", "are",
    "was", "were", "new", "says", "said", "after", "over", "amid", "about", "more",
    "than", "they", "them", "what", "when", "which", "while", "also", "some", "such",
}


def _content_words(text: str) -> set:
    """Lowercased words worth matching on: 4+ characters, not stopwords."""
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower())
            if len(w) >= 4 and w not in _STOPWORDS}


def _parse_published(iso: str) -> Optional[datetime]:
    """Parse the ISO string produced by _entry_published_at."""
    try:
        return datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return None


def _cites_its_article(target_type: str, name: str, description: str, article: dict) -> bool:
    """
    Does this line plausibly come from the article it cites?

    Across a 160-article batch the model's numbering drifts, and a wrong number
    would staple a real headline onto an unrelated summary — "Bose returns with
    new open earbuds" filed under a sentence about electric vehicles. A line that
    fails this check keeps its summary and loses only the source link.
    """
    haystack = f"{article.get('title', '')} {article.get('summary', '')}".lower()
    if not haystack.strip():
        return False
    if target_type in ("COMPANY", "PRODUCT"):
        # The article should name the company or product it is about.
        tokens = [t for t in re.findall(r"[a-z0-9]+", (name or "").lower()) if len(t) > 2]
        return any(t in haystack for t in tokens) if tokens else False
    # MACRO themes are interpretive, so match the model's own words instead.
    # Compare on 5-character stems so "Iran" matches "Iranian".
    stems = {w[:5] for w in _content_words(haystack)}
    return sum(1 for w in _content_words(description) if w[:5] in stems) >= 2


def _strip_parent_possessive(name: str, parent: str) -> str:
    """
    "Qualcomm's Snapdragon 8 Elite Gen 6" -> "Snapdragon 8 Elite Gen 6".

    The model often writes the product as the company owns it, which creates a
    second target beside the plain name. Only the possessive form is stripped —
    "Apple Watch" keeps its company word, because "Watch" alone is not a product.
    """
    if not parent or not name:
        return name
    low, par = name.lower(), parent.lower().strip()
    for possessive in ("'s ", "\u2019s "):
        prefix = par + possessive
        if low.startswith(prefix):
            stripped = name[len(prefix):].strip()
            if stripped and not _is_junk_name(stripped, "PRODUCT"):
                return stripped
    return name


def _entry_published_at(entry) -> Optional[str]:
    """
    Publish time of an RSS entry as an ISO-8601 UTC string, or None if the feed
    omits it. feedparser hands back a UTC struct_time, which calendar.timegm
    reads as UTC — time.mktime would silently apply the local offset.
    """
    for attr in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, attr, None)
        if parsed:
            try:
                ts = calendar.timegm(parsed)
                return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
            except (TypeError, ValueError, OverflowError):
                continue
    return None


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


# Set False the first time the DB rejects the post-023 columns, so a database
# without the migration still collects events instead of losing the whole run.
_EVENT_COLUMNS_OK = True


def _event_row(target_id: int, article: Optional[dict], description: str) -> dict:
    """
    Build an events row. headline is the publication's headline; the model's
    read of it goes to summary. Articles reach here from run_scout; callers
    without one (legacy paths, tests) fall back to the description.
    """
    description = (description or "").strip()
    title = ((article or {}).get("title") or "").strip()
    row = {
        "target_id": target_id,
        "headline": title or description,
        "summary": description or None,
        "source_title": title or None,
        "source_url": (article or {}).get("url") or None,
    }
    published_at = (article or {}).get("published_at")
    if published_at:
        row["published_at"] = published_at
    return row


def _insert_event(supabase, row: dict) -> bool:
    """Insert an event, degrading to the pre-023 column set if the migration is missing."""
    global _EVENT_COLUMNS_OK
    if DRY_RUN:
        logger.info("   [dry-run] would insert event: %s", {k: v for k, v in row.items() if v is not None})
        return True
    if _EVENT_COLUMNS_OK:
        try:
            supabase.table("events").insert(row).execute()
            return True
        except Exception as e:
            message = str(e)
            if "column" not in message.lower() and "PGRST204" not in message:
                raise
            _EVENT_COLUMNS_OK = False
            logger.warning(
                "events is missing the migration 023 columns (%s). Writing headline only "
                "until it is applied; source_url, summary and published_at are dropped.",
                message[:120],
            )
    supabase.table("events").insert({"target_id": row["target_id"], "headline": row["headline"]}).execute()
    return True


def _existing_event_id(supabase, target_id: int, row: dict) -> Optional[int]:
    """
    Has this story already been filed against this target?

    Keyed on source_url, because the model's summary is worded differently every
    run — which is exactly why matching on it let the same story back in daily.
    Falls back to the headline when a feed gives no link.
    """
    source_url = row.get("source_url")
    if source_url and _EVENT_COLUMNS_OK:
        try:
            found = (
                supabase.table("events").select("id")
                .eq("target_id", target_id).eq("source_url", source_url)
                .limit(1).execute().data or []
            )
            if found:
                return found[0]["id"]
        except Exception:
            pass  # pre-023 database: fall through to the headline check
    found = (
        supabase.table("events").select("id")
        .eq("target_id", target_id).eq("headline", row["headline"])
        .limit(1).execute().data or []
    )
    return found[0]["id"] if found else None


def _save_macro_event(name: str, description: str, article: Optional[dict] = None) -> None:
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
        row = _event_row(target_id, article, description)
        if not row["headline"]:
            return
        if _existing_event_id(supabase, target_id, row):
            logger.info("   -> [MACRO] %s already has this story. Skipping.", name)
            return
        _insert_event(supabase, row)
        logger.info("   🌐 New event for [MACRO] %s: %s", name, row["headline"][:60])
    except Exception as e:
        logger.exception("Database error for MACRO %s", name)
        logger.error("   ❌ Database Error for MACRO %s: %s", name, e)


def save_target_to_db(
    target_type: str,
    name: str,
    description: str,
    parent_company_name: str = "",
    article: Optional[dict] = None,
    macro_themes=None,
) -> str:
    """
    Save the extracted company, product or macro-theme event to Supabase.

    Returns what happened — "event", "target", "duplicate", "rejected" or
    "error" — so run_scout can report it rather than guess.
    """
    target_type = target_type.strip().upper()
    name = name.strip()
    if target_type == "MACRO":
        _save_macro_event(name, description, article)
        return "event"
    if target_type not in ("COMPANY", "PRODUCT"):
        return "rejected"
    if target_type == "PRODUCT":
        name = _strip_parent_possessive(name, parent_company_name)

    supabase = get_supabase()
    try:
        existing = supabase.table("targets").select("*").eq("name", name).execute()
        data_list = getattr(existing, "data", None)

        if data_list and len(data_list) > 0:
            # Exact name match: add event to existing target
            target_id = data_list[0].get("id")
            # Also backfill parent_target_id if not yet set
            if target_type == "PRODUCT" and parent_company_name and not data_list[0].get("parent_target_id"):
                parent_id = _resolve_parent_id(supabase, parent_company_name)
                if parent_id and not DRY_RUN:
                    supabase.table("targets").update({"parent_target_id": parent_id}).eq("id", target_id).execute()
                    logger.info("   🔗 Linked %s → %s", name, parent_company_name)
            row = _event_row(target_id, article, description)
            if not target_id or not row["headline"]:
                logger.info("   -> [%s] %s is already in the database. Skipping.", target_type, name)
                return "duplicate"
            if _existing_event_id(supabase, target_id, row):
                logger.info("   -> [%s] %s already has this story. Skipping.", target_type, name)
                return "duplicate"
            _insert_event(supabase, row)
            logger.info("   📌 New event for [%s] %s: %s", target_type, name, row["headline"][:60])
            return "event"

        # No exact match: check normalized name to avoid "M4 iPad Air" vs "iPad Air M4"
        # duplicates, and "Meta Platforms" arriving alongside "Meta".
        same_type_list = fetch_all_rows(
            lambda: supabase.table("targets").select("id, name").eq("target_type", target_type).order("id")
        )
        norm_new = normalize_target_name(name)
        for t in same_type_list:
            if normalize_target_name(t.get("name") or "") == norm_new:
                target_id = t.get("id")
                row = _event_row(target_id, article, description)
                if target_id and row["headline"]:
                    if _existing_event_id(supabase, target_id, row):
                        return "duplicate"
                    _insert_event(supabase, row)
                    logger.info("   📌 New event for [%s] %s (matched normalized %s): %s",
                                target_type, t.get("name"), name, row["headline"][:60])
                    return "event"
                logger.info("   -> [%s] %s matches existing %s. Skipping new target.", target_type, name, t.get("name"))
                return "duplicate"

        # Nothing matched, so this would create a permanently tracked target.
        # That is the expensive decision — the tracker will search for this name
        # every day — so it is the one place the guards apply.
        reason = _is_junk_name(name, target_type, macro_themes)
        if reason:
            logger.info("   🚫 Refused new %s target '%s': %s", target_type, name, reason)
            return "rejected"

        # New target: insert target then one event. Only companies get domain/logo; products do not.
        row = {
            "name": name,
            "target_type": target_type,
            "description": (description or "").strip(),
            "status": "tracking",
        }
        if DRY_RUN:
            logger.info("   [dry-run] would create %s target '%s' + event: %s",
                        target_type, name, ((article or {}).get("title") or description)[:70])
            return "target"
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
        event_row = _event_row(target_id, article, description) if target_id else None
        if event_row and event_row["headline"]:
            _insert_event(supabase, event_row)
        logger.info("   💾 SAVED: [%s] %s (event: %s)", target_type, name,
                    event_row["headline"][:50] if event_row else "")
        return "target"
    except Exception as e:
        logger.exception("Database error for %s", name)
        logger.error("   ❌ Database Error for %s: %s", name, e)
        return "error"


class Extraction(NamedTuple):
    """One line of AI output: which target an article touches, and why."""
    target_type: str
    name: str
    description: str
    parent_company: str
    article_idx: Optional[int]


def _parse_ai_extraction_line(line: str) -> Optional[Extraction]:
    """
    Parse a single line of AI output. Current format carries the article number,
    so the event can keep the headline, link and publish time of its source:
      COMPANY | 3 | Name | Description
      PRODUCT | 3 | Name | Description | Parent Company (or NONE)
      MACRO   | 3 | Theme Name | Description

    The older numberless format is still accepted, since a model occasionally
    drops the number and the line is worth keeping without provenance:
      COMPANY | Name | Description

    Returns an Extraction, or None if the line is not a usable extraction.
    """
    line = line.strip()
    if "|" not in line:
        return None
    parts = [p.strip() for p in line.split("|")]
    if len(parts) < 3:
        return None
    target_type = parts[0].upper()
    if target_type not in ("COMPANY", "PRODUCT", "MACRO"):
        return None

    article_idx = None
    if len(parts) >= 4 and re.fullmatch(r"\[?\d{1,4}\]?", parts[1]):
        article_idx = int(parts[1].strip("[]"))
        parts = [parts[0]] + parts[2:]
        if len(parts) < 3:
            return None

    name = parts[1]
    description = parts[2]
    parent_company = parts[3] if len(parts) > 3 else ""
    if not name:
        return None
    return Extraction(target_type, name, description, parent_company, article_idx)


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
    articles = []
    stale_before = datetime.now(timezone.utc) - timedelta(days=ARTICLE_MAX_AGE_DAYS)
    metrics = {
        "feeds": len(RSS_FEEDS), "feeds_with_entries": 0, "feeds_failed": 0,
        "articles_seen": 0, "articles_relevant": 0, "lines_parsed": 0, "ai_error": False,
        "silent_feeds": [], "events_written": 0, "targets_created": 0,
        "duplicates_skipped": 0, "names_rejected": 0, "lines_unsourced": 0,
        "articles_dated": 0, "articles_stale": 0, "lines_mismatched": 0,
        "extraction_retried": False,
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
                title = (getattr(entry, "title", "") or "").strip()
                summary = (entry.get("summary", "") or "").strip()
                if not title or not passes_filter(title + " " + summary):
                    continue
                published_at = _entry_published_at(entry)
                if published_at:
                    metrics["articles_dated"] += 1
                    published_dt = _parse_published(published_at)
                    if published_dt and published_dt < stale_before:
                        metrics["articles_stale"] += 1
                        continue
                articles.append({
                    "idx": len(articles) + 1,
                    "title": title,
                    "url": (getattr(entry, "link", "") or "").strip() or None,
                    "published_at": published_at,
                    "summary": summary,
                })
        except Exception as e:
            logger.warning("Could not read %s: %s", feed_url, e)
            metrics["feeds_failed"] += 1
            metrics["silent_feeds"].append(urlparse(feed_url).netloc or feed_url[:60])

    metrics["articles_relevant"] = len(articles)
    if not articles:
        logger.info("No market-moving articles found today.")
        return metrics

    logger.info(
        "Filtered raw articles down to %d highly relevant ones. Sending ONE batch request to the AI...\n",
        len(articles),
    )
    by_idx = {a["idx"]: a for a in articles}
    # Numbered so each extracted line can point back at the article it came from.
    batch_text = "\n---\n".join(
        f"[{a['idx']}] Title: {a['title']}\nSummary: {a['summary']}\n" for a in articles
    )

    macro_themes = _fetch_macro_theme_names()
    macro_list = "\n".join(f"  - {t}" for t in macro_themes) if macro_themes else "  (none seeded)"

    prompt = f"""
    You are an expert market and geopolitics analyst. Read the following batch of numbered news articles.
    Extract EVERY COMPANY event, EVERY new PRODUCT launch, AND attach relevant MACRO themes.

    Rules:
    1. One article can produce MULTIPLE lines — extract every affected company, product, and macro theme.
    2. Work through the articles in order and put each article's lines together.
       Every line MUST carry the number of the article it summarises, so the event
       keeps its source. A line whose summary does not match its number is discarded.
    3. FAN OUT geopolitics news to ALL plausibly-affected public companies.
       Example: "US expands chip export ban to China" → emit COMPANY lines for NVIDIA, AMD, TSMC, ASML, Intel, Applied Materials, AND a MACRO line for "Semiconductor Export Controls".
       Example: "OPEC cuts production 2M bpd" → COMPANY lines for ExxonMobil, Chevron, Delta Air Lines, United Airlines, AND a MACRO line for "OPEC & Energy Policy".
    4. MACRO themes MUST match one of these seeded names EXACTLY (or omit — do not invent new themes):
{macro_list}
    5. Format your response with one entity per line, using '|' as separator:
       COMPANY | [article number] | [Company Name] | [1-sentence summary of the event for this company]
       PRODUCT | [article number] | [Product Name] | [1-sentence summary of launch] | [Parent Company Name or NONE]
       MACRO   | [article number] | [Exact theme name from the list above] | [1-sentence summary of the geopolitical/policy event]

    6. For PRODUCT lines, always include the parent company name as the last field.
    7. Never emit a country, government, central bank, military alliance or armed group as a COMPANY
       (Germany, NATO, the Houthis, the Federal Reserve). That news belongs on a MACRO theme,
       plus COMPANY lines for the listed businesses it affects.
    8. Give a product its own name, not the company's: "Snapdragon 8 Elite Gen 6",
       never "Qualcomm's Snapdragon 8 Elite Gen 6".
    9. Only emit a PRODUCT line when the article names a specific branded product
       ("Snapdragon 8 Elite Gen 6", "Cadillac Vistiq"). Never invent one from a description:
       "a new fitness tracker" or "redesigned treadmills" is not a product name. Do not split one
       launch into several PRODUCT lines unless the article names several distinct products.
    10. A MACRO line needs a concrete event — a decision, announcement or escalation — not a topic.
       Skip the theme rather than writing "ongoing discussions continue".
    11. Use the company's common name ("Meta", not "Meta Platforms Inc").
    12. Do not include conversational text, headers, or markdown fences. Do not use '|' inside a summary.
    13. If absolutely nothing is found, output NONE.

    Articles:
    {batch_text}
    """

    try:
        model = get_model()
        raw_text = ""
        for attempt in (1, 2):
            raw_text = (model.generate_content(prompt).text or "").strip()
            if raw_text and raw_text.upper() != "NONE":
                break
            # A bare NONE across a full batch of market-moving articles is a bad
            # response, not a quiet news day, and it silently costs a whole run.
            if attempt == 1 and len(articles) >= 10:
                logger.warning("Extraction returned %r for %d relevant articles — retrying once.",
                               raw_text[:20], len(articles))
                metrics["extraction_retried"] = True
        if not raw_text or raw_text.upper() == "NONE":
            logger.info("AI found no entities to extract.")
            return metrics
        outcomes = {"event": "events_written", "target": "targets_created",
                    "duplicate": "duplicates_skipped", "rejected": "names_rejected"}
        for line in raw_text.split("\n"):
            parsed = _parse_ai_extraction_line(line)
            if not parsed:
                continue
            metrics["lines_parsed"] += 1
            article = by_idx.get(parsed.article_idx) if parsed.article_idx else None
            if article is not None and not _cites_its_article(
                parsed.target_type, parsed.name, parsed.description, article
            ):
                logger.debug("   ↯ %s %r cites article %s but does not match it; dropping the link.",
                             parsed.target_type, parsed.name, parsed.article_idx)
                metrics["lines_mismatched"] += 1
                article = None
            if article is None:
                # No usable number: keep the line, but it has no headline or link
                # of its own and falls back to the model's summary.
                metrics["lines_unsourced"] += 1
            outcome = save_target_to_db(
                parsed.target_type, parsed.name, parsed.description,
                parsed.parent_company, article=article, macro_themes=macro_themes,
            )
            key = outcomes.get(outcome)
            if key:
                metrics[key] += 1
            if outcome == "target":
                metrics["events_written"] += 1  # a new target arrives with its first event
        logger.info(
            "✅ Scout completed. %d events, %d new targets, %d duplicates skipped, %d names refused.",
            metrics["events_written"], metrics["targets_created"],
            metrics["duplicates_skipped"], metrics["names_rejected"],
        )
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
        # Events without an article number fall back to the model's summary as the
        # headline, which is what this change exists to stop.
        s.check(m["lines_parsed"] > 0 and m["lines_unsourced"] / max(1, m["lines_parsed"]) > 0.25,
                f"{m['lines_unsourced']} of {m['lines_parsed']} extracted lines cited no article")
        # A feed that stops publishing dates sends every event back to ingest time.
        s.check(m["articles_relevant"] > 0 and m["articles_dated"] == 0,
                "no article carried a publish date; events fall back to ingest time")
