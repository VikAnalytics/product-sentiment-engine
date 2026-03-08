"""
Shared name normalization for targets: detect duplicates like "M4 iPad Air" vs "iPad Air M4"
or "Fire TV app" vs "Fire TV app (redesigned)".
"""
import re


def normalize_target_name(name: str) -> str:
    """
    Normalize a target name for duplicate detection.
    - Lowercase
    - Strip parentheticals and their content, e.g. "(redesigned)" or "(2026)"
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
    # Sort words so word order doesn't create duplicates
    words = sorted(s.split()) if s else []
    return " ".join(words)


def guess_domain(name: str) -> str:
    """Guess a likely domain from target name: lowercase, alphanumeric only, then .com."""
    if not name or not isinstance(name, str):
        return ""
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]", "", s)
    return f"{s}.com" if s else ""
