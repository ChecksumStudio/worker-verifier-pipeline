"""Deterministic checks — the cheap tier of the gate.

These run before any model sees the draft. No LLM call, no cost, no judgment:
each check maps to a rule ID in rules/outreach_style.md and either finds a
violation or doesn't. A draft that fails here never reaches the LLM verifier —
the cheapest check that can reject should be the one that rejects.

Covered here: R1 (length), R2 (hype words), R3 (exclamations),
R5 (subject line), R6 (placeholders), R8 (sign-off).
Left to the LLM verifier: R4 (concrete next step), R7 (claims grounded in
the brief) — those need reading, not counting.
"""

import re

BANNED_WORDS = [
    "revolutionize", "game-changing", "cutting-edge", "synergy",
    "unlock", "supercharge", "disrupt", "next-level", "world-class",
]

CLICKBAIT_SUBJECTS = ["quick question", "re:"]

PLACEHOLDER_RE = re.compile(r"\[[^\]]{1,40}\]|\{\{[^}]{1,40}\}\}|<insert[^>]{0,40}>", re.I)


def split_subject_body(draft: str):
    """First line must be the subject; the rest is the body."""
    lines = draft.strip().splitlines()
    if not lines:
        return None, ""
    first = lines[0].strip()
    if first.lower().startswith("subject:"):
        return first[len("subject:"):].strip(), "\n".join(lines[1:]).strip()
    return None, draft.strip()


def run_checks(draft: str, sender_name: str) -> list[dict]:
    """Return a list of violations: [{rule, evidence}, ...]. Empty = clean."""
    violations = []
    subject, body = split_subject_body(draft)

    # R5 — subject line
    if subject is None:
        violations.append({"rule": "R5", "evidence": "no `Subject: ` first line"})
    else:
        if len(subject) > 60:
            violations.append(
                {"rule": "R5", "evidence": f"subject is {len(subject)} chars (max 60)"})
        for bait in CLICKBAIT_SUBJECTS:
            if subject.lower().startswith(bait):
                violations.append(
                    {"rule": "R5", "evidence": f"clickbait subject opener: {bait!r}"})

    # R1 — body length
    word_count = len(body.split())
    if word_count > 130:
        violations.append(
            {"rule": "R1", "evidence": f"body is {word_count} words (max 130)"})

    # R2 — hype vocabulary
    lowered = draft.lower()
    for word in BANNED_WORDS:
        if word in lowered:
            violations.append({"rule": "R2", "evidence": f"banned word: {word!r}"})

    # R3 — exclamation marks
    bangs = draft.count("!")
    if bangs > 1:
        violations.append(
            {"rule": "R3", "evidence": f"{bangs} exclamation marks (max 1)"})

    # R6 — unresolved placeholders
    for match in PLACEHOLDER_RE.findall(draft):
        violations.append({"rule": "R6", "evidence": f"placeholder survived: {match!r}"})

    # R8 — sign-off with the sender's name
    tail = "\n".join(body.splitlines()[-3:]).lower()
    if sender_name.lower() not in tail:
        violations.append(
            {"rule": "R8",
             "evidence": f"sender name {sender_name!r} not in the closing lines"})

    return violations
