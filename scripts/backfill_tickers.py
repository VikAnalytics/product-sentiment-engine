"""
Backfill stock tickers for tracked companies.

Only 51 of 480 tracked companies had a ticker, which caps two things hard: the
simulator can only ever pick from names that have price data, and price_correlator
can only attribute a move for events on those names. Many of the rest are genuinely
private (Anthropic, Stripe, Anduril), so the job is to find the public ones without
inventing tickers for the private ones.

Two stages, because an LLM alone will confidently hallucinate a symbol:
  1. Ask the model for a ticker, in batches, allowing "PRIVATE" as an answer.
  2. Verify every proposed ticker against yfinance and keep only symbols that
     return real price history whose company name plausibly matches.

Usage:
    PYTHONPATH=src python scripts/backfill_tickers.py --dry-run
    PYTHONPATH=src python scripts/backfill_tickers.py
    PYTHONPATH=src python scripts/backfill_tickers.py --limit 50
"""
import argparse
import logging
import os
import re
import sys
import time
from typing import Dict, List, Optional

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_src = os.path.join(_root, "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from config import get_model, get_supabase, fetch_all_rows  # noqa: E402

log = logging.getLogger("backfill_tickers")

BATCH_SIZE = 40
VERIFY_DELAY_SEC = 0.4

# Symbols the model reaches for when it is guessing rather than recalling.
_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,6}$")


def _clean_ticker(raw: str) -> Optional[str]:
    """Normalize a model-proposed ticker, or None when it is not ticker-shaped."""
    if not raw:
        return None
    s = raw.strip().upper().split("\n")[0].strip()
    s = s.strip("`'\"()[]").replace("$", "").strip()
    if not s or s in {"PRIVATE", "NONE", "N/A", "NA", "UNKNOWN", "-"}:
        return None
    # Strip an exchange prefix such as "NASDAQ: AAPL".
    if ":" in s:
        s = s.split(":", 1)[1].strip()
    return s if _TICKER_RE.match(s) else None


def _ask_model(names: List[str]) -> Dict[str, str]:
    """Ask for tickers for one batch. Returns name -> raw ticker string."""
    listing = "\n".join(f"- {n}" for n in names)
    prompt = f"""You map company names to their primary stock ticker.

For each company below, reply with one line:
Company Name | TICKER

Rules:
- Use the ticker of the primary US listing where one exists (AAPL, MSFT, NVDA).
- If the company is a subsidiary, use the ticker of the listed parent.
- If the company is private, state-owned, a non-profit, a government agency, or
  you are not confident, reply PRIVATE. A wrong ticker is far worse than PRIVATE.
- Output only the lines, no preamble and no commentary.

Companies:
{listing}
"""
    resp = get_model().generate_content(prompt)
    text = (getattr(resp, "text", "") or "").strip()

    # Models sometimes wrap the answer in a code fence or add a lead-in line.
    text = re.sub(r"^```[a-z]*\n?|```$", "", text, flags=re.MULTILINE).strip()

    out: Dict[str, str] = {}
    private = 0
    by_lower = {n.lower(): n for n in names}
    for line in text.split("\n"):
        line = line.strip().lstrip("-*0123456789. ").strip()
        if not line:
            continue
        # "Name | TICKER" is what we ask for; tolerate a dash or tab separator.
        parts = re.split(r"\s*[|\t]\s*|\s+-\s+", line, maxsplit=1)
        if len(parts) != 2:
            continue
        left, right = parts
        key = left.strip().strip("-").strip().lower()
        name = by_lower.get(key)
        if name is None:  # tolerate light reformatting of the name
            for cand_lower, cand in by_lower.items():
                if cand_lower in key or key in cand_lower:
                    name = cand
                    break
        if name is None:
            continue
        proposed = _clean_ticker(right)
        if not proposed:
            private += 1
            continue
        if name not in out:
            out[name] = proposed

    # Every name coming back PRIVATE is a normal, common outcome. Parsing nothing
    # at all is not, and used to look identical from the outside.
    if not out and not private:
        log.warning("  parsed nothing from this batch; raw response began: %r", text[:200])
    return out


_SUFFIXES = {
    "inc", "inc.", "corp", "corp.", "corporation", "co", "co.", "company",
    "plc", "ltd", "ltd.", "limited", "holdings", "holding", "group", "sa", "nv",
    "ag", "se", "the", "technologies", "technology", "systems", "international",
    "&", "and", "class", "a", "b",
}


def _name_tokens(name: str) -> set:
    cleaned = re.sub(r"[^a-z0-9 ]+", " ", (name or "").lower())
    return {t for t in cleaned.split() if t and t not in _SUFFIXES}


def _acronym(tokens_in_order: List[str]) -> str:
    return "".join(t[0] for t in tokens_in_order if t)


def _ordered_tokens(name: str) -> List[str]:
    cleaned = re.sub(r"[^a-z0-9 ]+", " ", (name or "").lower())
    return [t for t in cleaned.split() if t and t not in _SUFFIXES]


