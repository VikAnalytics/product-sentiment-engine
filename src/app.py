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
import re
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


def _parse_iso_dt(ts: str) -> datetime:
    """Parse ISO 8601 timestamp robustly on Python 3.9 (fromisoformat is stricter there).
    Normalises fractional seconds to exactly 6 digits before parsing."""
    ts = ts.replace("Z", "+00:00")
    # Pad or truncate fractional seconds to exactly 6 digits
    ts = re.sub(r"\.(\d+)([+-])", lambda m: "." + (m.group(1) + "000000")[:6] + m.group(2), ts)
    return datetime.fromisoformat(ts)

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
    page_icon="📊",
    initial_sidebar_state="expanded",
)


# -----------------------------------------------------------------------------
# Minimal custom CSS: only for our hero card and avatar initials (no global overrides)
# -----------------------------------------------------------------------------
def _inject_custom_css() -> None:
    d = {
        "bg":            "#0A0E1A",
        "surface":       "rgba(255,255,255,0.06)",
        "surface_hover": "rgba(255,255,255,0.10)",
        "border":        "rgba(255,255,255,0.10)",
        "text1":         "#F5F5F7",
        "text2":         "#A1A1A6",
        "text3":         "#D1D1D6",
        "accent":        "#2997FF",
        "sidebar_bg":    "rgba(16,21,40,0.97)",
        "hero_bg":       "rgba(255,255,255,0.06)",
        "hero_border":   "rgba(255,255,255,0.12)",
        "tab_list":      "rgba(255,255,255,0.06)",
        "tab_active":    "rgba(255,255,255,0.14)",
        "tab_active_c":  "#F5F5F7",
        "tab_inactive_c":"#A1A1A6",
        "expander_bg":   "rgba(255,255,255,0.04)",
        "rank_bg":       "rgba(255,255,255,0.04)",
        "mesh1":         "#1A2A4A",
        "mesh2":         "#2A1A4A",
        "mesh3":         "#1A3A2A",
        "input_bg":      "rgba(255,255,255,0.06)",
        "hr":            "rgba(255,255,255,0.08)",
        "pcc_label_bdr": "rgba(255,255,255,0.08)",
        "pcc_item_bdr":  "rgba(255,255,255,0.04)",
        "pcc_quote_bg":  "rgba(41,151,255,0.08)",
        "caption_bg":    "rgba(255,255,255,0.06)",
        "shadow":        "rgba(0,0,0,0.45)",
        "shadow_hover":  "rgba(0,0,0,0.65)",
        "blob_opacity":  "0.40",
        "hdr_bg":        "rgba(10,14,26,0.90)",
        "shimmer":       "rgba(255,255,255,0.07)",
        "pill_shadow":   "0 2px 8px rgba(0,0,0,0.4)",
    }
    st.markdown(f"""
        <style>
        /* ── Global ─────────────────────────────────────────── */
        html, body {{
            color-scheme: dark !important;
        }}
        html, body, [class*="css"] {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                         Helvetica, Arial, sans-serif !important;
            -webkit-font-smoothing: antialiased;
        }}
        .stApp, .main, [data-testid="stAppViewContainer"],
        [data-testid="stMain"], [data-testid="stAppViewContainer"] > .main {{
            background: {d['bg']} !important;
        }}
        #MainMenu {{ visibility: hidden; }}
        footer {{ visibility: hidden; }}
        header[data-testid="stHeader"] {{ background: transparent !important; box-shadow: none !important; }}
        .stAppDeployButton {{ display: none !important; }}
        .stMainBlockContainer {{ padding-top: 1.5rem !important; }}

        /* ── Gradient mesh blobs ─────────────────────────────── */
        .mesh-blob {{
            position: fixed; border-radius: 50%; filter: blur(90px);
            pointer-events: none; z-index: 0; opacity: {d['blob_opacity']};
        }}
        .mesh-b1 {{ width:700px; height:700px; background:{d['mesh1']}; top:-200px; left:-200px;
                    animation: mf1 18s ease-in-out infinite; }}
        .mesh-b2 {{ width:600px; height:600px; background:{d['mesh2']}; bottom:-150px; right:-150px;
                    animation: mf2 22s ease-in-out infinite; }}
        .mesh-b3 {{ width:400px; height:400px; background:{d['mesh3']}; top:40%; left:55%;
                    animation: mf3 26s ease-in-out infinite; }}
        @keyframes mf1 {{
            0%,100% {{ transform: translate(0,0) scale(1); }}
            33%      {{ transform: translate(60px,-40px) scale(1.06); }}
            66%      {{ transform: translate(-30px,50px) scale(0.97); }}
        }}
        @keyframes mf2 {{
            0%,100% {{ transform: translate(0,0) scale(1); }}
            40%      {{ transform: translate(-50px,40px) scale(1.09); }}
            70%      {{ transform: translate(40px,-30px) scale(0.95); }}
        }}
        @keyframes mf3 {{
            0%,100% {{ transform: translate(0,0) scale(1); }}
            50%      {{ transform: translate(30px,55px) scale(1.13); }}
        }}

        /* ── Page header ─────────────────────────────────────── */
        .page-header {{
            position: sticky; top: 3.5rem; z-index: 200;
            background: {d['hdr_bg']};
            backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
            border-bottom: 1px solid {d['border']};
            padding: 10px 16px; margin: -1.5rem -1rem 1.5rem -1rem;
            display: flex; align-items: center; gap: 10px;
        }}
        .ph-title {{ font-size: 0.9rem; font-weight: 700; color: {d['text1']}; letter-spacing: -0.02em; }}
        .ph-sep   {{ color: {d['text2']}; font-size: 0.85rem; }}
        .ph-target {{ font-size: 0.9rem; font-weight: 500; color: {d['accent']}; }}
        .ph-live  {{
            margin-left: auto; display: flex; align-items: center; gap: 6px;
            font-size: 0.75rem; font-weight: 600; color: #30D158;
            letter-spacing: 0.05em; text-transform: uppercase;
        }}
        .live-dot {{
            width: 7px; height: 7px; border-radius: 50%; background: #30D158;
            animation: pulse-green 2s ease-in-out infinite;
        }}
        @keyframes pulse-green {{
            0%,100% {{ opacity:1; transform:scale(1); }}
            50%      {{ opacity:0.45; transform:scale(0.8); }}
        }}

        /* ── Sidebar ─────────────────────────────────────────── */
        [data-testid="stSidebar"] {{
            background: {d['sidebar_bg']} !important;
            backdrop-filter: blur(20px);
            border-right: 1px solid {d['border']} !important;
        }}
        [data-testid="stSidebar"] .stMarkdown h2 {{
            font-size: 1rem; font-weight: 700; color: {d['text1']}; letter-spacing: -0.02em;
        }}
        [data-testid="stSidebar"] [data-testid="stExpander"] {{
            background: {d['input_bg']} !important;
            border-radius: 12px !important;
            border: 1px solid {d['border']} !important;
            box-shadow: none !important;
        }}

        /* ── Typography ──────────────────────────────────────── */
        h1, h2, h3 {{ color: {d['text1']}; letter-spacing: -0.03em; line-height: 1.15; font-weight: 700; }}
        p, li {{ color: {d['text1']}; line-height: 1.6; }}
        .stCaption, [data-testid="stCaptionContainer"] p {{ color: {d['text2']} !important; font-size: 0.82rem !important; }}

        /* ── Tabs ─────────────────────────────────────────────── */
        .stTabs [data-baseweb="tab-list"] {{
            gap: 4px; background: {d['tab_list']}; border-radius: 14px;
            padding: 5px; border: none; display: flex; width: 100%;
        }}
        .stTabs [data-baseweb="tab"] {{
            flex: 1; text-align: center; justify-content: center;
            border-radius: 10px; padding: 8px 0; font-size: 0.875rem;
            font-weight: 500; color: {d['tab_inactive_c']}; border: none;
            background: transparent; transition: all 0.18s ease; letter-spacing: 0.01em;
        }}
        .stTabs [aria-selected="true"] {{
            background: {d['tab_active']} !important; color: {d['tab_active_c']} !important;
            font-weight: 600; box-shadow: 0 1px 6px {d['shadow']};
        }}

        /* ── Expanders ───────────────────────────────────────── */
        [data-testid="stExpander"] {{
            background: {d['expander_bg']} !important;
            backdrop-filter: blur(20px);
            border-radius: 18px !important;
            border: 1px solid {d['border']} !important;
            box-shadow: 0 2px 18px {d['shadow']} !important;
            margin-bottom: 12px; overflow: hidden;
            transition: transform 0.2s cubic-bezier(0.4,0,0.2,1), box-shadow 0.2s ease !important;
        }}
        [data-testid="stExpander"]:hover {{
            transform: translateY(-2px) !important;
            box-shadow: 0 8px 36px {d['shadow_hover']} !important;
        }}
        [data-testid="stExpander"] details summary {{
            background: transparent !important;
        }}
        [data-testid="stExpander"] details summary p {{
            font-weight: 600 !important; font-size: 0.95rem !important; color: {d['text1']} !important;
        }}
        [data-testid="stExpander"] details summary:hover {{ background: rgba(128,128,128,0.05) !important; }}

        /* ── Inputs / Selects ────────────────────────────────── */
        [data-baseweb="select"] > div {{ border-radius: 12px !important; background: {d['input_bg']} !important; }}
        [data-baseweb="select"] span {{ color: {d['text1']} !important; }}
        [data-testid="stMultiSelect"] span[data-baseweb="tag"] {{
            border-radius: 8px; background: rgba(41,151,255,0.15); color: {d['accent']};
        }}
        [data-testid="stRadio"] label {{ font-size: 0.875rem; font-weight: 500; color: {d['text1']}; }}
        [data-testid="stAlert"] {{ border-radius: 14px; border: none !important; }}
        hr {{ border-color: {d['hr']}; }}
        [data-testid="stToggle"] label {{ font-size: 0.85rem; font-weight: 500; color: {d['text2']}; }}

        /* ── Selectbox dropdown portal ───────────────────────── */
        [data-baseweb="popover"], [data-baseweb="menu"] {{
            background: #1C2333 !important;
            border: 1px solid {d['border']} !important;
            border-radius: 12px !important;
            box-shadow: 0 8px 32px {d['shadow']} !important;
        }}
        [data-baseweb="option"],
        [data-baseweb="option"] * {{
            background: transparent !important;
            color: {d['text1']} !important;
            font-size: 0.875rem !important;
        }}
        [data-baseweb="option"]:hover,
        [data-baseweb="option"][aria-selected="true"] {{
            background: {d['input_bg']} !important;
        }}
        li[role="option"],
        li[role="option"] * {{
            background: transparent !important;
            color: {d['text1']} !important;
        }}
        li[role="option"]:hover {{ background: {d['input_bg']} !important; }}

        /* ── Score ring animation ────────────────────────────── */
        .score-ring {{
            animation: ring-appear 0.65s cubic-bezier(0.34,1.56,0.64,1) forwards;
        }}
        @keyframes ring-appear {{
            from {{ opacity:0; transform:scale(0.65); }}
            to   {{ opacity:1; transform:scale(1); }}
        }}

        /* ── Glass hero card ─────────────────────────────────── */
        .hero-card {{
            background: {d['hero_bg']};
            backdrop-filter: blur(24px); -webkit-backdrop-filter: blur(24px);
            border-radius: 24px; border: 1px solid {d['hero_border']};
            box-shadow: 0 8px 40px {d['shadow']};
            padding: 36px 40px; margin-bottom: 12px;
        }}
        .hero-initial {{
            width: 72px; height: 72px; border-radius: 18px;
            background: linear-gradient(135deg, {d['accent']}, #1055D4);
            color: #fff; font-size: 28px; font-weight: 700;
            display: inline-flex; align-items: center; justify-content: center;
            box-shadow: 0 4px 16px rgba(0,113,227,0.28);
        }}
        .hero-type {{
            font-size: 0.70rem; font-weight: 700; color: {d['text2']};
            letter-spacing: 0.10em; text-transform: uppercase; display: block; margin-bottom: 4px;
        }}
        .hero-name {{
            font-size: 2rem; font-weight: 700; color: {d['text1']};
            letter-spacing: -0.04em; line-height: 1.1; margin: 0;
        }}
        .hero-desc {{
            font-size: 0.95rem; color: {d['text3']}; line-height: 1.65; margin-top: 16px;
        }}

        /* ── Badge pills ─────────────────────────────────────── */
        .score-pill {{
            display: inline-flex; align-items: center; gap: 5px;
            padding: 5px 13px; border-radius: 980px;
            font-size: 0.78rem; font-weight: 600; line-height: 1.4;
            box-shadow: {d['pill_shadow']};
        }}
        .badge-row {{
            display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin: 12px 0 0 0;
        }}

        /* ── Event card internals ────────────────────────────── */
        .pcc-grid {{
            display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 28px; margin: 4px 0 12px 0;
        }}
        .pcc-label {{
            font-size: 0.68rem; font-weight: 700; color: {d['text2']};
            letter-spacing: 0.10em; text-transform: uppercase;
            margin-bottom: 10px; padding-bottom: 8px;
            border-bottom: 1px solid {d['pcc_label_bdr']};
        }}
        .pcc-item {{
            font-size: 0.875rem; color: {d['text1']}; line-height: 1.6;
            padding: 5px 0; border-bottom: 1px solid {d['pcc_item_bdr']};
            display: flex; gap: 8px; align-items: flex-start;
        }}
        .pcc-item-dot {{ color: {d['text2']}; flex-shrink: 0; margin-top: 2px; }}
        .pcc-quote {{
            font-size: 0.85rem; color: {d['text3']}; line-height: 1.65; font-style: italic;
            border-left: 3px solid {d['accent']};
            padding: 8px 0 8px 14px; margin: 6px 0;
            background: {d['pcc_quote_bg']}; border-radius: 0 8px 8px 0;
        }}
        .pcc-source-link {{
            font-size: 0.72rem; color: {d['accent']}; font-weight: 500;
            text-decoration: none; display: inline-block; margin-top: 3px;
        }}
        .pcc-empty {{ font-size: 0.85rem; color: {d['text2']}; }}
        .pcc-badge-row {{
            display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 18px;
        }}
        .pcc-source-caption {{
            font-size: 0.75rem; color: {d['text2']};
            padding: 3px 10px; background: {d['caption_bg']}; border-radius: 980px;
        }}

        /* ── Rankings ────────────────────────────────────────── */
        .rank-row {{
            display: flex; align-items: center;
            padding: 14px 20px; margin-bottom: 6px;
            background: {d['rank_bg']};
            border-radius: 14px; border: 1px solid {d['border']};
            gap: 14px; transition: transform 0.15s ease, box-shadow 0.15s ease;
        }}
        .rank-row:hover {{ transform: translateX(4px); box-shadow: 0 4px 20px {d['shadow_hover']}; }}
        .rank-num   {{ font-size: 0.85rem; font-weight: 700; color: {d['text2']}; width: 32px; flex-shrink: 0; text-align: center; }}
        .rank-medal {{ font-size: 1.25rem; width: 32px; flex-shrink: 0; text-align: center; line-height: 1; }}
        .rank-name-wrap {{ flex: 1; min-width: 0; }}
        .rank-name  {{ font-size: 0.9rem; font-weight: 600; color: {d['text1']}; }}
        .rank-type  {{ font-size: 0.7rem; color: {d['text2']}; letter-spacing: 0.05em; text-transform: uppercase; }}
        .rank-bar-track {{
            height: 5px; background: {d['border']}; border-radius: 3px;
            flex: 1; min-width: 60px; max-width: 110px; overflow: hidden; margin-top: 3px;
        }}
        .rank-meta {{ font-size: 0.8rem; color: {d['text2']}; white-space: nowrap; }}

        /* ── Section heads ───────────────────────────────────── */
        .section-head {{
            font-size: 1.5rem; font-weight: 700; color: {d['text1']};
            letter-spacing: -0.03em; margin: 0 0 4px 0;
        }}
        .section-sub {{
            font-size: 0.875rem; color: {d['text2']}; line-height: 1.5; margin-bottom: 20px;
        }}

        /* ── Skeleton shimmer ────────────────────────────────── */
        .skeleton {{ border-radius: 10px; overflow: hidden; position: relative; background: {d['border']}; }}
        .skeleton::after {{
            content: ''; position: absolute; inset: 0;
            background: linear-gradient(90deg, transparent 0%, {d['shimmer']} 50%, transparent 100%);
            animation: shimmer 1.6s ease-in-out infinite;
        }}
        @keyframes shimmer {{ 0% {{ transform: translateX(-100%); }} 100% {{ transform: translateX(100%); }} }}
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


def _score_ring_html(score: Optional[int], size: int = 80) -> str:
    """SVG animated score ring (Apple Watch-style)."""
    if score is None:
        return ""
    r = (size - 10) / 2
    circ = 2 * 3.14159 * r
    pct = (score + 10) / 20          # map -10..+10 → 0..1
    dashoffset = circ * (1 - pct)
    color = _score_color(score)
    sign = "+" if score > 0 else ""
    cx = cy = size / 2
    fscore = round(size * 0.175)
    flabel = round(size * 0.095)
    return (
        f'<div class="score-ring" style="position:relative;width:{size}px;height:{size}px;flex-shrink:0;">'
        f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}">'
        f'<circle cx="{cx}" cy="{cy}" r="{r:.1f}" fill="none" stroke="rgba(128,128,128,0.15)" stroke-width="6"/>'
        f'<circle cx="{cx}" cy="{cy}" r="{r:.1f}" fill="none" stroke="{color}" stroke-width="6"'
        f' stroke-linecap="round" stroke-dasharray="{circ:.1f}" stroke-dashoffset="{dashoffset:.1f}"'
        f' transform="rotate(-90 {cx} {cy})"/>'
        f'</svg>'
        f'<div style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;">'
        f'<span style="font-size:{fscore}px;font-weight:800;color:{color};line-height:1;">{sign}{score}</span>'
        f'<span style="font-size:{flabel}px;font-weight:600;color:#86868B;letter-spacing:0.04em;text-transform:uppercase;">score</span>'
        f'</div></div>'
    )


def _mini_sparkline_svg(score_rows: list, width: int = 200, height: int = 48) -> str:
    """Inline SVG sparkline of 30-day rolling avg. Returns empty string if insufficient data."""
    df = _build_score_timeseries(score_rows, 30)
    if df.empty or len(df) < 2:
        return ""
    values = df["rolling_avg"].tolist()
    mn = min(values) - 0.5
    mx = max(values) + 0.5
    if mx == mn:
        mx = mn + 1.0
    def px(i: int) -> float:
        return i / (len(values) - 1) * width
    def py(v: float) -> float:
        return height - 4 - (v - mn) / (mx - mn) * (height - 8)
    pts = " ".join(f"{px(i):.1f},{py(v):.1f}" for i, v in enumerate(values))
    fill_pts = f"0,{height} {pts} {width},{height}"
    color = _score_color(round(values[-1]))
    uid = abs(hash(pts)) % 99999
    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" style="overflow:visible;display:block;">'
        f'<defs><linearGradient id="sf{uid}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="{color}" stop-opacity="0.30"/>'
        f'<stop offset="100%" stop-color="{color}" stop-opacity="0"/>'
        f'</linearGradient></defs>'
        f'<polygon points="{fill_pts}" fill="url(#sf{uid})"/>'
        f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2.5"'
        f' stroke-linecap="round" stroke-linejoin="round"/>'
        f'</svg>'
    )


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
            dt = _parse_iso_dt(raw)
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
    """Fetch all tracked targets for sidebar (id, name, type, parent). Selected target details from fetch_target_by_id."""
    supabase = get_supabase()
    resp = supabase.table("targets").select(
        "id, name, target_type, status, parent_target_id, logo_url, domain, sector, is_f500"
    ).eq("status", "tracking").execute()
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
    """Logo URL for target; falls back to parent company logo for products with no logo."""
    url = (target.get("logo_url") or "").strip()
    if url:
        return url
    parent_id = target.get("parent_target_id")
    if parent_id:
        targets_by_id: dict = st.session_state.get("_targets_by_id", {})
        parent = targets_by_id.get(parent_id, {})
        url = (parent.get("logo_url") or "").strip()
        return url if url else None
    return None


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


@st.cache_data(ttl=60)
def fetch_price_reaction(event_id: Optional[int]) -> Optional[dict]:
    """Fetch price reaction row for an event. Returns None if no ticker / no data."""
    if event_id is None:
        return None
    supabase = get_supabase()
    resp = (
        supabase.table("price_reactions")
        .select("ticker, price_at_event, window_return_pct, reaction_1d, reaction_3d, reaction_7d, market_session, confidence, confidence_reason")
        .eq("event_id", event_id)
        .limit(1)
        .execute()
    )
    rows = getattr(resp, "data", None) or []
    return rows[0] if rows else None


@st.cache_data(ttl=60)
def fetch_price_series(target_id: Optional[int], days: int = 30) -> list:
    """Fetch daily close prices for the price chart (last N days, last bar per day).
    Paginates in 1000-row pages to work around Supabase's default row cap."""
    if target_id is None:
        return []
    from datetime import timezone as _tz
    cutoff = (datetime.now(_tz.utc) - timedelta(days=days)).isoformat()
    supabase = get_supabase()
    by_date: dict = {}
    page_size = 1000
    offset = 0
    while True:
        resp = (
            supabase.table("stock_prices")
            .select("ts, close")
            .eq("target_id", target_id)
            .gte("ts", cutoff)
            .order("ts", desc=False)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        rows = getattr(resp, "data", None) or []
        for r in rows:
            day = r["ts"][:10]
            by_date[day] = r["close"]  # last bar of day wins (ascending order)
        if len(rows) < page_size:
            break
        offset += page_size
    return [{"date": d, "close": c} for d, c in sorted(by_date.items())]


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


@st.cache_data(ttl=120)
def fetch_todays_headlines(lookback_hours: int = 24) -> tuple:
    """Fetch all events from the last N hours across all tracked targets.
    Returns (events_list, sentiment_map) where sentiment_map is event_id -> {score, tag, desc}."""
    from datetime import datetime, timedelta, timezone
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).isoformat()
    sb = get_supabase()

    events = (
        sb.table("events")
        .select("id, target_id, headline, created_at")
        .gte("created_at", cutoff)
        .order("created_at", desc=True)
        .limit(300)
        .execute()
        .data or []
    )

    event_ids = [e["id"] for e in events if e.get("id")]
    sentiment_map: dict = {}
    if event_ids:
        sent_rows = (
            sb.table("sentiment")
            .select("event_id, sentiment_score, implication_tag, pros")
            .gte("created_at", cutoff)
            .limit(1000)
            .execute()
            .data or []
        )
        for s in sent_rows:
            eid = s.get("event_id")
            if eid and eid not in sentiment_map:
                pros_text = (s.get("pros") or "").strip()
                sentiment_map[eid] = {
                    "score": s.get("sentiment_score"),
                    "tag": s.get("implication_tag"),
                    "desc": pros_text[:160] if pros_text else "",
                }

    return events, sentiment_map


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
    # OpenAI fallback patterns when no real signal exists in the chatter
    "no direct quotes",
    "no quotes directly",
    "no quotes pertaining",
    "no relevant sentiment",
    "no chatter found",
    "found in the provided chatter",
    "found in the chatter",
    "regarding positive market sentiment",
    "regarding negative market sentiment",
)


