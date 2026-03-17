"""
Market Intelligence Engine — Executive Streamlit Dashboard.
Consumes targets, events, and sentiment from Supabase; uses config singleton for DB.

Run from project root:
  streamlit run src/app.py
Or with explicit Python path:
  PYTHONPATH=src streamlit run src/app.py
"""
import base64
import os
import sys

# Ensure src is on path so "from config import ..." works when run as streamlit run src/app.py
_src_dir = os.path.dirname(os.path.abspath(__file__))
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlparse

import requests

from config import get_supabase
from sentiment_dedupe import (
    dedupe_lines as _dedupe_lines,
    normalize_for_dedupe as _normalize_for_dedupe,
    to_bullet_lines as _to_bullet_lines,
)
try:
    from consolidate_pros_cons import consolidate_bullet_points_with_ai
except ImportError:
    consolidate_bullet_points_with_ai = None

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
    page_title="Market Intelligence",
    initial_sidebar_state="expanded",
)


# -----------------------------------------------------------------------------
# Minimal custom CSS: only for our hero card and avatar initials (no global overrides)
# -----------------------------------------------------------------------------
def _inject_custom_css() -> None:
    st.markdown(
        """
        <style>
        /* ── Global ─────────────────────────────────────────── */
        html, body, [class*="css"] {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                         Helvetica, Arial, sans-serif !important;
            -webkit-font-smoothing: antialiased;
        }
        .stApp { background: #F5F5F7 !important; }
        #MainMenu { visibility: hidden; }
        footer { visibility: hidden; }
        header[data-testid="stHeader"] { background: transparent !important; box-shadow: none !important; }
        .stAppDeployButton { display: none !important; }
        .stMainBlockContainer { padding-top: 2rem !important; }

        /* ── Sidebar ─────────────────────────────────────────── */
        [data-testid="stSidebar"] {
            background: rgba(255,255,255,0.92) !important;
            backdrop-filter: blur(20px);
            border-right: 1px solid rgba(0,0,0,0.07) !important;
        }
        [data-testid="stSidebar"] .stMarkdown h2 {
            font-size: 1rem; font-weight: 700; color: #1D1D1F; letter-spacing: -0.02em;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] {
            background: rgba(0,0,0,0.02) !important;
            border-radius: 12px !important;
            border: 1px solid rgba(0,0,0,0.07) !important;
            box-shadow: none !important;
        }

        /* ── Typography ──────────────────────────────────────── */
        h1, h2, h3 { color: #1D1D1F; letter-spacing: -0.03em; line-height: 1.15; font-weight: 700; }
        p, li { color: #1D1D1F; line-height: 1.6; }
        .stCaption, [data-testid="stCaptionContainer"] p { color: #86868B !important; font-size: 0.82rem !important; }

        /* ── Tabs ─────────────────────────────────────────────── */
        .stTabs [data-baseweb="tab-list"] {
            gap: 4px;
            background: rgba(0,0,0,0.05);
            border-radius: 14px;
            padding: 5px;
            border: none;
        }
        .stTabs [data-baseweb="tab"] {
            border-radius: 10px;
            padding: 8px 22px;
            font-size: 0.875rem;
            font-weight: 500;
            color: #86868B;
            border: none;
            background: transparent;
            transition: all 0.18s ease;
        }
        .stTabs [aria-selected="true"] {
            background: #FFFFFF !important;
            color: #1D1D1F !important;
            font-weight: 600;
            box-shadow: 0 1px 6px rgba(0,0,0,0.10);
        }

        /* ── Expanders ───────────────────────────────────────── */
        [data-testid="stExpander"] {
            background: rgba(255,255,255,0.80) !important;
            backdrop-filter: blur(20px);
            border-radius: 18px !important;
            border: 1px solid rgba(0,0,0,0.06) !important;
            box-shadow: 0 2px 18px rgba(0,0,0,0.04) !important;
            margin-bottom: 12px;
            overflow: hidden;
        }
        [data-testid="stExpander"] details summary p {
            font-weight: 600 !important;
            font-size: 0.95rem !important;
            color: #1D1D1F !important;
        }
        [data-testid="stExpander"] details summary:hover { background: rgba(0,0,0,0.02); }

        /* ── Inputs / Selects ────────────────────────────────── */
        [data-baseweb="select"] > div { border-radius: 12px !important; }
        [data-testid="stMultiSelect"] span[data-baseweb="tag"] {
            border-radius: 8px; background: rgba(0,113,227,0.1); color: #0071E3;
        }
        [data-testid="stRadio"] label { font-size: 0.875rem; font-weight: 500; }
        [data-testid="stAlert"] { border-radius: 14px; border: none !important; }
        hr { border-color: rgba(0,0,0,0.06); }

        /* ── Glass hero card ─────────────────────────────────── */
        .hero-card {
            background: rgba(255,255,255,0.88);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border-radius: 24px;
            border: 1px solid rgba(255,255,255,0.70);
            box-shadow: 0 8px 40px rgba(0,0,0,0.07);
            padding: 36px 40px;
            margin-bottom: 24px;
        }
        .hero-initial {
            width: 72px; height: 72px; border-radius: 18px;
            background: linear-gradient(135deg, #0071E3, #0055B3);
            color: #fff; font-size: 28px; font-weight: 700;
            display: inline-flex; align-items: center; justify-content: center;
            box-shadow: 0 4px 16px rgba(0,113,227,0.28);
        }
        .hero-type {
            font-size: 0.70rem; font-weight: 700; color: #86868B;
            letter-spacing: 0.10em; text-transform: uppercase; display: block; margin-bottom: 4px;
        }
        .hero-name {
            font-size: 2rem; font-weight: 700; color: #1D1D1F;
            letter-spacing: -0.04em; line-height: 1.1; margin: 0;
        }
        .hero-desc {
            font-size: 0.95rem; color: #424245; line-height: 1.65; margin-top: 16px;
        }

        /* ── Badge pills ─────────────────────────────────────── */
        .score-pill {
            display: inline-flex; align-items: center; gap: 5px;
            padding: 4px 13px; border-radius: 980px;
            font-size: 0.78rem; font-weight: 600; line-height: 1.4;
        }
        .badge-row {
            display: flex; align-items: center; gap: 8px;
            flex-wrap: wrap; margin: 12px 0 0 0;
        }

        /* ── Event card internals ────────────────────────────── */
        .pcc-grid {
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 28px;
            margin: 4px 0 12px 0;
        }
        .pcc-label {
            font-size: 0.68rem; font-weight: 700; color: #86868B;
            letter-spacing: 0.10em; text-transform: uppercase;
            margin-bottom: 10px; padding-bottom: 8px;
            border-bottom: 1px solid rgba(0,0,0,0.07);
        }
        .pcc-item {
            font-size: 0.875rem; color: #1D1D1F; line-height: 1.6;
            padding: 5px 0; border-bottom: 1px solid rgba(0,0,0,0.04);
            display: flex; gap: 8px; align-items: flex-start;
        }
        .pcc-item-dot { color: #86868B; flex-shrink: 0; margin-top: 2px; }
        .pcc-quote {
            font-size: 0.85rem; color: #424245; line-height: 1.65; font-style: italic;
            border-left: 3px solid #0071E3;
            padding: 8px 0 8px 14px; margin: 6px 0;
            background: rgba(0,113,227,0.03); border-radius: 0 8px 8px 0;
        }
        .pcc-source-link {
            font-size: 0.72rem; color: #0071E3; font-weight: 500;
            text-decoration: none; display: inline-block; margin-top: 3px;
        }
        .pcc-empty { font-size: 0.85rem; color: #86868B; }
        .pcc-badge-row {
            display: flex; align-items: center; gap: 8px;
            flex-wrap: wrap; margin-bottom: 18px;
        }
        .pcc-source-caption {
            font-size: 0.75rem; color: #86868B;
            padding: 3px 10px; background: rgba(0,0,0,0.04); border-radius: 980px;
        }

        /* ── Rankings ────────────────────────────────────────── */
        .rank-row {
            display: flex; align-items: center;
            padding: 14px 20px; margin-bottom: 6px;
            background: rgba(255,255,255,0.88);
            border-radius: 14px; border: 1px solid rgba(0,0,0,0.05);
            gap: 14px;
        }
        .rank-num { font-size: 0.85rem; font-weight: 700; color: #86868B; width: 28px; flex-shrink: 0; text-align: center; }
        .rank-name-wrap { flex: 1; min-width: 0; }
        .rank-name { font-size: 0.9rem; font-weight: 600; color: #1D1D1F; }
        .rank-type { font-size: 0.7rem; color: #86868B; letter-spacing: 0.05em; text-transform: uppercase; }
        .rank-meta { font-size: 0.8rem; color: #86868B; white-space: nowrap; }

        /* ── Section heads ───────────────────────────────────── */
        .section-head {
            font-size: 1.5rem; font-weight: 700; color: #1D1D1F;
            letter-spacing: -0.03em; margin: 0 0 4px 0;
        }
        .section-sub {
            font-size: 0.875rem; color: #86868B; line-height: 1.5; margin-bottom: 20px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# -----------------------------------------------------------------------------
# HTML helpers
# -----------------------------------------------------------------------------
def _he(text: str) -> str:
    """HTML-escape a string for safe inline insertion."""
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _logo_data_url(logo_bytes: bytes) -> str:
    """Convert logo bytes to an inline data URL."""
    if logo_bytes[:4] == b"\x89PNG":
        mime = "image/png"
    elif logo_bytes[:2] == b"\xff\xd8":
        mime = "image/jpeg"
    elif b"<svg" in logo_bytes[:200].lower() or logo_bytes[:5] == b"<?xml":
        mime = "image/svg+xml"
    else:
        mime = "image/png"
    return f"data:{mime};base64,{base64.b64encode(logo_bytes).decode()}"


# -----------------------------------------------------------------------------
# Sentiment score helpers
# -----------------------------------------------------------------------------
def _score_color(score: int) -> str:
    """Map score (-10..+10) to a hex color."""
    if score >= 7:
        return "#16a34a"   # green-600
    if score >= 3:
        return "#65a30d"   # lime-600
    if score >= -2:
        return "#6b7280"   # gray-500
    if score >= -6:
        return "#ea580c"   # orange-600
    return "#dc2626"       # red-600


def _score_label(score: int) -> str:
    if score >= 7:
        return "Very Positive"
    if score >= 3:
        return "Positive"
    if score >= -2:
        return "Neutral"
    if score >= -6:
        return "Negative"
    return "Very Negative"


def _render_score_badge(score: Optional[int]) -> None:
    """Render a colored score pill: e.g. ▲ +6 Positive"""
    if score is None:
        return
    color = _score_color(score)
    arrow = "▲" if score > 0 else ("▼" if score < 0 else "●")
    label = _score_label(score)
    sign = "+" if score > 0 else ""
    st.markdown(
        f'<span class="score-pill" style="background:{color};color:#fff;">'
        f'{arrow} {sign}{score} {label}</span>',
        unsafe_allow_html=True,
    )


def _compute_momentum(score_rows: list) -> Optional[float]:
    """
    Given sorted (created_at, sentiment_score) rows, return the delta:
    avg score of the last 7 days minus avg score of the 7 days before that.
    Returns None if insufficient data.
    """
    from datetime import timezone
    now = datetime.now(timezone.utc)
    cutoff_recent = now - timedelta(days=7)
    cutoff_prev = now - timedelta(days=14)

    recent, prev = [], []
    for row in score_rows:
        s = row.get("sentiment_score")
        if s is None:
            continue
        raw = row.get("created_at") or ""
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            continue
        if dt >= cutoff_recent:
            recent.append(s)
        elif dt >= cutoff_prev:
            prev.append(s)

    if not recent:
        return None
    avg_recent = sum(recent) / len(recent)
    if not prev:
        return None
    avg_prev = sum(prev) / len(prev)
    return round(avg_recent - avg_prev, 1)


_TAG_META = {
    "threat":      {"emoji": "🔴", "label": "Threat",      "color": "#dc2626"},
    "opportunity": {"emoji": "🟢", "label": "Opportunity", "color": "#16a34a"},
    "monitor":     {"emoji": "🟡", "label": "Monitor",     "color": "#ca8a04"},
    "no_action":   {"emoji": "⚪", "label": "No Action",   "color": "#6b7280"},
}

# Priority for resolving the dominant tag across multiple sentiment rows
_TAG_PRIORITY = {"threat": 0, "opportunity": 1, "monitor": 2, "no_action": 3}


def _dominant_tag(sentiments: list) -> Optional[str]:
    """Return the highest-priority implication_tag across all sentiment rows, or None."""
    tags = [s.get("implication_tag") for s in sentiments if s.get("implication_tag")]
    if not tags:
        return None
    return min(tags, key=lambda t: _TAG_PRIORITY.get(t, 99))


_SOURCE_LABELS = {
    "hn": "HN",
    "reddit": "Reddit",
    "stackoverflow": "Stack Overflow",
    "google_news": "Financial News",
}


def _format_source_type(source_types: list) -> str:
    """Given a list of source_type strings from sentiment rows, return a human-readable sources line."""
    seen: set = set()
    for st in source_types:
        if not st:
            continue
        for part in st.split("|"):
            p = part.strip()
            if p:
                seen.add(p)
    if not seen:
        return ""
    labels = [_SOURCE_LABELS.get(s, s.replace("_", " ").title()) for s in sorted(seen)]
    return ", ".join(labels)


def _render_tag_badge(tag: Optional[str]) -> None:
    """Render a colored implication tag pill: e.g. 🔴 Threat"""
    if not tag or tag not in _TAG_META:
        return
    meta = _TAG_META[tag]
    st.markdown(
        f'<span class="score-pill" style="background:{meta["color"]};color:#fff;">'
        f'{meta["emoji"]} {meta["label"]}</span>',
        unsafe_allow_html=True,
    )


def _render_momentum_badge(momentum: Optional[float]) -> None:
    """Render a momentum indicator: e.g. ↑ +2.3 vs last week"""
    if momentum is None:
        return
    if momentum > 0:
        color, arrow = "#16a34a", "↑"
        label = f"+{momentum} vs last 7 days"
    elif momentum < 0:
        color, arrow = "#dc2626", "↓"
        label = f"{momentum} vs last 7 days"
    else:
        color, arrow = "#6b7280", "→"
        label = "Stable vs last 7 days"
    st.markdown(
        f'<span class="score-pill" style="background:{color};color:#fff;">'
        f'{arrow} {label}</span>',
        unsafe_allow_html=True,
    )


# -----------------------------------------------------------------------------
# Data fetching
# -----------------------------------------------------------------------------
def fetch_targets():
    """Fetch all targets for sidebar (id, name, type, parent). Selected target details from fetch_target_by_id."""
    supabase = get_supabase()
    resp = supabase.table("targets").select(
        "id, name, target_type, status, parent_target_id, logo_url, domain"
    ).execute()
    return getattr(resp, "data", None) or []


def fetch_target_by_id(target_id: Optional[int]):
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


def fetch_events_for_target(target_id: Optional[int]):
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


def fetch_sentiment_for_event(event_id: Optional[int]):
    """Fetch all sentiment rows for an event (where event_id matches)."""
    if event_id is None:
        return []
    supabase = get_supabase()
    resp = (
        supabase.table("sentiment")
        .select("id, target_id, event_id, pros, cons, verbatim_quotes, source_url, created_at, sentiment_score, implication_tag, source_type")
        .eq("event_id", event_id)
        .execute()
    )
    return getattr(resp, "data", None) or []


def fetch_sentiment_for_target_ungrouped(target_id: Optional[int]):
    """Fetch sentiment rows for this target with no event (legacy or general target-level)."""
    if target_id is None:
        return []
    supabase = get_supabase()
    resp = (
        supabase.table("sentiment")
        .select("id, target_id, event_id, pros, cons, verbatim_quotes, source_url, created_at, sentiment_score, implication_tag, source_type")
        .eq("target_id", target_id)
        .is_("event_id", None)
        .execute()
    )
    return getattr(resp, "data", None) or []


def fetch_all_sentiment_scores_for_target(target_id: Optional[int]) -> list:
    """Fetch all (created_at, sentiment_score) rows for a target to compute momentum."""
    if target_id is None:
        return []
    supabase = get_supabase()
    resp = (
        supabase.table("sentiment")
        .select("created_at, sentiment_score")
        .eq("target_id", target_id)
        .not_.is_("sentiment_score", None)
        .order("created_at", desc=False)
        .execute()
    )
    return getattr(resp, "data", None) or []


def fetch_all_scores_batch() -> dict:
    """One-shot fetch of all (target_id, sentiment_score, created_at) rows. Returns dict: target_id -> [rows]."""
    supabase = get_supabase()
    resp = (
        supabase.table("sentiment")
        .select("target_id, sentiment_score, created_at")
        .not_.is_("sentiment_score", None)
        .order("created_at", desc=False)
        .execute()
    )
    rows = getattr(resp, "data", None) or []
    by_target: dict = {}
    for r in rows:
        tid = r.get("target_id")
        if tid:
            by_target.setdefault(tid, []).append(r)
    return by_target


def fetch_event_count_by_target() -> dict:
    """Returns dict: target_id -> event count."""
    supabase = get_supabase()
    resp = supabase.table("events").select("target_id").execute()
    rows = getattr(resp, "data", None) or []
    counts: dict = {}
    for r in rows:
        tid = r.get("target_id")
        if tid:
            counts[tid] = counts.get(tid, 0) + 1
    return counts


def fetch_recent_sentiment_for_target(target_id: Optional[int], limit: int = 5) -> list:
    """Fetch the most recent sentiment rows for a target (all events), for use in comparison cards."""
    if target_id is None:
        return []
    supabase = get_supabase()
    resp = (
        supabase.table("sentiment")
        .select("pros, cons, verbatim_quotes, source_url, sentiment_score, created_at")
        .eq("target_id", target_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return getattr(resp, "data", None) or []


def fetch_target_sentiment_summary(target_id: Optional[int]):
    """Fetch the AI-consolidated pros/cons for this target (one row per target). Returns dict or None."""
    if target_id is None:
        return None
    supabase = get_supabase()
    resp = supabase.table("target_sentiment_summary").select("pros, cons").eq("target_id", target_id).execute()
    data = getattr(resp, "data", None) or []
    return data[0] if data else None


# -----------------------------------------------------------------------------
# Filter low-value / placeholder sentiment (so we don't show "None identified" noise)
# -----------------------------------------------------------------------------
_PLACEHOLDER_PHRASES = (
    "none identified", "no clear pros", "no clear cons", "not explicitly mentioned",
    "no verbatims", "no pros", "no cons", "none found", "n/a", "not mentioned",
    "comments refer to", "refer to \"", "no items recorded", "no verbatims for this source",
)

# Longer boilerplate sentences we never want to show (model fallback when there is no signal)
_LONG_PLACEHOLDER_PHRASES = (
    "no information found in the chatter regarding market sentiment",
    "no information on the target topic in the provided chatter",
    "no relevant quotes on the target topic in the provided chatter",
)


def _text_is_placeholder(text: str) -> bool:
    """True if text is empty or a known placeholder / no-signal phrase."""
    if not text or not isinstance(text, str):
        return True
    s = text.strip().lower()
    if not s:
        return True
    # Always treat these longer boilerplate phrases as placeholders, regardless of length
    for p in _LONG_PLACEHOLDER_PHRASES:
        if p in s:
            return True
    # For the shorter phrases, only treat as placeholder when the whole field is small
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
    # Pros/cons: use AI to keep only distinct differentiators when Gemini is configured
    if os.getenv("GEMINI_API_KEY") and consolidate_bullet_points_with_ai:
        try:
            pros_out = consolidate_bullet_points_with_ai(all_pros, "pros")
            cons_out = consolidate_bullet_points_with_ai(all_cons, "cons")
        except Exception:
            pros_out = _dedupe_lines(all_pros)
            cons_out = _dedupe_lines(all_cons)
    else:
        pros_out = _dedupe_lines(all_pros)
        cons_out = _dedupe_lines(all_cons)
    return {
        "pros": pros_out,
        "cons": cons_out,
        "voice": voice_deduped,
    }



# -----------------------------------------------------------------------------
# Sidebar: navigation (Companies / Products)
# -----------------------------------------------------------------------------
def render_sidebar(targets: list, selected_target_id: Optional[int]) -> Optional[int]:
    """Render sidebar: Companies first; Products filtered by selected company. Returns selected target_id."""
    with st.sidebar:
        st.markdown(
            '<p style="font-size:1rem;font-weight:700;color:#1D1D1F;letter-spacing:-0.02em;margin:0 0 4px 0;">Market Intelligence</p>'
            '<p style="font-size:0.75rem;color:#86868B;margin:0 0 12px 0;">Powered by Gemini · Supabase</p>',
            unsafe_allow_html=True,
        )
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
def render_target_overview(target: dict, score_rows: Optional[list] = None) -> None:
    """Render target as a hero card: logo or initial, name, description, score momentum."""
    if not target:
        return
    name = target.get("name") or "Unnamed Target"
    description = target.get("description") or ""
    logo_url = _target_logo_url(target)
    initial = _target_initial(target)

    # Hero: try primary logo_url (Clearbit), then Google favicon by domain; else initial
    domain = target.get("domain") or (_domain_from_logo_url(logo_url) if logo_url else None)
    logo_bytes = _get_logo_bytes(logo_url, domain)
    target_type = (target.get("target_type") or "").upper()

    # Build inline logo HTML (data URL avoids st.image layout constraints)
    if logo_bytes:
        data_url = _logo_data_url(logo_bytes)
        logo_html = (
            f'<img src="{data_url}" width="72" height="72" '
            f'style="border-radius:14px;object-fit:contain;flex-shrink:0;" />'
        )
    else:
        logo_html = f'<div class="hero-initial">{_he(initial)}</div>'

    # Score + momentum badges
    badges = []
    if score_rows:
        recent_scores = [r.get("sentiment_score") for r in score_rows[-10:] if r.get("sentiment_score") is not None]
        if recent_scores:
            avg = round(sum(recent_scores) / len(recent_scores))
            color = _score_color(avg)
            arrow = "▲" if avg > 0 else ("▼" if avg < 0 else "●")
            sign = "+" if avg > 0 else ""
            badges.append(
                f'<span class="score-pill" style="background:{color};color:#fff;">'
                f'{arrow} {sign}{avg} {_score_label(avg)}</span>'
            )
        momentum = _compute_momentum(score_rows)
        if momentum is not None:
            if momentum > 0:
                mc, ma, ml = "#16a34a", "↑", f"+{momentum} vs last 7d"
            elif momentum < 0:
                mc, ma, ml = "#dc2626", "↓", f"{momentum} vs last 7d"
            else:
                mc, ma, ml = "#6b7280", "→", "Stable vs last 7d"
            badges.append(
                f'<span class="score-pill" style="background:{mc};color:#fff;">{ma} {ml}</span>'
            )
    badge_html = f'<div class="badge-row">{"".join(badges)}</div>' if badges else ""
    type_html = f'<span class="hero-type">{_he(target_type)}</span>' if target_type else ""
    desc_html = f'<div class="hero-desc">{_he(description)}</div>' if description else ""

    # Build as a single flat string — Streamlit's markdown parser mis-renders
    # multiline HTML by treating newline-separated closing tags as literal text.
    inner = (
        f'<div style="flex:1;min-width:0;">'
        f'{type_html}'
        f'<div class="hero-name">{_he(name)}</div>'
        f'{badge_html}'
        f'</div>'
    )
    row = (
        f'<div style="display:flex;align-items:flex-start;gap:20px;">'
        f'{logo_html}{inner}'
        f'</div>'
    )
    st.markdown(
        f'<div class="hero-card">{row}{desc_html}</div>',
        unsafe_allow_html=True,
    )


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
    """Render one event as an expander; prose/cons/quotes as a clean HTML grid inside."""
    headline = (event.get("headline") or "").strip() or "Untitled event"
    created = event.get("created_at")
    if created:
        try:
            dt = datetime.fromisoformat(created.replace("Z", "+00:00")) if isinstance(created, str) and "T" in created else created
            date_str = dt.strftime("%b %d, %Y") if hasattr(dt, "strftime") else str(created)
        except Exception:
            date_str = str(created)
    else:
        date_str = ""

    tag = _dominant_tag(sentiments)
    tag_prefix = f"{_TAG_META[tag]['emoji']} " if tag and tag in _TAG_META else ""
    label = f"{tag_prefix}{headline} — {date_str}" if date_str else f"{tag_prefix}{headline}"

    with st.expander(label, expanded=True):
        if not sentiments:
            st.caption("No new chatter for this event. The tracker saves pros, cons, and quotes when it finds net-new signal.")
            return

        agg = aggregate_sentiment(sentiments)
        sources = list({(s.get("source_url") or "").strip() for s in sentiments if (s.get("source_url") or "").strip()})
        scores = [s.get("sentiment_score") for s in sentiments if s.get("sentiment_score") is not None]
        avg_score = round(sum(scores) / len(scores)) if scores else None
        source_label = _format_source_type([s.get("source_type") for s in sentiments])

        # ── Badge row (score + tag + source caption) ──────────────
        badges = []
        if avg_score is not None:
            color = _score_color(avg_score)
            arrow = "▲" if avg_score > 0 else ("▼" if avg_score < 0 else "●")
            sign = "+" if avg_score > 0 else ""
            badges.append(
                f'<span class="score-pill" style="background:{color};color:#fff;">'
                f'{arrow} {sign}{avg_score} {_score_label(avg_score)}</span>'
            )
        if tag and tag in _TAG_META:
            meta = _TAG_META[tag]
            badges.append(
                f'<span class="score-pill" style="background:{meta["color"]};color:#fff;">'
                f'{meta["emoji"]} {meta["label"]}</span>'
            )
        if source_label:
            badges.append(f'<span class="pcc-source-caption">Sources: {_he(source_label)}</span>')

        st.markdown(
            f'<div class="pcc-badge-row">{"".join(badges)}</div>',
            unsafe_allow_html=True,
        )

        # ── Pros / Cons / Voice grid ───────────────────────────────
        def _build_bullets(lines):
            if not lines:
                return '<span class="pcc-empty">None recorded.</span>'
            return "".join(
                f'<div class="pcc-item"><span class="pcc-item-dot">·</span>{_he(line)}</div>'
                for line in lines
            )

        def _build_quotes(voice):
            if not voice:
                return '<span class="pcc-empty">None recorded.</span>'
            parts = []
            for quote, url in voice[:6]:
                link = (
                    f'<a href="{url}" target="_blank" class="pcc-source-link">View source →</a>'
                    if url else ""
                )
                parts.append(f'<div class="pcc-quote">{_he(quote)}{link}</div>')
            return "".join(parts)

        pros_col = f'<div><div class="pcc-label">Pros</div>{_build_bullets(agg["pros"])}</div>'
        cons_col = f'<div><div class="pcc-label">Cons</div>{_build_bullets(agg["cons"])}</div>'
        voice_col = f'<div><div class="pcc-label">Voice of the Customer</div>{_build_quotes(agg["voice"])}</div>'
        st.markdown(
            f'<div class="pcc-grid">{pros_col}{cons_col}{voice_col}</div>',
            unsafe_allow_html=True,
        )

        if sources:
            st.caption(f"Consolidated from {len(sentiments)} source(s).")
            with st.expander("Source links", expanded=False):
                for url in sources[:20]:
                    st.markdown(f"[{_source_label(url)}]({url})")
                if len(sources) > 20:
                    st.caption(f"… and {len(sources) - 20} more.")

        # Strategic analysis
        analysis = event.get("cached_analysis")
        if analysis:
            st.divider()
            st.markdown("**Strategic analysis**")
            st.markdown(analysis)
        else:
            st.caption("Run report.py to generate strategic analysis for this event.")


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
# P2: Competitive comparison helpers
# -----------------------------------------------------------------------------
def _avg_score(score_rows: list) -> Optional[float]:
    """Return rounded average sentiment score or None if no data."""
    scores = [r.get("sentiment_score") for r in score_rows if r.get("sentiment_score") is not None]
    return round(sum(scores) / len(scores)) if scores else None


def render_target_compare_card(target: dict, score_rows: list, sentiment_rows: list) -> None:
    """Render a compact comparison card: inline logo, big score, sparkline, top pros/cons."""
    name = target.get("name") or "Unknown"
    ttype = (target.get("target_type") or "").upper()
    logo_url = _target_logo_url(target)
    domain = target.get("domain") or (_domain_from_logo_url(logo_url) if logo_url else None)
    logo_bytes = _get_logo_bytes(logo_url, domain)

    # ── Header: inline logo + name (flat HTML, no st.columns) ─────
    if logo_bytes:
        data_url = _logo_data_url(logo_bytes)
        logo_html = (
            f'<img src="{data_url}" width="44" height="44" '
            f'style="border-radius:10px;object-fit:contain;flex-shrink:0;" />'
        )
    else:
        initial = (name[0].upper() if name else "?")
        logo_html = (
            f'<div style="width:44px;height:44px;border-radius:10px;'
            f'background:linear-gradient(135deg,#0071E3,#0055B3);color:#fff;'
            f'font-size:18px;font-weight:700;display:inline-flex;'
            f'align-items:center;justify-content:center;flex-shrink:0;">'
            f'{_he(initial)}</div>'
        )
    type_span = f'<span style="font-size:0.68rem;font-weight:700;color:#86868B;letter-spacing:0.08em;text-transform:uppercase;">{_he(ttype)}</span>'
    name_div = f'<div style="font-size:1rem;font-weight:700;color:#1D1D1F;line-height:1.2;">{_he(name)}</div>'
    name_block = f'<div style="flex:1;min-width:0;">{type_span}{name_div}</div>'
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;">{logo_html}{name_block}</div>',
        unsafe_allow_html=True,
    )

    # ── Big score display ──────────────────────────────────────────
    avg = _avg_score(score_rows)
    momentum = _compute_momentum(score_rows)
    if avg is not None:
        color = _score_color(avg)
        sign = "+" if avg > 0 else ""
        label = _score_label(avg)
        m_html = ""
        if momentum is not None:
            if momentum > 0:
                mc, ma, ml = "#16a34a", "↑", f"+{momentum}"
            elif momentum < 0:
                mc, ma, ml = "#dc2626", "↓", str(momentum)
            else:
                mc, ma, ml = "#6b7280", "→", "0"
            m_html = (
                f'<span style="font-size:0.78rem;font-weight:600;color:{mc};margin-left:6px;">'
                f'{ma} {ml} vs last 7d</span>'
            )
        st.markdown(
            f'<div style="text-align:center;padding:16px 0 12px 0;">'
            f'<div style="font-size:3.2rem;font-weight:800;color:{color};letter-spacing:-0.04em;line-height:1;">{sign}{avg}</div>'
            f'<div style="font-size:0.75rem;color:#86868B;font-weight:600;letter-spacing:0.06em;text-transform:uppercase;margin-top:4px;">{_he(label)}{m_html}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div style="text-align:center;padding:20px 0;color:#86868B;font-size:0.875rem;">No score data yet</div>',
            unsafe_allow_html=True,
        )

    # ── 30-day sparkline ──────────────────────────────────────────
    if score_rows:
        try:
            df_spark = _build_score_timeseries(score_rows, 30)
            if not df_spark.empty:
                df_spark["date"] = pd.to_datetime(df_spark["date"])
                df_spark = df_spark.set_index("date")[["rolling_avg"]]
                st.line_chart(df_spark, height=72, use_container_width=True)
                st.caption("30-day trend · 7-day avg")
        except Exception:
            pass

    # ── Top pros / cons compact grid ──────────────────────────────
    meaningful = filter_meaningful_sentiment(sentiment_rows)
    if meaningful:
        agg = aggregate_sentiment(meaningful)

        def _mini_bullets(lines, n=3):
            if not lines:
                return '<span class="pcc-empty">None recorded.</span>'
            return "".join(
                f'<div class="pcc-item"><span class="pcc-item-dot">·</span>{_he(l)}</div>'
                for l in lines[:n]
            )

        pros_col = f'<div><div class="pcc-label">Pros</div>{_mini_bullets(agg["pros"])}</div>'
        cons_col = f'<div><div class="pcc-label">Cons</div>{_mini_bullets(agg["cons"])}</div>'
        st.markdown(
            f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:8px;">{pros_col}{cons_col}</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div style="text-align:center;color:#86868B;font-size:0.875rem;padding:12px 0;">No sentiment data yet</div>',
            unsafe_allow_html=True,
        )


# -----------------------------------------------------------------------------
# P5: Trend charts (30/90 day sentiment timeline)
# -----------------------------------------------------------------------------
def _build_score_timeseries(score_rows: list, lookback_days: int) -> "pd.DataFrame":
    """
    Aggregate score rows into daily avg scores within the lookback window.
    Returns a pandas DataFrame with columns: date, score, rolling_avg.
    """
    from datetime import timezone

    if not score_rows:
        return pd.DataFrame(columns=["date", "score", "rolling_avg"])

    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    rows = []
    for r in score_rows:
        s = r.get("sentiment_score")
        if s is None:
            continue
        raw = r.get("created_at") or ""
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            continue
        if dt < cutoff:
            continue
        rows.append({"date": dt.date(), "score": s})

    if not rows:
        return pd.DataFrame(columns=["date", "score", "rolling_avg"])

    df = pd.DataFrame(rows)
    daily = df.groupby("date")["score"].mean().reset_index()
    daily = daily.sort_values("date")
    daily["rolling_avg"] = daily["score"].rolling(window=7, min_periods=1).mean().round(1)
    daily["score"] = daily["score"].round(1)
    return daily


def render_trend_chart(score_rows: list, target_name: str) -> None:
    """Render interactive sentiment trend chart with 30/90/All-time window toggle."""
    try:
        import altair as alt
    except ImportError:
        st.caption("_Chart library not available (altair required)._")
        return

    if not score_rows:
        st.caption("_No score data yet — trend chart will appear after the tracker runs._")
        return

    window_label = st.radio(
        "Window",
        options=["30 days", "90 days", "All time"],
        index=0,
        horizontal=True,
        key=f"trend_window_{target_name}",
    )
    days_map = {"30 days": 30, "90 days": 90, "All time": 3650}
    lookback = days_map[window_label]

    df = _build_score_timeseries(score_rows, lookback)
    if df.empty:
        st.caption(f"_No scored data in the last {window_label}._")
        return

    df["date"] = pd.to_datetime(df["date"])

    # Neutral reference band: -2 to +2
    neutral_band = alt.Chart(
        pd.DataFrame({"y1": [-2], "y2": [2]})
    ).mark_rect(opacity=0.08, color="#6b7280").encode(
        y=alt.Y("y1:Q"),
        y2=alt.Y2("y2:Q"),
    )

    # Zero line
    zero_rule = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(
        color="#6b7280", strokeDash=[4, 4], opacity=0.5
    ).encode(y="y:Q")

    # Daily avg bars (light)
    bars = alt.Chart(df).mark_bar(opacity=0.25, color="#0071E3").encode(
        x=alt.X("date:T", title=None, axis=alt.Axis(labelColor="#86868B", domainColor="rgba(0,0,0,0.1)", tickColor="transparent", gridColor="rgba(0,0,0,0.04)")),
        y=alt.Y("score:Q", title="Score", scale=alt.Scale(domain=[-10, 10]), axis=alt.Axis(labelColor="#86868B", titleColor="#86868B", domainColor="rgba(0,0,0,0.1)", gridColor="rgba(0,0,0,0.04)", tickColor="transparent")),
        tooltip=[
            alt.Tooltip("date:T", title="Date", format="%b %d, %Y"),
            alt.Tooltip("score:Q", title="Avg Score", format=".1f"),
        ],
    )

    # 7-day rolling avg line
    line = alt.Chart(df).mark_line(color="#0071E3", strokeWidth=2.5).encode(
        x=alt.X("date:T"),
        y=alt.Y("rolling_avg:Q", scale=alt.Scale(domain=[-10, 10])),
        tooltip=[
            alt.Tooltip("date:T", title="Date", format="%b %d, %Y"),
            alt.Tooltip("rolling_avg:Q", title="7-day Avg", format=".1f"),
        ],
    )

    points = alt.Chart(df).mark_circle(color="#0071E3", size=48, opacity=0.9).encode(
        x="date:T",
        y=alt.Y("rolling_avg:Q", scale=alt.Scale(domain=[-10, 10])),
        tooltip=[
            alt.Tooltip("date:T", title="Date", format="%b %d, %Y"),
            alt.Tooltip("rolling_avg:Q", title="7-day Avg", format=".1f"),
        ],
    )

    chart = (neutral_band + zero_rule + bars + line + points).properties(
        height=260,
        title=alt.TitleParams(
            text=f"{target_name} — Sentiment Trend ({window_label})",
            fontSize=13, fontWeight="bold", color="#1D1D1F", anchor="start",
        ),
        background="transparent",
    ).configure_view(strokeWidth=0).interactive()

    st.altair_chart(chart, use_container_width=True)
    st.caption(
        f"Bars = daily avg score | Line = 7-day rolling avg | Gray band = neutral zone (−2 to +2) | "
        f"{len(df)} day(s) with data"
    )


def render_weekly_brief_tab() -> None:
    """Show the most recent weekly brief from the reports/ directory."""
    st.markdown(
        '<div class="section-head">Weekly Executive Brief</div>'
        '<div class="section-sub">Strategic synthesis of the past 7 days — opportunities, risks, competitive shifts, and recommended actions.</div>',
        unsafe_allow_html=True,
    )

    # Locate the reports directory relative to this file
    reports_dir = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reports"))
    reports_dir = os.environ.get("REPORTS_DIR") or reports_dir

    try:
        files = [
            f for f in os.listdir(reports_dir)
            if f.startswith("weekly_brief_") and f.endswith(".md")
        ]
    except FileNotFoundError:
        files = []

    if not files:
        st.info(
            "No weekly brief found yet. Generate one by running:\n\n"
            "```\nPYTHONPATH=src python src/weekly_brief.py\n```"
        )
        return

    # Sort descending by filename (YYYY-WXX is lexicographically sortable)
    files.sort(reverse=True)
    latest = files[0]
    file_path = os.path.join(reports_dir, latest)

    # Let user pick a past brief if more than one exists
    if len(files) > 1:
        selected = st.selectbox(
            "Select week",
            options=files,
            index=0,
            format_func=lambda f: f.replace("weekly_brief_", "").replace(".md", ""),
            key="weekly_brief_select",
        )
        file_path = os.path.join(reports_dir, selected)
        latest = selected

    week_label = latest.replace("weekly_brief_", "").replace(".md", "")
    st.caption(f"Showing: **{week_label}**")
    st.divider()

    try:
        with open(file_path, "r") as f:
            content = f.read()
        st.markdown(content, unsafe_allow_html=False)
    except Exception as e:
        st.error(f"Could not read weekly brief: {e}")


def render_compare_tab(targets: list) -> None:
    """Compare up to 4 targets side by side."""
    st.markdown(
        '<div class="section-head">Compare Targets</div>'
        '<div class="section-sub">Select up to 4 targets to compare sentiment score, momentum, and top themes.</div>',
        unsafe_allow_html=True,
    )

    all_names = [t.get("name") or f"Target {t.get('id')}" for t in targets]
    target_by_name = {(t.get("name") or f"Target {t.get('id')}"): t for t in targets}

    selected_names = st.multiselect(
        "Choose targets to compare",
        options=all_names,
        default=all_names[:min(3, len(all_names))],
        max_selections=4,
        key="compare_multiselect",
    )
    if not selected_names:
        st.info("Select at least one target above.")
        return

    selected_targets = [target_by_name[n] for n in selected_names if n in target_by_name]
    cols = st.columns(len(selected_targets))
    for col, target in zip(cols, selected_targets):
        with col:
            t_id = target.get("id")
            score_rows = fetch_all_sentiment_scores_for_target(t_id)
            sentiment_rows = fetch_recent_sentiment_for_target(t_id, limit=10)
            render_target_compare_card(target, score_rows, sentiment_rows)


def render_rankings_tab(targets: list) -> None:
    """Leaderboard: all tracked targets ranked by avg sentiment score."""
    st.markdown(
        '<div class="section-head">Sentiment Rankings</div>'
        '<div class="section-sub">All tracked targets ranked by average AI-assigned market sentiment score (−10 to +10).</div>',
        unsafe_allow_html=True,
    )

    scores_by_target = fetch_all_scores_batch()
    event_counts = fetch_event_count_by_target()

    rows = []
    for t in targets:
        t_id = t.get("id")
        t_name = t.get("name") or "Unknown"
        ttype = (t.get("target_type") or "").capitalize()
        t_scores = scores_by_target.get(t_id, [])
        avg = _avg_score(t_scores)
        momentum = _compute_momentum(t_scores)
        n_events = event_counts.get(t_id, 0)
        rows.append({
            "target_id": t_id, "name": t_name, "type": ttype,
            "avg_score": avg, "momentum": momentum,
            "events": n_events, "readings": len(t_scores),
        })

    rows_scored = sorted([r for r in rows if r["avg_score"] is not None], key=lambda x: x["avg_score"], reverse=True)
    rows_sorted = rows_scored + [r for r in rows if r["avg_score"] is None]

    if not rows_sorted:
        st.info("No targets to rank yet.")
        return

    html_rows = []
    for i, r in enumerate(rows_sorted, 1):
        if r["avg_score"] is not None:
            color = _score_color(r["avg_score"])
            score_cell = (
                f'<span class="score-pill" style="background:{color};color:#fff;">'
                f'{r["avg_score"]:+d} {_score_label(r["avg_score"])}</span>'
            )
        else:
            score_cell = '<span class="rank-meta">—</span>'

        m = r["momentum"]
        if m is None:
            trend_html = '<span class="rank-meta">—</span>'
        elif m > 0:
            trend_html = f'<span style="color:#16a34a;font-weight:600;font-size:0.82rem;">↑ +{m}</span>'
        elif m < 0:
            trend_html = f'<span style="color:#dc2626;font-weight:600;font-size:0.82rem;">↓ {m}</span>'
        else:
            trend_html = '<span class="rank-meta">→ 0</span>'

        html_rows.append(f"""
        <div class="rank-row">
          <span class="rank-num">{i}</span>
          <div class="rank-name-wrap">
            <div class="rank-name">{_he(r["name"])}</div>
            <div class="rank-type">{_he(r["type"])}</div>
          </div>
          <div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap;">
            {score_cell}
            {trend_html}
            <span class="rank-meta">{r["events"]} events</span>
            <span class="rank-meta">{r["readings"]} readings</span>
          </div>
        </div>
        """)

    st.markdown("".join(html_rows), unsafe_allow_html=True)

    with st.expander("Score scale reference", expanded=False):
        st.markdown(
            "| Range | Label |\n|-------|-------|\n"
            "| +7 to +10 | 🟢 Very Positive |\n"
            "| +3 to +6  | 🟡 Positive |\n"
            "| -2 to +2  | ⚪ Neutral |\n"
            "| -6 to -3  | 🟠 Negative |\n"
            "| -10 to -7 | 🔴 Very Negative |"
        )


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

    tab_dive, tab_compare, tab_rank, tab_brief = st.tabs(["🔍 Deep Dive", "⚡ Compare", "🏆 Rankings", "📋 Weekly Brief"])

    with tab_dive:
        if selected_id is None:
            st.info("Select a company or product in the sidebar.")
        else:
            target = fetch_target_by_id(selected_id)
            score_rows = fetch_all_sentiment_scores_for_target(selected_id)
            render_target_overview(target, score_rows)

            if score_rows:
                with st.expander("📈 Sentiment trend", expanded=False):
                    render_trend_chart(score_rows, target.get("name") or "")

            st.markdown(
                '<div class="section-head">Events &amp; Sentiment</div>'
                '<div class="section-sub">Headlines for this target with pros, cons, and voice-of-customer per event.</div>',
                unsafe_allow_html=True,
            )
            events = fetch_events_for_target(selected_id)

            def get_sentiment(event_id):
                return fetch_sentiment_for_event(event_id)

            render_timeline(events, get_sentiment)

            # Show target-level sentiment: use AI summary when available, else aggregate ungrouped rows
            ungrouped = fetch_sentiment_for_target_ungrouped(selected_id)
            meaningful_ungrouped = filter_meaningful_sentiment(ungrouped)
            summary = fetch_target_sentiment_summary(selected_id)
            agg = aggregate_sentiment(meaningful_ungrouped) if meaningful_ungrouped else {"pros": [], "cons": [], "voice": []}
            has_summary = summary and ((summary.get("pros") or "").strip() or (summary.get("cons") or "").strip())
            if meaningful_ungrouped or has_summary:
                st.divider()
                st.markdown('<div class="section-head" style="font-size:1.2rem;">Company Sentiment</div>', unsafe_allow_html=True)
                st.caption(
                    "Sentiment for this target."
                    + (" From **target_sentiment_summary** (rule-based consolidated)." if has_summary else " From **ungrouped sentiment** rows (no summary for this target yet).")
                )
                pros_display = _to_bullet_lines(summary["pros"] or "") if has_summary else agg["pros"]
                cons_display = _to_bullet_lines(summary["cons"] or "") if has_summary else agg["cons"]
                sources = list({(s.get("source_url") or "").strip() for s in meaningful_ungrouped if (s.get("source_url") or "").strip()})
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.markdown("**Pros**")
                    st.markdown("---")
                    if pros_display:
                        for line in pros_display:
                            st.markdown(f"- {line}")
                    else:
                        st.caption("_No pros recorded._")
                with col2:
                    st.markdown("**Cons**")
                    st.markdown("---")
                    if cons_display:
                        for line in cons_display:
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

    with tab_compare:
        render_compare_tab(targets)

    with tab_rank:
        render_rankings_tab(targets)

    with tab_brief:
        render_weekly_brief_tab()


if __name__ == "__main__":
    main()