def _names_match(company: str, listed: str) -> bool:
    """
    True when a listed security's name plausibly refers to the same company.

    Checking only that a symbol exists is no check at all: the model proposed
    NVDA for Arm, and NVDA is perfectly real. But a plain word overlap is too
    strict in the other direction, because companies trade under names the world
    does not use for them, so also accept an acronym ("TSMC" for Taiwan
    Semiconductor Manufacturing) or a spacing difference ("Supermicro" for Super
    Micro Computer).
    """
    a_tokens, b_tokens = _ordered_tokens(company), _ordered_tokens(listed)
    if not a_tokens or not b_tokens:
        return False

    a, b = set(a_tokens), set(b_tokens)
    if len(a & b) / min(len(a), len(b)) >= 0.5:
        return True

    # Spacing differences: "Supermicro" against "Super Micro Computer", or a
    # consumer brand against its legal entity, "Snapchat" against "Snap".
    a_joined, b_joined = "".join(a_tokens), "".join(b_tokens)
    shorter, longer = sorted((a_joined, b_joined), key=len)
    if len(shorter) >= 4 and longer.startswith(shorter):
        return True

    # Initialisms: "TSMC" against Taiwan Semiconductor Manufacturing Company.
    # Built from the raw words too, since the acronym usually counts the very
    # suffixes ("Company", "Group") that token matching strips out.
    # A prefix rather than an exact hit, because the legal name usually carries
    # trailing words the initialism drops: Taiwan Semiconductor Manufacturing
    # Company *Limited* acronyms to TSMCL, and the company is called TSMC.
    a_all = re.sub(r"[^a-z0-9 ]+", " ", company.lower()).split()
    b_all = re.sub(r"[^a-z0-9 ]+", " ", listed.lower()).split()

    def _is_initialism(short: List[str], full_variants: List[List[str]]) -> bool:
        if len(short) != 1 or len(short[0]) < 2:
            return False
        return any(_acronym(v).startswith(short[0]) for v in full_variants if len(v) > 1)

    if _is_initialism(a_tokens, [b_tokens, b_all]):
        return True
    if _is_initialism(b_tokens, [a_tokens, a_all]):
        return True

    return False


def _verify(ticker: str, company: str) -> bool:
    """True when the symbol is real, currently priced, and names the same company."""
    try:
        import yfinance as yf

        handle = yf.Ticker(ticker)
        # Yahoo throttles bursts, and a throttled reply is an empty frame rather
        # than an error, which is indistinguishable from a delisted symbol. Retry
        # once before concluding the symbol is dead.
        hist = handle.history(period="5d")
        if hist is None or hist.empty:
            time.sleep(2.0)
            handle = yf.Ticker(ticker)
            hist = handle.history(period="5d")
        if hist is None or hist.empty:
            log.info("  reject %-6s %-30s no price history", ticker, company[:30])
            return False

        try:
            info = handle.info or {}
        except Exception:
            info = {}
        listed = (info.get("longName") or info.get("shortName") or "").strip()
        if not listed:
            log.info("  reject %-6s %-30s no listed name to check against", ticker, company[:30])
            return False
        if not _names_match(company, listed):
            log.info("  reject %-6s %-30s resolves to %r", ticker, company[:30], listed[:40])
            return False
        return True
    except Exception as exc:
        log.info("  reject %-6s %-30s lookup failed: %s", ticker, company[:30], exc)
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="resolve and verify, write nothing")
    ap.add_argument("--limit", type=int, default=0, help="only process this many companies")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    sb = get_supabase()
    companies = fetch_all_rows(
        lambda: sb.table("targets")
        .select("id, name, ticker")
        .eq("target_type", "COMPANY")
        .eq("status", "tracking")
    )
    missing = [c for c in companies if not (c.get("ticker") or "").strip()]
    if args.limit:
        missing = missing[: args.limit]

    have = len(companies) - len([c for c in companies if not (c.get("ticker") or "").strip()])
    log.info("companies tracked: %d, with ticker: %d, missing: %d",
             len(companies), have, len(companies) - have)
    if not missing:
        log.info("nothing to do")
        return 0
    log.info("resolving %d company name(s) in batches of %d\n", len(missing), BATCH_SIZE)

    by_name = {c["name"]: c for c in missing if c.get("name")}
    proposed: Dict[str, str] = {}
    names = list(by_name)
    for i in range(0, len(names), BATCH_SIZE):
        batch = names[i : i + BATCH_SIZE]
        try:
            got = _ask_model(batch)
        except Exception as exc:
            log.warning("batch %d failed: %s", i // BATCH_SIZE + 1, exc)
            continue
        proposed.update(got)
        log.info("batch %d/%d: %d proposed",
                 i // BATCH_SIZE + 1, (len(names) + BATCH_SIZE - 1) // BATCH_SIZE, len(got))

    log.info("\nverifying %d proposed ticker(s) against yfinance", len(proposed))
    confirmed: Dict[str, str] = {}
    for name, ticker in sorted(proposed.items()):
        if _verify(ticker, name):
            confirmed[name] = ticker
            log.info("  ok     %-6s %s", ticker, name[:40])
        time.sleep(VERIFY_DELAY_SEC)

    log.info(
        "\nconfirmed %d of %d proposed, %d company(s) left without a ticker",
        len(confirmed), len(proposed), len(missing) - len(confirmed),
    )

    if args.dry_run:
        log.info("dry run, nothing written")
        return 0

    written = 0
    for name, ticker in confirmed.items():
        target = by_name.get(name)
        if not target:
            continue
        try:
            sb.table("targets").update({"ticker": ticker}).eq("id", target["id"]).execute()
            written += 1
        except Exception as exc:
            log.warning("  write failed for %s (%s): %s", name, ticker, exc)

    log.info("wrote %d ticker(s)", written)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
