"""The LLM verifier — the judgment tier of the gate.

It only sees drafts that already survived the deterministic checks, and it only
judges the rules that need reading rather than counting: R4 (concrete next
step) and R7 (every claim grounded in the brief).

Two deliberate design choices, both from
https://github.com/ChecksumStudio/agent-verification-rails:

1. The verdict vocabulary is HELD / FAILED — never "approved". HELD means
   "I could not break this draft with the checks I ran", and the verdict names
   what it did NOT examine. A pass that stays silent about its scope gets
   carried into domains it never checked.
2. Fail closed. If the verifier's output cannot be parsed as the required
   JSON, the draft is FAILED. An unreadable verdict is not a soft yes.

The verifier should be a different (and cheaper) model than the worker: a
model re-reading its own output brings the same blind spots to the audit.
"""

import json
import re

VERIFIER_PROMPT = """You are a verification gate for outreach emails. You do not rewrite,
improve, or praise drafts. You check them against rules and report violations.

THE BRIEF (ground truth — the only facts the draft may assert):
{brief}

THE RULES you are judging (others were already machine-checked; do not re-judge them):
- R4 — Concrete next step: the email ends with exactly one specific, low-effort ask
  (a question, or a proposed action with a timeframe). "Let me know your thoughts"
  or multiple asks = violation.
- R7 — One claim, one basis: every factual claim about the recipient or their company
  must appear in the brief. Any invented fact (funding, launches, metrics, names) = violation.

THE DRAFT:
---
{draft}
---

Respond with ONLY a JSON object, no other text:
{{
  "verdict": "HELD" or "FAILED",
  "violations": [{{"rule": "R4" or "R7", "evidence": "quote or describe the exact problem"}}],
  "not_checked": ["list what you did not examine, e.g. deliverability, tone toward this specific recipient, whether the brief itself is accurate"]
}}

"HELD" means: I could not find an R4 or R7 violation in this draft. It does not mean
the email is good, persuasive, or safe to send unread. When in doubt, FAIL."""


def verify(provider, model: str, brief: str, draft: str) -> dict:
    raw = provider.complete(
        VERIFIER_PROMPT.format(brief=brief, draft=draft), model=model)
    # Models sometimes wrap JSON in fences despite instructions; strip them,
    # but anything beyond that fails closed.
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    try:
        result = json.loads(cleaned)
        verdict = result.get("verdict")
        if verdict not in ("HELD", "FAILED"):
            raise ValueError(f"invalid verdict: {verdict!r}")
        result.setdefault("violations", [])
        result.setdefault("not_checked", [])
        result["raw"] = raw
        return result
    except (json.JSONDecodeError, ValueError, AttributeError) as exc:
        return {
            "verdict": "FAILED",
            "violations": [{
                "rule": "GATE",
                "evidence": f"verifier output unparseable ({exc}); failing closed"}],
            "not_checked": ["everything — the verdict itself was malformed"],
            "raw": raw,
        }
