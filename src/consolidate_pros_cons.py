"""
Use Gemini to consolidate pros or cons: merge similar points and keep only distinct differentiators.
Used by the backfill script to clean existing sentiment; can also be used when writing new sentiment.
"""
from config import get_model

# Cap input size to stay within model context; consolidation is best when there's clear redundancy
MAX_CONSOLIDATE_CHARS = 3500


def consolidate_bullet_points_with_ai(lines: list, field_label: str = "points") -> list:
    """
    Given a list of bullet points (pros or cons), ask the model to return only distinct
    differentiators: merge points that say the same thing, drop redundancy, one clear line per idea.

    Returns a list of consolidated lines. If input is empty or has 0-1 lines, returns as-is.
    """
    lines = [str(l).strip() for l in lines if (l or "").strip()]
    if len(lines) <= 1:
        return lines
    text = "\n".join(lines)
    if len(text) > MAX_CONSOLIDATE_CHARS:
        text = text[:MAX_CONSOLIDATE_CHARS] + "\n[... truncated for length ...]"
    prompt = f"""Role: Act as a data synthesis and editing expert.

Task: Below is a list of statements that can contain redundant information, often repeating the same facts in different ways. Your goal is to consolidate this into a clean, concise list of unique points.

Rules:

Identify Core Claims: Break the text down into its fundamental facts or claims.

Remove Redundancy: Merge or delete statements that convey the same meaning. If multiple sentences describe the same fact, keep only the most clear, comprehensive version of that fact.

Preserve Uniqueness: Ensure that every statement in the final output is semantically distinct from the others. No two statements should explain the same concept.

Output format: One unique point per line. No numbering, no bullets, no extra commentary. Only the consolidated lines.

Input {field_label}:
{text}

Consolidated {field_label} (unique points only, one per line):"""
    try:
        model = get_model()
        response = model.generate_content(prompt)
        raw = (response.text or "").strip()
        if not raw:
            return lines
        out = []
        for line in raw.replace("\r\n", "\n").split("\n"):
            line = line.strip()
            for prefix in ("•", "-", "*", "–", "—", "1.", "2.", "3.", "4.", "5."):
                if line.startswith(prefix):
                    line = line[len(prefix):].strip()
                    break
            if line and line.lower() not in ("none", "n/a", "."):
                out.append(line)
        return out if out else lines
    except Exception:
        return lines


def _parse_consolidated_lines(raw: str) -> list:
    """Parse model output into list of non-empty lines (strip bullets/numbers)."""
    out = []
    for line in (raw or "").replace("\r\n", "\n").split("\n"):
        line = line.strip()
        for prefix in ("•", "-", "*", "–", "—", "1.", "2.", "3.", "4.", "5."):
            if line.startswith(prefix):
                line = line[len(prefix):].strip()
                break
        if line and line.lower() not in ("none", "n/a", "."):
            out.append(line)
    return out


def consolidate_pros_and_cons_single_call(pros_lines: list, cons_lines: list) -> tuple:
    """
    One API call: consolidate both pros and cons in a single prompt. Returns (pros_str, cons_str).
    Use this in backfill to halve API usage (1 call per target instead of 2).
    """
    pros_lines = [str(l).strip() for l in pros_lines if (l or "").strip()]
    cons_lines = [str(l).strip() for l in cons_lines if (l or "").strip()]
    if not pros_lines and not cons_lines:
        return "", ""
    if len(pros_lines) <= 1 and len(cons_lines) <= 1:
        return "\n".join(pros_lines).strip(), "\n".join(cons_lines).strip()
    pros_text = "\n".join(pros_lines) if pros_lines else "(none)"
    cons_text = "\n".join(cons_lines) if cons_lines else "(none)"
    if len(pros_text) + len(cons_text) > MAX_CONSOLIDATE_CHARS * 2:
        pros_text = pros_text[:MAX_CONSOLIDATE_CHARS] + "\n[... truncated ...]" if len(pros_text) > MAX_CONSOLIDATE_CHARS else pros_text
        cons_text = cons_text[:MAX_CONSOLIDATE_CHARS] + "\n[... truncated ...]" if len(cons_text) > MAX_CONSOLIDATE_CHARS else cons_text
    prompt = f"""Role: Act as a data synthesis and editing expert.

Task: Below are two lists (PROS and CONS) that can contain redundant information. Consolidate each into a clean, concise list of unique points.

Rules: Identify core claims. Remove redundancy—if multiple sentences describe the same fact, keep only the clearest version. Preserve uniqueness—no two statements should explain the same concept. Output format: one unique point per line.

Reply with exactly two sections in this format (use these headers):

PROS:
<consolidated pros, one per line>

CONS:
<consolidated cons, one per line>

Input PROS:
{pros_text}

Input CONS:
{cons_text}

Your reply (PROS: then CONS:):"""
    try:
        model = get_model()
        response = model.generate_content(prompt)
        raw = (response.text or "").strip()
        if not raw:
            return "\n".join(pros_lines).strip(), "\n".join(cons_lines).strip()
        pros_out, cons_out = [], []
        section = None
        for line in raw.replace("\r\n", "\n").split("\n"):
            line_stripped = line.strip()
            if line_stripped.upper().startswith("PROS:"):
                section = "pros"
                rest = line_stripped[5:].strip()
                if rest:
                    pros_out.extend(_parse_consolidated_lines(rest))
                continue
            if line_stripped.upper().startswith("CONS:"):
                section = "cons"
                rest = line_stripped[5:].strip()
                if rest:
                    cons_out.extend(_parse_consolidated_lines(rest))
                continue
            if section == "pros" and line_stripped:
                pros_out.extend(_parse_consolidated_lines(line_stripped))
            elif section == "cons" and line_stripped:
                cons_out.extend(_parse_consolidated_lines(line_stripped))
        new_pros = "\n".join(pros_out).strip() if pros_out else ""
        new_cons = "\n".join(cons_out).strip() if cons_out else ""
        return new_pros, new_cons
    except Exception:
        return "\n".join(pros_lines).strip(), "\n".join(cons_lines).strip()


def consolidate_pros_cons_with_ai(pros: str, cons: str) -> tuple:
    """
    Given raw pros and cons strings (as stored in DB), split into lines, run AI consolidation
    on each, return (new_pros, new_cons) as newline-joined strings. Uses 2 API calls.
    """
    from sentiment_dedupe import to_bullet_lines
    pros_lines = to_bullet_lines(pros or "")
    cons_lines = to_bullet_lines(cons or "")
    new_pros_lines = consolidate_bullet_points_with_ai(pros_lines, "pros")
    new_cons_lines = consolidate_bullet_points_with_ai(cons_lines, "cons")
    new_pros = "\n".join(new_pros_lines).strip() if new_pros_lines else (pros or "").strip()
    new_cons = "\n".join(new_cons_lines).strip() if new_cons_lines else (cons or "").strip()
    return new_pros, new_cons
