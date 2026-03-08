"""
Market Intelligence Engine — Executive Streamlit Dashboard.
Consumes targets, events, and sentiment from Supabase; uses config singleton for DB.

Run from project root:
  streamlit run src/app.py
Or with explicit Python path:
  PYTHONPATH=src streamlit run src/app.py
"""
import os
import re
import sys

# Ensure src is on path so "from config import ..." works when run as streamlit run src/app.py
_src_dir = os.path.dirname(os.path.abspath(__file__))
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

import streamlit as st
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import requests

from config import get_supabase

try:
    from postgrest.exceptions import APIError as PostgrestAPIError
except ImportError:
    PostgrestAPIError = None  # type: ignore[misc, assignment]

try:
    from streamlit_searchbox import st_searchbox
    _SEARCHBOX_AVAILABLE = True
except ImportError:
    _SEARCHBOX_AVAILABLE = False


# -----------------------------------------------------------------------------
# Page config (must be first Streamlit command)
# -----------------------------------------------------------------------------
st.set_page_config(
    layout="wide",
    page_title="Intelligence Dashboard",
    initial_sidebar_state="expanded",
)


# -----------------------------------------------------------------------------
# Minimal custom CSS: only for our hero card and avatar initials (no global overrides)
# -----------------------------------------------------------------------------
def _inject_custom_css() -> None:
    st.markdown(
        """
        <style>
        /* Hero initial circle when no logo */
        .hero-initial {
            width: 64px;
            height: 64px;
            border-radius: 10px;
            background: #0d9488;
            color: #fff;
            font-size: 24px;
            font-weight: 700;
            display: inline-flex;
            align-items: center;
            justify-content: center;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# -----------------------------------------------------------------------------
# Data fetching
# -----------------------------------------------------------------------------
def fetch_targets():
    """Fetch all targets for sidebar (id, name, type, parent). Selected target details from fetch_target_by_id."""
    supabase = get_supabase()
    resp = supabase.table("targets").select(
        "id, name, target_type, status, parent_target_id"
    ).execute()
    return getattr(resp, "data", None) or []


def fetch_target_by_id(target_id: int):
    """Fetch a single target by id; returns dict or None (includes logo_url)."""
    if target_id is None:
        return None
    supabase = get_supabase()
    resp = supabase.table("targets").select("*").eq("id", target_id).execute()
    data = getattr(resp, "data", None) or []
    return data[0] if data else None


def _target_initial(target: dict) -> str:
    """First letter of target name (or '?') for avatar placeholder."""
    name = (target.get("name") or "").strip()
    return (name[0].upper() if name else "?")[:1]


def _target_logo_url(target: dict) -> Optional[str]:
    """Logo URL if set and non-empty; else None."""
    url = (target.get("logo_url") or "").strip()
    return url if url else None


def _is_image_bytes(data: bytes) -> bool:
    """True if data looks like a PNG, JPEG, GIF, or SVG image."""
    if not data or len(data) < 4:
        return False
    # PNG, JPEG, GIF
    if data[:4] == b"\x89PNG" or data[:2] == b"\xff\xd8" or data[:6] in (b"GIF87a", b"GIF89a"):
        return True
    # SVG (text)
    if data[:5] == b"<?xml" or (data[:1] == b"<" and b"<svg" in data[:100].lower()):
        return True
    return False


def _load_logo_bytes(logo_url: str) -> Optional[bytes]:
    """Fetch logo image bytes server-side. Cached in session on success. Returns None on failure."""
    if not logo_url or not logo_url.startswith(("http://", "https://")):
        return None
    cache = st.session_state.setdefault("_logo_cache", {})
    if logo_url in cache and cache[logo_url] is not None:
        return cache[logo_url]
    try:
        r = requests.get(
            logo_url,
            timeout=8,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
            },
        )
        if not r.ok:
            return None
        data = r.content
        ct = (r.headers.get("content-type") or "").lower()
        if ct.startswith("image/") or _is_image_bytes(data):
            cache[logo_url] = data
            return data
    except Exception:
        pass
    return None


def _domain_from_logo_url(logo_url: str) -> Optional[str]:
    """Extract domain from Clearbit-style logo URL (e.g. https://logo.clearbit.com/apple.com -> apple.com)."""
    if not logo_url or "logo.clearbit.com/" not in logo_url:
        return None
    try:
        # URL might be https://logo.clearbit.com/apple.com or .../apple.com?size=64
        path = urlparse(logo_url).path or ""
        domain = path.strip("/").split("?")[0].strip()
        return domain if "." in domain else None
    except Exception:
        return None


def _google_favicon_url(domain: str, size: int = 128) -> str:
    """Google's favicon API - works without auth and returns a small logo/icon."""
    return f"https://www.google.com/s2/favicons?domain={domain}&sz={size}"


def _get_logo_bytes(logo_url: Optional[str], domain: Optional[str]) -> Optional[bytes]:
    """
    Get logo image bytes: try primary logo_url (e.g. Clearbit) first; if that fails, try Google favicon for domain.
    This way we can show real logos even when Clearbit blocks server-side requests.
    """
    if logo_url:
        data = _load_logo_bytes(logo_url)
        if data:
            return data
    if domain:
        fallback_url = _google_favicon_url(domain)
        data = _load_logo_bytes(fallback_url)
        if data:
            return data
    return None


def fetch_events_for_target(target_id: int):
    """Fetch events for target, ordered by created_at descending."""
    if target_id is None:
        return []
    supabase = get_supabase()
    resp = (
        supabase.table("events")
        .select("id, target_id, headline, created_at, cached_analysis, cached_analysis_at")
        .eq("target_id", target_id)
        .order("created_at", desc=True)
        .execute()
    )
    return getattr(resp, "data", None) or []


def fetch_sentiment_for_event(event_id: int):
    """Fetch all sentiment rows for an event (where event_id matches)."""
    if event_id is None:
        return []
    supabase = get_supabase()
    resp = (
        supabase.table("sentiment")
        .select("id, target_id, event_id, pros, cons, verbatim_quotes, source_url, created_at")
        .eq("event_id", event_id)
        .execute()
    )
    return getattr(resp, "data", None) or []


def fetch_sentiment_for_target_ungrouped(target_id: int):
    """Fetch sentiment rows for this target with no event (legacy or general target-level)."""
    if target_id is None:
        return []
    supabase = get_supabase()
    resp = (
        supabase.table("sentiment")
        .select("id, target_id, event_id, pros, cons, verbatim_quotes, source_url, created_at")
        .eq("target_id", target_id)
        .is_("event_id", None)
        .execute()
    )
    return getattr(resp, "data", None) or []


# -----------------------------------------------------------------------------
# Filter low-value / placeholder sentiment (so we don't show "None identified" noise)
# -----------------------------------------------------------------------------
_PLACEHOLDER_PHRASES = (
    "none identified", "no clear pros", "no clear cons", "not explicitly mentioned",
    "no verbatims", "no pros", "no cons", "none found", "n/a", "not mentioned",
    "comments refer to", "refer to \"", "no items recorded", "no verbatims for this source",
)


def _text_is_placeholder(text: str) -> bool:
    """True if text is empty or a known placeholder / no-signal phrase."""
    if not text or not isinstance(text, str):
        return True
    s = text.strip().lower()
    if not s:
        return True
    for p in _PLACEHOLDER_PHRASES:
        if p in s and len(s) < 120:
            return True
    return False


def filter_meaningful_sentiment(sentiments: list) -> list:
    """Keep only sentiment rows that have at least one of pros/cons/verbatim with real content."""
    out = []
    for s in sentiments:
        pros = (s.get("pros") or "").strip()
        cons = (s.get("cons") or "").strip()
        quotes = (s.get("verbatim_quotes") or "").strip()
        if _text_is_placeholder(pros) and _text_is_placeholder(cons) and _text_is_placeholder(quotes):
            continue
        out.append(s)
    return out


# -----------------------------------------------------------------------------
# Aggregate and dedupe sentiment (avoid repeating same points across sources)
# -----------------------------------------------------------------------------
def _normalize_for_dedupe(text: str) -> str:
    """Lowercase, strip punctuation, collapse spaces — for similarity check."""
    if not text:
        return ""
    s = (text or "").strip().lower()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _dedupe_lines(lines: list) -> list:
    """Drop duplicates and near-duplicates: keep longer when one is substring of other."""
    if not lines:
        return []
    # Sort by normalized length descending so we keep the most complete version first
    with_key = [(_normalize_for_dedupe(l), l) for l in lines if (l or "").strip()]
    with_key.sort(key=lambda x: len(x[0]), reverse=True)
    seen_keys = []
    result = []
    for key, original in with_key:
        if not key:
            continue
        # Skip if this key is contained in an already-kept key, or vice versa
        is_dup = False
        for sk in seen_keys:
            if key in sk or sk in key:
                is_dup = True
                break
        if is_dup:
            continue
        seen_keys.append(key)
        result.append(original.strip())
    return result


def aggregate_sentiment(sentiments: list) -> dict:
    """
    Merge many sentiment rows into one consolidated view with deduped pros/cons
    and combined voice-of-customer (quote + source link). Stops repetition across sources.
    """
    all_pros = []
    all_cons = []
    voice = []  # list of (quote_text, source_url)
    for s in sentiments:
        for line in _to_bullet_lines(s.get("pros") or ""):
            all_pros.append(line)
        for line in _to_bullet_lines(s.get("cons") or ""):
            all_cons.append(line)
        quotes = (s.get("verbatim_quotes") or "").strip()
        url = (s.get("source_url") or "").strip()
        if quotes and not _text_is_placeholder(quotes):
            for line in _to_bullet_lines(quotes):
                voice.append((line, url))
    # Dedupe voice by quote text (same quote from different sources → show once)
    voice_deduped = []
    seen_quote_key = set()
    for quote, url in voice:
        key = _normalize_for_dedupe(quote)
        if key and key not in seen_quote_key:
            seen_quote_key.add(key)
            voice_deduped.append((quote, url))
    return {
        "pros": _dedupe_lines(all_pros),
        "cons": _dedupe_lines(all_cons),
        "voice": voice_deduped,
    }


# -----------------------------------------------------------------------------
# Insight text parsing (multi-line / bullet-friendly)
# -----------------------------------------------------------------------------
def _to_bullet_lines(text: str):
    """Split insight text into list of non-empty lines for bullet display.
    Handles newlines, pipe, bullet chars, and long single-line text (sentence split)."""
    if not text or not isinstance(text, str):
        return []
    raw = text.strip()
    if not raw:
        return []
    # 1) Split by newline and " | " (AI-style separator)
    lines = []
    for part in raw.replace("\r\n", "\n").split("\n"):
        for sub in part.split(" | "):
            sub = sub.strip()
            for prefix in ("•", "-", "*", "–", "—"):
                if sub.startswith(prefix):
                    sub = sub.lstrip(prefix).strip()
            if sub and sub.lower() not in ("none", "n/a", "none found", "."):
                lines.append(sub)
    # 2) If we still have long one-liners (e.g. from DB with no newlines), split by sentences
    result = []
    for line in lines:
        if len(line) > 100 and ". " in line:
            # Sentence-style split so long one-liners become multiple bullets
            parts = []
            for sent in line.split(". "):
                sent = sent.strip()
                if not sent:
                    continue
                # Reattach common abbreviations to next part
                if parts and parts[-1].lower() in ("e.g", "i.e", "dr", "mr", "ms", "etc"):
                    parts[-1] = parts[-1] + ". " + sent + ("." if not sent.endswith(".") else "")
                elif len(sent) >= 20 or " " in sent:
                    parts.append(sent if sent.endswith(".") else sent + ".")
                else:
                    parts.append(sent)
            result.extend(parts)
        else:
            result.append(line)
    return result


def _render_insight_block(
    label: str,
    text: str,
    empty_placeholder: str = "_No items recorded._",
    as_blockquote: bool = False,
) -> None:
    """Render a section (Pros/Cons/VoC) with bullet list or blockquotes."""
    st.markdown(f"**{label}**")
    st.markdown("---")
    lines = _to_bullet_lines(text)
    if not lines:
        st.caption(empty_placeholder)
        return
    for line in lines:
        if as_blockquote:
            st.markdown(f"> {line}")
        else:
            st.markdown(f"- {line}")
    st.markdown("")


# -----------------------------------------------------------------------------
# Sidebar: navigation (Companies / Products)
# -----------------------------------------------------------------------------
def render_sidebar(targets: list, selected_target_id: Optional[int]) -> Optional[int]:
    """Render sidebar: Companies first; Products filtered by selected company. Returns selected target_id."""
    with st.sidebar:
        st.markdown("## Market Intelligence Engine")
        st.divider()

        companies = [t for t in targets if (t.get("target_type") or "").upper() == "COMPANY"]
        all_products = [t for t in targets if (t.get("target_type") or "").upper() == "PRODUCT"]

        if not companies and not all_products:
            st.caption("No targets yet. Add companies or products to get started.")
            st.divider()
            return None

        prev_company = st.session_state.get("_sidebar_company_id")
        prev_product = st.session_state.get("_sidebar_product_id")

        company_ids = [c["id"] for c in companies]
        c_idx = company_ids.index(selected_target_id) if selected_target_id in company_ids else 0
        # If current selection is a product, pre-select its parent company in the dropdown
        if selected_target_id and selected_target_id not in company_ids:
            for p in all_products:
                if p.get("id") == selected_target_id and p.get("parent_target_id") in company_ids:
                    if p["parent_target_id"] in company_ids:
                        c_idx = company_ids.index(p["parent_target_id"])
                    break

        new_company_id = None
        new_product_id = None

        def _company_options(searchterm: str):
            term = (searchterm or "").strip().lower()
            if not term:
                return [(c.get("name") or f"Target {c.get('id')}", c["id"]) for c in companies]
            return [(c.get("name") or f"Target {c.get('id')}", c["id"]) for c in companies if term in (c.get("name") or "").lower()]

        def _product_options(searchterm: str):
            term = (searchterm or "").strip().lower()
            if not term:
                return [(p.get("name") or f"Target {p.get('id')}", p["id"]) for p in products]
            return [(p.get("name") or f"Target {p.get('id')}", p["id"]) for p in products if term in (p.get("name") or "").lower()]

        # Products list depends on selected company (set below for searchbox path)
        products = all_products  # will overwrite when company selected
        new_company_id = prev_company
        new_product_id = prev_product

        with st.expander("**Companies**", expanded=bool(companies)):
            if companies:
                if _SEARCHBOX_AVAILABLE:
                    default_c = next((c for c in companies if c["id"] == selected_target_id), companies[0])
                    default_val = (default_c.get("name") or f"Target {default_c['id']}", default_c["id"]) if default_c else None
                    selected_c = st_searchbox(
                        _company_options,
                        key="sidebar_companies_search",
                        placeholder="Search and select company...",
                        default=default_val,
                        default_options=[(c.get("name") or f"Target {c['id']}", c["id"]) for c in companies],
                    )
                    if selected_c is not None:
                        new_company_id = selected_c[1] if isinstance(selected_c, (list, tuple)) and len(selected_c) >= 2 else selected_c
                    else:
                        new_company_id = selected_target_id if selected_target_id in company_ids else (companies[0]["id"] if companies else None)
                else:
                    c_labels = [c.get("name") or f"Target {c.get('id')}" for c in companies]
                    c_idx = company_ids.index(selected_target_id) if selected_target_id in company_ids else 0
                    sel_c = st.selectbox("Select company", range(len(c_labels)), format_func=lambda i: c_labels[i], index=c_idx, key="sidebar_companies")
                    new_company_id = company_ids[sel_c]
            else:
                st.caption("No companies yet.")

        if new_company_id is not None:
            products = [p for p in all_products if p.get("parent_target_id") == new_company_id]
        else:
            products = all_products
        product_ids = [p["id"] for p in products]

        with st.expander("**Products**", expanded=bool(products)):
            if products:
                if _SEARCHBOX_AVAILABLE:
                    default_p = next((p for p in products if p["id"] == selected_target_id), products[0] if products else None)
                    default_val = (default_p.get("name") or f"Target {default_p['id']}", default_p["id"]) if default_p else None
                    selected_p = st_searchbox(
                        _product_options,
                        key="sidebar_products_search",
                        placeholder="Search and select product...",
                        default=default_val,
                        default_options=[(p.get("name") or f"Target {p['id']}", p["id"]) for p in products],
                    )
                    if selected_p is not None:
                        new_product_id = selected_p[1] if isinstance(selected_p, (list, tuple)) and len(selected_p) >= 2 else selected_p
                    else:
                        new_product_id = selected_target_id if selected_target_id in product_ids else (products[0]["id"] if products else None)
                else:
                    p_labels = [p.get("name") or f"Target {p.get('id')}" for p in products]
                    p_idx = product_ids.index(selected_target_id) if selected_target_id in product_ids else 0
                    sel_p = st.selectbox("Select product", range(len(p_labels)), format_func=lambda i: p_labels[i], index=p_idx, key="sidebar_products")
                    new_product_id = product_ids[sel_p]
            else:
                if new_company_id is not None:
                    st.caption("No products linked to this company.")
                else:
                    st.caption("No products yet.")

        st.session_state["_sidebar_company_id"] = new_company_id
        st.session_state["_sidebar_product_id"] = new_product_id

        if new_company_id is not None and new_company_id != prev_company:
            choice_id = new_company_id
        elif new_product_id is not None and new_product_id != prev_product:
            choice_id = new_product_id
        elif selected_target_id is not None:
            choice_id = selected_target_id
        else:
            choice_id = new_company_id if new_company_id is not None else new_product_id

        st.divider()
        return choice_id


# -----------------------------------------------------------------------------
# Main: target overview (hero with logo/initial + description)
# -----------------------------------------------------------------------------
def render_target_overview(target: dict) -> None:
    """Render target as a hero card: logo or initial, name, description."""
    if not target:
        return
    name = target.get("name") or "Unnamed Target"
    description = target.get("description") or ""
    logo_url = _target_logo_url(target)
    initial = _target_initial(target)

    # Hero: try primary logo_url (Clearbit), then Google favicon by domain; else initial
    domain = target.get("domain") or (_domain_from_logo_url(logo_url) if logo_url else None)
    logo_bytes = _get_logo_bytes(logo_url, domain)
    col_logo, col_name = st.columns([0.12, 0.88])
    with col_logo:
        if logo_bytes:
            st.image(logo_bytes, width=64)
        else:
            st.markdown(f'<span class="hero-initial">{initial}</span>', unsafe_allow_html=True)
    with col_name:
        st.markdown(f"## {name}")
    if description:
        desc_escaped = description.replace("<", "&lt;").replace(">", "&gt;")
        st.markdown(f'<p style="margin-top:0.5rem; margin-bottom:1rem; color:#374151; line-height:1.6;">{desc_escaped}</p>', unsafe_allow_html=True)
    else:
        st.caption("No description.")
    st.divider()


# -----------------------------------------------------------------------------
# Timeline: events and sentiment (expanders, 3 columns)
# -----------------------------------------------------------------------------
def _source_label(url: str) -> str:
    """Derive a short label from URL for display (e.g. news.ycombinator.com)."""
    if not url:
        return "Source"
    url = url.strip()
    if not url.startswith("http"):
        return "Source"
    try:
        parsed = urlparse(url)
        netloc = (parsed.netloc or "").strip()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc or "Source"
    except Exception:
        return "Source"


def render_event_card(event: dict, sentiments: list) -> None:
    """Render one event as an expander with headline+date; inside, each sentiment as a card with 3 columns."""
    headline = (event.get("headline") or "").strip() or "Untitled event"
    created = event.get("created_at")
    if created:
        try:
            if isinstance(created, str) and "T" in created:
                dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            else:
                dt = created
            date_str = dt.strftime("%b %d, %Y") if hasattr(dt, "strftime") else str(created)
        except Exception:
            date_str = str(created)
    else:
        date_str = ""

    label = f"{headline} — {date_str}" if date_str else headline

    with st.expander(label, expanded=True):
        if not sentiments:
            st.caption(
                "_No sentiment for this event yet._ The tracker runs on HN/Reddit and saves "
                "pros, cons, and quotes per event when it finds net-new signal."
            )
            return

        # One consolidated view: merge all sources and dedupe so we don't repeat the same points
        agg = aggregate_sentiment(sentiments)
        sources = list({(s.get("source_url") or "").strip() for s in sentiments if (s.get("source_url") or "").strip()})

        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("**Pros**")
            st.markdown("---")
            if agg["pros"]:
                for line in agg["pros"]:
                    st.markdown(f"- {line}")
            else:
                st.caption("_No pros recorded._")
            st.markdown("")
        with col2:
            st.markdown("**Cons**")
            st.markdown("---")
            if agg["cons"]:
                for line in agg["cons"]:
                    st.markdown(f"- {line}")
            else:
                st.caption("_No cons recorded._")
            st.markdown("")
        with col3:
            st.markdown("**Voice of the Customer**")
            st.markdown("---")
            if agg["voice"]:
                for quote, url in agg["voice"]:
                    st.markdown(f"> {quote}")
                    if url:
                        st.markdown(f"[View Source]({url})")
                st.markdown("")
            else:
                st.caption("_No verbatims recorded._")

        if sources:
            st.caption(f"Consolidated from {len(sentiments)} source(s).")
            with st.expander("Source links", expanded=False):
                for url in sources[:20]:
                    st.markdown(f"[{_source_label(url)}]({url})")
                if len(sources) > 20:
                    st.caption(f"… and {len(sources) - 20} more.")

        # Strategic analysis from report.py (stored in events.cached_analysis when report runs)
        analysis = event.get("cached_analysis")
        if analysis:
            st.divider()
            st.markdown("**Strategic analysis**")
            st.markdown("---")
            st.markdown(analysis)
        else:
            st.caption("_Run report.py to generate strategic analysis for this event._")


def render_timeline(events: list, get_sentiment_fn) -> None:
    """Render events and their sentiment; for each event, fetch sentiment and render card."""
    if not events:
        st.info("No events for this target yet.")
        return
    for event in events:
        event_id = event.get("id")
        raw = get_sentiment_fn(event_id) if event_id else []
        sentiments = filter_meaningful_sentiment(raw)
        render_event_card(event, sentiments)


# -----------------------------------------------------------------------------
# Session state and main flow
# -----------------------------------------------------------------------------
def main():
    _inject_custom_css()
    if "selected_target_id" not in st.session_state:
        st.session_state["selected_target_id"] = None

    try:
        targets = fetch_targets()
    except Exception as e:
        st.error(
            "**Could not load targets from Supabase.** Check Streamlit Cloud → Settings → Secrets: "
            "**SUPABASE_URL** and **SUPABASE_KEY** (use the **service_role** key from Supabase → Project Settings → API). "
            "Ensure all migrations are applied (including `006_rls_read_policies.sql`)."
        )
        # Show PostgREST details when available (Streamlit redacts uncaught errors)
        err_parts = []
        if PostgrestAPIError and isinstance(e, PostgrestAPIError):
            code = getattr(e, "code", None)
            details = getattr(e, "details", None) or ""
            if code == "404" and ("<!DOCTYPE html" in str(details) or "supabase" in str(details).lower()):
                st.warning(
                    "**Wrong SUPABASE_URL.** You're getting a 404 HTML page instead of the API. "
                    "In Supabase go to **Project Settings → API** and set **SUPABASE_URL** to the **Project URL** "
                    "(e.g. `https://xxxx.supabase.co`), not the dashboard or app URL."
                )
            if code is not None:
                err_parts.append(f"Code: {e.code}")
            if getattr(e, "message", None):
                err_parts.append(f"Message: {e.message}")
            if details and len(str(details)) < 500:
                err_parts.append(f"Details: {details}")
            elif details:
                err_parts.append(f"Details: (truncated, {len(str(details))} chars)")
            if getattr(e, "hint", None):
                err_parts.append(f"Hint: {e.hint}")
        if not err_parts:
            err_parts.append(str(e))
        st.code("\n".join(err_parts), language="text")
        st.stop()

    selected_id = render_sidebar(targets, st.session_state["selected_target_id"])
    st.session_state["selected_target_id"] = selected_id

    if selected_id is None:
        st.markdown("## Select a company or product in the sidebar.")
        return

    target = fetch_target_by_id(selected_id)
    render_target_overview(target)

    st.markdown("## Events & sentiment")
    st.caption(
        "Headlines and dates for this target, with pros, cons, and voice-of-customer per event. "
        "Use this to see what happened and what the market said about each moment."
    )
    st.markdown("")
    events = fetch_events_for_target(selected_id)

    def get_sentiment(event_id):
        return fetch_sentiment_for_event(event_id)

    render_timeline(events, get_sentiment)

    # Show target-level (ungrouped) sentiment only if at least one row has real content
    ungrouped = fetch_sentiment_for_target_ungrouped(selected_id)
    meaningful_ungrouped = filter_meaningful_sentiment(ungrouped)
    if meaningful_ungrouped:
        st.divider()
        st.markdown("### General sentiment (not tied to a specific event)")
        st.caption("Sentiment for this target with no event link (e.g. from before events existed).")
        # Render same pros/cons/voice layout as event cards, but without a second expander/headline
        agg = aggregate_sentiment(meaningful_ungrouped)
        sources = list({(s.get("source_url") or "").strip() for s in meaningful_ungrouped if (s.get("source_url") or "").strip()})
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("**Pros**")
            st.markdown("---")
            if agg["pros"]:
                for line in agg["pros"]:
                    st.markdown(f"- {line}")
            else:
                st.caption("_No pros recorded._")
        with col2:
            st.markdown("**Cons**")
            st.markdown("---")
            if agg["cons"]:
                for line in agg["cons"]:
                    st.markdown(f"- {line}")
            else:
                st.caption("_No cons recorded._")
        with col3:
            st.markdown("**Voice of the Customer**")
            st.markdown("---")
            if agg["voice"]:
                for quote, url in agg["voice"]:
                    st.markdown(f"> {quote}")
                    if url:
                        st.markdown(f"[View Source]({url})")
            else:
                st.caption("_No verbatims recorded._")
        if sources:
            st.caption(f"Consolidated from {len(meaningful_ungrouped)} source(s).")
            with st.expander("Source links", expanded=False):
                for url in sources[:20]:
                    st.markdown(f"[{_source_label(url)}]({url})")
                if len(sources) > 20:
                    st.caption(f"… and {len(sources) - 20} more.")

        # Show strategic analysis for this target when we have it (from any event's cached_analysis)
        analysis = None
        for ev in events:
            if (ev.get("cached_analysis") or "").strip():
                analysis = (ev.get("cached_analysis") or "").strip()
                break
        if analysis:
            st.divider()
            st.markdown("**Strategic analysis**")
            st.markdown("---")
            st.markdown(analysis)
        else:
            st.caption("_Run report.py to generate strategic analysis for this target._")


if __name__ == "__main__":
    main()
