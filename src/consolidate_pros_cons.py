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