def _text_is_placeholder(text: str) -> bool:
    """True if text is empty or a known placeholder / no-signal phrase."""
    if not text or not isinstance(text, str):
        return True
    s = text.strip().lower()
    if not s:
        return True
    # Catch any OpenAI "no signal" sentence starting with "no " or "none "
    _NO_SIGNAL_KEYWORDS = ("chatter", "found", "sentiment", "quotes", "information", "mention", "identified", "comments", "provided")
    if (s.startswith("no ") or s.startswith("none ")) and any(w in s[:150] for w in _NO_SIGNAL_KEYWORDS):
        return True
    # Always treat these phrases as placeholders, regardless of length
    for p in _LONG_PLACEHOLDER_PHRASES:
        if p in s:
            return True
    for p in _PLACEHOLDER_PHRASES:
        if p in s:
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
            if not _text_is_placeholder(line):
                all_pros.append(line)
        for line in _to_bullet_lines(s.get("cons") or ""):
            if not _text_is_placeholder(line):
                all_cons.append(line)
        quotes = (s.get("verbatim_quotes") or "").strip()
        url = (s.get("source_url") or "").strip()
        if quotes and not _text_is_placeholder(quotes):
            for line in _to_bullet_lines(quotes):
                # Skip lines where the AI put a URL as the quote text itself.
                # The source URL is already shown via the "View source →" link.
                if not line.startswith(("http://", "https://")):
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
    if os.getenv("OPENAI_API_KEY") and consolidate_bullet_points_with_ai:
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
def render_sidebar(targets: list, selected_target_id: Optional[int]) -> tuple:
    """Render sidebar. Returns (view, selected_target_id) where view is 'news' or 'analysis'."""
    with st.sidebar:
        st.markdown(
            '<p style="font-size:1rem;font-weight:700;color:#F5F5F7;letter-spacing:-0.02em;margin:0 0 4px 0;">Market Intelligence</p>'
            '<p style="font-size:0.75rem;color:#A1A1A6;margin:0 0 12px 0;">Powered by OpenAI · Supabase</p>',
            unsafe_allow_html=True,
        )
        st.divider()

        # ── Top-level navigation ───────────────────────────────
        view = st.radio("View", ["News Feed", "Analysis"], horizontal=True,
                        label_visibility="collapsed", key="sidebar_view")
        st.divider()

        companies = [t for t in targets if (t.get("target_type") or "").upper() == "COMPANY"]
        all_products = [t for t in targets if (t.get("target_type") or "").upper() == "PRODUCT"]

        if not companies and not all_products:
            st.caption("No targets yet. Add companies or products to get started.")
            st.divider()
            return view, None

        # ── Sector + F500 filters (Analysis only) ─────────────
        all_sectors = sorted({(t.get("sector") or "").strip() for t in companies if (t.get("sector") or "").strip()})
        if all_sectors:
            sel_sectors = st.multiselect("Sector", all_sectors, placeholder="All sectors", label_visibility="collapsed", key="sidebar_sector_filter")
        else:
            sel_sectors = []

        f500_only = st.checkbox("Fortune 500 only", key="sidebar_f500_filter")

        # Apply filters to company list
        if sel_sectors:
            companies = [c for c in companies if (c.get("sector") or "").strip() in sel_sectors]
        if f500_only:
            companies = [c for c in companies if c.get("is_f500")]

        company_ids = [c["id"] for c in companies]
        c_idx = company_ids.index(selected_target_id) if selected_target_id in company_ids else 0
        # If current selection is a product, pre-select its parent company
        if selected_target_id and selected_target_id not in company_ids:
            for p in all_products:
                if p.get("id") == selected_target_id and p.get("parent_target_id") in company_ids:
                    c_idx = company_ids.index(p["parent_target_id"])
                    break

        new_company_id = None
        new_product_id = None

        with st.expander("**Companies**", expanded=bool(companies)):
            if companies:
                c_labels = [c.get("name") or f"Target {c.get('id')}" for c in companies]
                sel_c = st.selectbox("Select company", range(len(c_labels)), format_func=lambda i: c_labels[i], index=c_idx, key="sidebar_companies", label_visibility="collapsed")
                new_company_id = company_ids[sel_c]
            else:
                st.caption("No companies yet.")

        products = [p for p in all_products if p.get("parent_target_id") == new_company_id] if new_company_id else all_products
        product_ids = [p["id"] for p in products]

        with st.expander("**Products**", expanded=bool(products)):
            if products:
                p_labels = [p.get("name") or f"Target {p.get('id')}" for p in products]
                p_idx = product_ids.index(selected_target_id) if selected_target_id in product_ids else 0
                sel_p = st.selectbox("Select product", range(len(p_labels)), format_func=lambda i: p_labels[i], index=p_idx, key="sidebar_products", label_visibility="collapsed")
                new_product_id = product_ids[sel_p]
            else:
                st.caption("No products linked to this company." if new_company_id else "No products yet.")

        prev_company = st.session_state.get("_sidebar_company_id")
        prev_product = st.session_state.get("_sidebar_product_id")
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
        return view, choice_id


