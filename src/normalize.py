"""
Shared name normalization for targets: detect duplicates like "M4 iPad Air" vs "iPad Air M4"
or "Fire TV app" vs "Fire TV app (redesigned)".
"""
import re

# Trailing words that name a legal wrapper rather than the business, so
# "Meta Platforms" and "Meta" are one company rather than two targets — which
# is how a second Meta arrived with no ticker and split its sentiment.
CORPORATE_SUFFIXES = {
    "inc", "incorporated", "corp", "corporation", "co", "company", "ltd",
    "limited", "llc", "lp", "plc", "sa", "ag", "nv", "ab", "oyj", "spa",
    "holding", "holdings", "group", "platforms", "technologies", "systems",
}


def _strip_corporate_suffixes(words: list) -> list:
    """Drop trailing legal-wrapper words, keeping at least one word."""
    while len(words) > 1 and words[-1] in CORPORATE_SUFFIXES:
        words = words[:-1]
    return words


def normalize_target_name(name: str) -> str:
    """
    Normalize a target name for duplicate detection.
    - Lowercase
    - Strip parentheticals and their content, e.g. "(redesigned)" or "(2026)"
    - Drop trailing corporate suffixes, so "Meta Platforms" == "Meta"
    - Remove punctuation, split into words, sort, rejoin
    So "M4 iPad Air" and "iPad Air M4" both become "air ipad m4";
    "Fire TV app (redesigned)" and "Fire TV app" both become "app fire tv".
    """
    if not name or not isinstance(name, str):
        return ""
    s = name.strip().lower()
    # Remove parentheticals and their content (e.g. " (redesigned)", "(2026)")
    s = re.sub(r"\s*\([^)]*\)", "", s)
    # Keep only word chars and spaces
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    words = s.split() if s else []
    # Suffixes are positional, so strip before sorting.
    words = _strip_corporate_suffixes(words)
    # Sort words so word order doesn't create duplicates
    return " ".join(sorted(words))


def guess_domain(name: str) -> str:
    """Guess a likely domain from target name: lowercase, alphanumeric only, then .com."""
    if not name or not isinstance(name, str):
        return ""
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]", "", s)
    return f"{s}.com" if s else ""
