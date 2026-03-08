"""
Resolve company name to official website domain using Gemini.
Only companies have domains; products do not. Supports single (Scout) and batch (script) resolution.
"""
import re
from typing import Dict, List, Optional

from config import get_model
from normalize import guess_domain

# Max names per batch to stay under token limits
BATCH_SIZE = 40


def _normalize_domain(raw: str) -> Optional[str]:
    """Extract a clean domain from AI response (e.g. 'https://apple.com' -> apple.com)."""
    if not raw or not isinstance(raw, str):
        return None
    s = raw.strip().lower().split("\n")[0].strip()
    for prefix in ("https://", "http://", "www."):
        if s.startswith(prefix):
            s = s[len(prefix) :].strip()
    if s.startswith("www."):
        s = s[4:].strip()
    s = s.split("/")[0].split("?")[0].strip()
    if not s or " " in s or "." not in s or len(s) < 4:
        return None
    return s if re.match(r"^[a-z0-9][a-z0-9.-]*\.[a-z]{2,}$", s) else None


def _parse_batch_response(text: str, names: List[str]) -> Dict[str, str]:
    """Parse AI response: lines like 'Company Name | domain.com'. Returns name -> domain for names in list."""
    result = {}
    names_normalized = {n.strip(): n.strip() for n in names if n and n.strip()}
    for line in (text or "").strip().split("\n"):
        line = line.strip()
        if not line or "|" not in line:
            continue
        parts = line.split("|", 1)
        if len(parts) != 2:
            continue
        name_part = parts[0].strip()
        domain = _normalize_domain(parts[1])
        if not domain:
            continue
        # Match to requested name (exact, or case-insensitive, or substring)
        matched = None
        for key in names_normalized:
            if key in result:
                continue
            if key == name_part or key.lower() == name_part.lower():
                matched = key
                break
            if name_part.lower() in key.lower() or key.lower() in name_part.lower():
                matched = key
                break
        if matched:
            result[matched] = domain
    return result


def resolve_domains_batch(names: List[str], use_ai: bool = True) -> Dict[str, str]:
    """
    Resolve many company names to domains in one (or few) Gemini call(s).
    Returns dict: company_name -> domain. Missing/invalid entries fall back to guess_domain(name).
    """
    if not names:
        return {}
    names = [n.strip() for n in names if n and n.strip()]
    result = {}

    if use_ai:
        for i in range(0, len(names), BATCH_SIZE):
            batch = names[i : i + BATCH_SIZE]
            try:
                model = get_model()
                prompt = (
                    "For each company below, give its official website domain. "
                    "Reply with exactly one line per company: Company Name | domain.com "
                    "(use the same company name as in the list). No URLs, no explanation.\n\n"
                    "Companies:\n" + "\n".join(batch)
                )
                response = model.generate_content(prompt)
                raw = (response.text or "").strip()
                parsed = _parse_batch_response(raw, batch)
                for n in batch:
                    result[n] = parsed.get(n) or guess_domain(n)
            except Exception:
                for n in batch:
                    result[n] = guess_domain(n)
    else:
        for n in names:
            result[n] = guess_domain(n)
    return result


def resolve_domain(name: str, target_type: str = "company", use_ai: bool = True) -> str:
    """
    Resolve a single company name to domain (e.g. for Scout when creating one company).
    Only use for companies; for products, domain is not set. Falls back to guess_domain on failure.
    """
    if not name or not isinstance(name, str):
        return guess_domain(name or "")
    if use_ai:
        try:
            model = get_model()
            prompt = (
                "What is the official website domain for this company? "
                "Reply with ONLY the domain, e.g. apple.com or netchoice.org — no explanation, no URL, no quotes. "
                f"Name: {name.strip()}"
            )
            response = model.generate_content(prompt)
            domain = _normalize_domain((response.text or "").strip())
            if domain:
                return domain
        except Exception:
            pass
    return guess_domain(name)