# -----------------------------------------------------------------------------
# Main: target overview (hero with logo/initial + description)
# -----------------------------------------------------------------------------
def render_target_overview(target: dict, score_rows: Optional[list] = None) -> None:
    """Render target as a hero card: logo/initial, score ring, sparkline, momentum badges."""
    if not target:
        return
    name = target.get("name") or "Unnamed Target"
    description = target.get("description") or ""
    logo_url = _target_logo_url(target)
    initial = _target_initial(target)

    domain = target.get("domain") or (_domain_from_logo_url(logo_url) if logo_url else None)
    logo_bytes = _get_logo_bytes(logo_url, domain)
    target_type = (target.get("target_type") or "").upper()

    if logo_bytes:
        data_url = _logo_data_url(logo_bytes)
        logo_html = (
            f'<img src="{data_url}" width="72" height="72" '
            f'style="border-radius:14px;object-fit:contain;flex-shrink:0;" />'
        )
    else:
        logo_html = f'<div class="hero-initial">{_he(initial)}</div>'

    # Compute score, ring, momentum badges
    avg_score: Optional[int] = None
    badges = []
    if score_rows:
        recent_scores = [r.get("sentiment_score") for r in score_rows[-10:] if r.get("sentiment_score") is not None]
        if recent_scores:
            avg_score = round(sum(recent_scores) / len(recent_scores))
        momentum = _compute_momentum(score_rows)
        if momentum is not None:
            if momentum > 0:
                mc, ma, ml = "#16a34a", "↑", f"+{momentum} vs last 7d"
            elif momentum < 0:
                mc, ma, ml = "#dc2626", "↓", f"{momentum} vs last 7d"
            else:
                mc, ma, ml = "#6b7280", "→", "Stable"
            badges.append(
                f'<span class="score-pill" style="background:{mc};color:#fff;">{ma} {ml}</span>'
            )
        label_str = _score_label(avg_score) if avg_score is not None else ""
        if avg_score is not None:
            badges.append(
                f'<span style="font-size:0.78rem;font-weight:600;color:{_score_color(avg_score)};">'
                f'{label_str}</span>'
            )

    ring_html = _score_ring_html(avg_score, size=84)
    badge_html = f'<div class="badge-row">{"".join(badges)}</div>' if badges else ""
    type_html = f'<span class="hero-type">{_he(target_type)}</span>' if target_type else ""
    desc_html = f'<div class="hero-desc">{_he(description)}</div>' if description else ""

    # Inline 30-day sparkline at the bottom of the card
    spark_html = ""
    if score_rows:
        spark = _mini_sparkline_svg(score_rows, width=220, height=44)
        if spark:
            spark_html = (
                f'<div style="margin-top:20px;padding-top:16px;border-top:1px solid rgba(128,128,128,0.12);">'
                f'<div style="font-size:0.68rem;font-weight:700;color:#86868B;letter-spacing:0.08em;'
                f'text-transform:uppercase;margin-bottom:8px;">30-day trend</div>'
                f'{spark}'
                f'</div>'
            )

    inner = (
        f'<div style="flex:1;min-width:0;">'
        f'{type_html}'
        f'<div class="hero-name">{_he(name)}</div>'
        f'{badge_html}'
        f'</div>'
        f'{ring_html}'
    )
    row = f'<div style="display:flex;align-items:flex-start;gap:20px;">{logo_html}{inner}</div>'
    st.markdown(
        f'<div class="hero-card">{row}{desc_html}{spark_html}</div>',
        unsafe_allow_html=True,
    )


