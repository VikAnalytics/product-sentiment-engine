"""
Shared logic for splitting and deduping pros/cons (and verbatim) text.
Used by the dashboard (app.py) and by the DB backfill script (scripts/dedupe_sentiment_in_db.py).
"""
import re

# Stopwords for similarity: ignore common words so "NET is beneficial" matches ".NET beneficial skill"
DEDUPE_STOPWORDS = frozenset(
    "a an the and or but is are was were be been being have has had do does did will would "
    "could should may might must shall can to of in for on with at by from as into through "
    "during before after above below between under again further then once here there when "
    "where why how all each few more most other some such no nor not only own same so than "
    "too very just also now it its this that these those i you he she we they".split()
)


def normalize_for_dedupe(text: str) -> str:
    """Lowercase, strip punctuation, collapse spaces — for similarity check."""
    if not text:
        return ""
    s = (text or "").strip().lower()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def significant_words(text: str) -> set:
    """Token set from normalized text, minus stopwords. Used to detect same-idea lines."""
    norm = normalize_for_dedupe(text)
    if not norm:
        return set()
    words = set(norm.split())
    return words - DEDUPE_STOPWORDS


def line_similarity(line_a: str, line_b: str, min_overlap: float = 0.55) -> bool:
    """True if the two lines express the same idea (high word overlap). Keeps one, drop the other."""
    wa, wb = significant_words(line_a), significant_words(line_b)
    if not wa or not wb:
        return False
    overlap = len(wa & wb) / min(len(wa), len(wb))
    return overlap >= min_overlap


def dedupe_lines(lines: list) -> list:
    """Drop duplicates and near-duplicates: substring containment + same-idea (word overlap). Keeps one per idea, preferring longer."""
    if not lines:
        return []
    with_key = [(normalize_for_dedupe(l), l) for l in lines if (l or "").strip()]
    with_key.sort(key=lambda x: len(x[0]), reverse=True)  # longer first so we keep the most complete
    seen_keys = []
    result = []
    for key, original in with_key:
        if not key:
            continue
        is_dup = False
        for sk in seen_keys:
            if key in sk or sk in key:
                is_dup = True
                break
        if not is_dup:
            for kept in result:
                if line_similarity(original, kept):
                    is_dup = True
                    break
        if is_dup:
            continue
        seen_keys.append(key)
        result.append(original.strip())
    return result


def to_bullet_lines(text: str) -> list:
    """Split insight text into list of non-empty lines for bullet display.
    Handles newlines, pipe, bullet chars, and long single-line text (sentence split)."""
    if not text or not isinstance(text, str):
        return []
    raw = text.strip()
    if not raw:
        return []
    lines = []
    for part in raw.replace("\r\n", "\n").split("\n"):
        for sub in part.split(" | "):
            sub = sub.strip()
            for prefix in ("•", "-", "*", "–", "—"):
                if sub.startswith(prefix):
                    sub = sub.lstrip(prefix).strip()
            if sub and sub.lower() not in ("none", "n/a", "none found", "."):
                lines.append(sub)
    result = []
    for line in lines:
        if len(line) > 100 and ". " in line:
            parts = []
            for sent in line.split(". "):
                sent = sent.strip()
                if not sent:
                    continue
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


def dedupe_pros_cons_text(pros: str, cons: str) -> tuple:
    """
    Given raw pros and cons strings (as stored in DB), return (new_pros, new_cons)
    with redundant lines removed. Uses to_bullet_lines + dedupe_lines; joins with newline.
    """
    pros_lines = to_bullet_lines(pros or "")
    cons_lines = to_bullet_lines(cons or "")
    new_pros = "\n".join(dedupe_lines(pros_lines)).strip() if pros_lines else (pros or "").strip()
    new_cons = "\n".join(dedupe_lines(cons_lines)).strip() if cons_lines else (cons or "").strip()
    return new_pros, new_cons