# -----------------------------------------------------------------------------
# Timeline: events and sentiment (expanders, 3 columns)
# -----------------------------------------------------------------------------
_DOMAIN_NAMES = {
    "news.ycombinator.com": "Hacker News",
    "ycombinator.com":      "Hacker News",
    "reddit.com":           "Reddit",
    "old.reddit.com":       "Reddit",
    "stackoverflow.com":    "Stack Overflow",
    "finance.yahoo.com":    "Yahoo Finance",
    "yahoo.com":            "Yahoo Finance",
    "reuters.com":          "Reuters",
    "bloomberg.com":        "Bloomberg",
    "techcrunch.com":       "TechCrunch",
    "wsj.com":              "Wall Street Journal",
    "ft.com":               "Financial Times",
    "cnbc.com":             "CNBC",
    "forbes.com":           "Forbes",
    "businessinsider.com":  "Business Insider",
    "theverge.com":         "The Verge",
    "wired.com":            "Wired",
    "arstechnica.com":      "Ars Technica",
    "venturebeat.com":      "VentureBeat",
    "seekingalpha.com":     "Seeking Alpha",
    "marketwatch.com":      "MarketWatch",
    "sec.gov":              "SEC EDGAR",
}


def _source_label(url: str) -> str:
    """Return a human-readable publication name for a URL."""
    if not url:
        return "Source"
    url = url.strip()
    if not url.startswith("http"):
        return "Source"
    try:
        netloc = (urlparse(url).netloc or "").strip().lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return _DOMAIN_NAMES.get(netloc) or netloc or "Source"
    except Exception:
        return "Source"


def render_event_card(event: dict, sentiments: list) -> None:
    """Render one event as an expander; prose/cons/quotes as a clean HTML grid inside."""
    headline = (event.get("headline") or "").strip() or "Untitled event"
    created = event.get("created_at")
    if created:
        try:
            dt = _parse_iso_dt(created) if isinstance(created, str) and "T" in created else created
            date_str = dt.strftime("%b %d, %Y") if hasattr(dt, "strftime") else str(created)
        except Exception:
            date_str = str(created)
    else:
        date_str = ""

    tag = _dominant_tag(sentiments)
    tag_prefix = f"{_TAG_META[tag]['emoji']} " if tag and tag in _TAG_META else ""
    label = f"{tag_prefix}{headline} — {date_str}" if date_str else f"{tag_prefix}{headline}"

    # Inject scoped CSS that gives this expander a colored left border by implication tag.
    # Uses CSS :has() (Chrome 105+, Safari 15.4+, Firefox 121+) to target the sibling expander.
    _TAG_BORDER = {
        "threat":      "#dc2626",
        "opportunity": "#16a34a",
        "monitor":     "#ca8a04",
        "no_action":   "#6b7280",
    }
    border_color = _TAG_BORDER.get(tag or "", "transparent")
    card_id = f"ec-{event.get('id', 'x')}"
    st.markdown(
        f'<style>.element-container:has(#{card_id}) + .element-container [data-testid="stExpander"]'
        f'{{border-left:4px solid {border_color} !important;border-radius:0 18px 18px 0 !important;}}</style>'
        f'<span id="{card_id}" style="display:none;"></span>',
        unsafe_allow_html=True,
    )

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

        # ── Price reaction block (public companies only) ──────────
        pr = fetch_price_reaction(event.get("id"))
        price_block_html = ""
        if pr and pr.get("price_at_event"):
            p0 = pr["price_at_event"]
            ticker = pr.get("ticker", "")
            conf = (pr.get("confidence") or "").lower()
            conf_reason = (pr.get("confidence_reason") or "").strip()
            session = (pr.get("market_session") or "").replace("_", " ").title()

            # Confidence styling
            conf_clr  = {"high": "#16a34a", "medium": "#ca8a04", "low": "#dc2626"}.get(conf, "#6b7280")
            conf_bg   = {"high": "rgba(22,163,74,0.10)", "medium": "rgba(202,138,4,0.10)", "low": "rgba(220,38,38,0.10)"}.get(conf, "rgba(107,114,128,0.08)")
            conf_icon = {"high": "●", "medium": "◑", "low": "○"}.get(conf, "○")

            # Build individual return cells
            def _ret_cell(label: str, val: Optional[float], primary: bool = False) -> str:
                if val is None:
                    return ""
                clr  = "#16a34a" if val > 0 else ("#dc2626" if val < 0 else "#6b7280")
                sign = "+" if val > 0 else ""
                size = "1rem" if primary else "0.8rem"
                weight = "800" if primary else "600"
                return (
                    f'<div style="display:flex;flex-direction:column;align-items:center;gap:2px;">'
                    f'<span style="font-size:{size};font-weight:{weight};color:{clr};">{sign}{val:.2f}%</span>'
                    f'<span style="font-size:0.63rem;font-weight:600;color:#86868B;text-transform:uppercase;letter-spacing:0.06em;">{label}</span>'
                    f'</div>'
                )

            cells = "".join(filter(None, [
                _ret_cell("1d return", pr.get("reaction_1d"), primary=True),
                _ret_cell("3d", pr.get("reaction_3d")),
                _ret_cell("7d", pr.get("reaction_7d")),
                _ret_cell("inter-event", pr.get("window_return_pct")),
            ]))

            conf_pill = (
                f'<span style="display:inline-flex;align-items:center;gap:5px;padding:3px 10px;'
                f'background:{conf_bg};border-radius:980px;font-size:0.72rem;font-weight:600;color:{conf_clr};">'
                f'{conf_icon} {conf.capitalize()} attribution confidence</span>'
            )
            reason_html = (
                f'<span style="font-size:0.72rem;color:#86868B;margin-left:6px;">{_he(conf_reason)}</span>'
                if conf_reason else ""
            )
            session_html = (
                f'<span style="font-size:0.72rem;color:#86868B;margin-left:8px;">· {_he(session)} session</span>'
                if session else ""
            )

            price_block_html = (
                f'<div style="margin:14px 0 10px 0;padding:14px 18px;'
                f'background:rgba(0,0,0,0.03);border-radius:14px;border:1px solid rgba(0,0,0,0.06);">'
                f'<div style="display:flex;align-items:center;gap:6px;margin-bottom:10px;">'
                f'<span style="font-size:0.7rem;font-weight:700;color:#86868B;letter-spacing:0.08em;text-transform:uppercase;">Price Impact · {_he(ticker)} ${p0:.2f}</span>'
                f'{session_html}'
                f'</div>'
                f'<div style="display:flex;align-items:flex-end;gap:24px;flex-wrap:wrap;margin-bottom:10px;">'
                f'{cells}'
                f'</div>'
                f'<div style="display:flex;align-items:center;flex-wrap:wrap;">'
                f'{conf_pill}{reason_html}'
                f'</div>'
                f'</div>'
            )

        st.markdown(
            f'<div class="pcc-badge-row">{"".join(badges)}</div>'
            + price_block_html,
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
                source_name = _source_label(url) if url else ""
                link = (
                    f'<a href="{url}" target="_blank" class="pcc-source-link">— {_he(source_name)}</a>'
                    if url else ""
                )
                parts.append(f'<div class="pcc-quote">{_he(quote)}{link}</div>')
            return "".join(parts)

        pros_col = f'<div><div class="pcc-label">Pros</div>{_build_bullets(agg["pros"])}</div>'
        cons_col = f'<div><div class="pcc-label">Cons</div>{_build_bullets(agg["cons"])}</div>'
        has_voice = bool(agg["voice"])
        voice_col = f'<div><div class="pcc-label">Voice of the Customer</div>{_build_quotes(agg["voice"])}</div>' if has_voice else ""
        grid_cols = "1fr 1fr 1fr" if has_voice else "1fr 1fr"
        st.markdown(
            f'<div class="pcc-grid" style="grid-template-columns:{grid_cols};">{pros_col}{cons_col}{voice_col}</div>',
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
            dt = _parse_iso_dt(raw)
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


def _render_price_chart(target_id: int, target: dict, events: list) -> None:
    """Price chart with event markers for public companies."""
    try:
        import altair as alt
        import pandas as pd
    except ImportError:
        st.caption("_Chart library not available._")
        return

    ticker = target.get("ticker", "")
    window = st.radio("Window", ["30d", "59d"], horizontal=True, key=f"price_win_{target_id}")
    days = 30 if window == "30d" else 59

    price_rows = fetch_price_series(target_id, days)
    if not price_rows:
        st.caption(f"_No price data yet for {ticker}. Run price_fetcher.py to populate._")
        return

    df = pd.DataFrame(price_rows)
    df["date"] = pd.to_datetime(df["date"])

    # Build event markers: one dot per event that falls in window
    cutoff_dt = df["date"].min()
    event_markers = []
    for e in events:
        ts = e.get("created_at", "")
        if not ts:
            continue
        try:
            dt = pd.to_datetime(ts[:10])
        except Exception:
            continue
        if dt >= cutoff_dt:
            event_markers.append({"date": dt, "headline": (e.get("headline") or "")[:60]})

    line = (
        alt.Chart(df)
        .mark_line(color="#0071E3", strokeWidth=2)
        .encode(
            x=alt.X("date:T", axis=alt.Axis(format="%b %d", labelAngle=-30, title="")),
            y=alt.Y("close:Q", scale=alt.Scale(zero=False), axis=alt.Axis(title=f"{ticker} close ($)")),
            tooltip=[alt.Tooltip("date:T", format="%b %d %Y"), alt.Tooltip("close:Q", title="Close", format="$.2f")],
        )
    )

    chart = line
    if event_markers:
        # Look up the close price on each event date so markers sit on the line
        price_by_date = {row["date"].strftime("%Y-%m-%d"): row["close"] for _, row in df.iterrows()}
        markers_with_price = [
            {**m, "close": price_by_date.get(m["date"].strftime("%Y-%m-%d"))}
            for m in event_markers
            if price_by_date.get(m["date"].strftime("%Y-%m-%d")) is not None
        ]
        if markers_with_price:
            df_ev = pd.DataFrame(markers_with_price)
            dots = (
                alt.Chart(df_ev)
                .mark_point(shape="triangle-up", size=120, filled=True, color="#FF9F0A")
                .encode(
                    x=alt.X("date:T"),
                    y=alt.Y("close:Q"),
                    tooltip=[alt.Tooltip("date:T", format="%b %d %Y"), alt.Tooltip("headline:N", title="Event")],
                )
            )
            chart = alt.layer(line, dots)

    st.altair_chart(
        chart.properties(height=280, background="transparent")
        .configure_view(strokeWidth=0)
        .configure_axis(grid=True, gridColor="#f0f0f0"),
        use_container_width=True,
    )
    if event_markers:
        st.caption(f"{ticker} daily close · orange markers = tracked events · {len(event_markers)} events in window")
    else:
        st.caption(f"{ticker} daily close · {days}-day window")


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


def render_news_tab(targets: list) -> None:
    """Global news feed: headlines for a selected date, newest first."""
    from datetime import datetime, timezone, timedelta, date as date_type

    st.markdown(
        '<div class="section-head">News Feed</div>'
        '<div class="section-sub">All tracked headlines for the selected day, newest first.</div>',
        unsafe_allow_html=True,
    )

    targets_by_id = {t["id"]: t for t in targets if t.get("id")}

    col_date, col_sector = st.columns([1, 2])
    with col_date:
        selected_date = st.date_input("Date", value=date_type.today(), max_value=date_type.today(), key="news_date_picker", label_visibility="collapsed")
    with col_sector:
        all_sectors = sorted({(t.get("sector") or "").strip() for t in targets if (t.get("sector") or "").strip()})
        sel_sectors = st.multiselect("Sector", all_sectors, placeholder="All sectors", key="news_sector_filter", label_visibility="collapsed")

    # Compute lookback in hours from start of selected date to end of it
    now_utc = datetime.now(timezone.utc)
    selected_start = datetime(selected_date.year, selected_date.month, selected_date.day, tzinfo=timezone.utc)
    selected_end = selected_start + timedelta(days=1)
    lookback_hours = max(1, int((now_utc - selected_start).total_seconds() // 3600) + 1)

    events, sentiment_map = fetch_todays_headlines(lookback_hours)
    # Narrow to the selected day window
    events = [e for e in events if selected_start <= _parse_iso_dt(e["created_at"]) < selected_end]

    if not events:
        st.info("No headlines tracked in the last 24 hours. Run the pipeline to fetch today's news.")
        return

    # Filter by sector if selected
    if sel_sectors:
        events = [e for e in events if (targets_by_id.get(e.get("target_id"), {}).get("sector") or "") in sel_sectors]

    if not events:
        st.caption("No headlines match the selected sector filter.")
        return

    tag_emoji = {"threat": "🔴", "opportunity": "🟢", "monitor": "🟡", "no_action": "⚪"}
    now = datetime.now(timezone.utc)

    for e in events:
        eid = e.get("id")
        target = targets_by_id.get(e.get("target_id"), {})
        company = target.get("name") or "Unknown"
        sector = (target.get("sector") or "").strip()
        headline = (e.get("headline") or "").strip() or "(no headline)"

        # Relative time
        try:
            evt_dt = _parse_iso_dt(e["created_at"])
            delta = now - evt_dt
            hours = int(delta.total_seconds() // 3600)
            mins = int((delta.total_seconds() % 3600) // 60)
            age = f"{hours}h ago" if hours > 0 else f"{mins}m ago"
        except Exception:
            age = ""

        sent = sentiment_map.get(eid, {})
        score = sent.get("score")
        tag = sent.get("tag") or ""
        desc = sent.get("desc") or ""

        # Score color
        score_color = "#6b7280"
        if score is not None:
            if score >= 7: score_color = "#16a34a"
            elif score >= 3: score_color = "#65a30d"
            elif score <= -7: score_color = "#dc2626"
            elif score <= -3: score_color = "#ea580c"

        score_badge = (
            f'<span style="background:{score_color};color:#fff;font-size:0.72rem;'
            f'font-weight:700;padding:2px 8px;border-radius:20px;">'
            f'{score:+d}</span>' if score is not None else ""
        )
        tag_badge = (
            f'<span style="font-size:0.8rem;margin-left:4px;">{tag_emoji.get(tag, "")} {tag}</span>'
            if tag else ""
        )
        sector_pill = (
            f'<span style="font-size:0.72rem;color:#A1A1A6;background:rgba(255,255,255,0.06);'
            f'padding:2px 8px;border-radius:20px;margin-left:6px;">{_he(sector)}</span>'
            if sector else ""
        )

        st.markdown(
            f'<div style="border:1px solid rgba(255,255,255,0.08);border-radius:12px;'
            f'padding:14px 18px;margin-bottom:10px;background:rgba(255,255,255,0.03);">'
            f'<div style="display:flex;align-items:center;gap:6px;margin-bottom:6px;">'
            f'<span style="font-size:0.82rem;font-weight:700;color:#F5F5F7;">{_he(company)}</span>'
            f'{sector_pill}'
            f'<span style="margin-left:auto;font-size:0.72rem;color:#6b7280;">{age}</span>'
            f'</div>'
            f'<div style="font-size:0.92rem;font-weight:600;color:#E5E5EA;margin-bottom:6px;">{_he(headline)}</div>'
            f'<div style="display:flex;align-items:center;gap:6px;">{score_badge}{tag_badge}</div>'
            + (f'<div style="font-size:0.8rem;color:#A1A1A6;margin-top:8px;line-height:1.5;">{_he(desc)}</div>' if desc else "")
            + f'</div>',
            unsafe_allow_html=True,
        )


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
    for t in [t for t in targets if (t.get("target_type") or "").upper() == "COMPANY"]:
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

    _MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}
    html_rows = []
    for i, r in enumerate(rows_sorted, 1):
        if r["avg_score"] is not None:
            color = _score_color(r["avg_score"])
            score_cell = (
                f'<span class="score-pill" style="background:{color};color:#fff;">'
                f'{r["avg_score"]:+d} {_score_label(r["avg_score"])}</span>'
            )
            bar_pct = round((r["avg_score"] + 10) / 20 * 100)
            bar_html = (
                f'<div class="rank-bar-track">'
                f'<div style="height:100%;width:{bar_pct}%;background:{color};border-radius:3px;"></div>'
                f'</div>'
            )
        else:
            score_cell = '<span class="rank-meta">—</span>'
            bar_html = ""

        m = r["momentum"]
        if m is None:
            trend_html = '<span class="rank-meta">—</span>'
        elif m > 0:
            trend_html = f'<span style="color:#16a34a;font-weight:600;font-size:0.82rem;">↑ +{m}</span>'
        elif m < 0:
            trend_html = f'<span style="color:#dc2626;font-weight:600;font-size:0.82rem;">↓ {m}</span>'
        else:
            trend_html = '<span class="rank-meta">→ 0</span>'

        rank_cell = (
            f'<span class="rank-medal">{_MEDALS[i]}</span>'
            if i in _MEDALS
            else f'<span class="rank-num">{i}</span>'
        )

        html_rows.append(
            f'<div class="rank-row">'
            f'{rank_cell}'
            f'<div class="rank-name-wrap">'
            f'<div class="rank-name">{_he(r["name"])}</div>'
            f'<div style="display:flex;align-items:center;gap:8px;">'
            f'<div class="rank-type">{_he(r["type"])}</div>'
            f'{bar_html}'
            f'</div>'
            f'</div>'
            f'<div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap;">'
            f'{score_cell}{trend_html}'
            f'<span class="rank-meta">{r["events"]} events</span>'
            f'<span class="rank-meta">{r["readings"]} readings</span>'
            f'</div>'
            f'</div>'
        )

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

    # Gradient mesh background blobs
    st.markdown(
        '<div class="mesh-blob mesh-b1"></div>'
        '<div class="mesh-blob mesh-b2"></div>'
        '<div class="mesh-blob mesh-b3"></div>',
        unsafe_allow_html=True,
    )

    if "selected_target_id" not in st.session_state:
        st.session_state["selected_target_id"] = None

    try:
        targets = fetch_targets()
        st.session_state["_targets_by_id"] = {t["id"]: t for t in targets if t.get("id")}
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

    view, selected_id = render_sidebar(targets, st.session_state["selected_target_id"])
    st.session_state["selected_target_id"] = selected_id

    # Sticky page header
    target_name_for_header = next(
        (t.get("name") for t in targets if t.get("id") == selected_id), None
    ) if selected_id else None
    sep_html = (
        f'<span class="ph-sep">/</span><span class="ph-target">{_he(target_name_for_header)}</span>'
        if target_name_for_header else ""
    )
    st.markdown(
        f'<div class="page-header">'
        f'<span class="ph-title">Market Intelligence</span>'
        f'{sep_html}'
        f'<div class="ph-live"><div class="live-dot"></div>Live</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    if view == "News Feed":
        render_news_tab(targets)
        return

    tab_dive, tab_compare, tab_rank, tab_brief = st.tabs(["Deep Dive", "Compare", "Rankings", "Weekly Brief"])

    with tab_dive:
        if selected_id is None:
            st.info("Select a company or product in the sidebar.")
        else:
            target = fetch_target_by_id(selected_id)
            score_rows = fetch_all_sentiment_scores_for_target(selected_id)
            render_target_overview(target, score_rows)

            if score_rows:
                with st.expander("Sentiment Trend", expanded=False):
                    render_trend_chart(score_rows, target.get("name") or "")

            # Price chart (public companies only)
            if target and target.get("ticker"):
                with st.expander(f"Price Chart — {target['ticker']}", expanded=False):
                    _render_price_chart(selected_id, target, fetch_events_for_target(selected_id))

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
                # Always run dedupe_lines so stored summary text (which is never deduplicated)
                # gets the same near-duplicate filtering as freshly aggregated rows.
                pros_display = _dedupe_lines(_to_bullet_lines(summary["pros"] or "")) if has_summary else agg["pros"]
                cons_display = _dedupe_lines(_to_bullet_lines(summary["cons"] or "")) if has_summary else agg["cons"]
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
