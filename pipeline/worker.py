"""The worker — drafts the email. It is expected to be fluent and expected to
be wrong sometimes. Nothing it produces ships on its own say-so; that is the
verifier's problem, which is the entire point of the pipeline."""

WORKER_PROMPT = """You are drafting a cold outreach email.

THE BRIEF (the only source of facts you may use):
{brief}

STYLE RULES (the draft must satisfy every one):
{rules}

{feedback_block}Write the email now. Output ONLY the email itself, starting with the
`Subject: ` line, then a blank line, then the body. No preamble, no commentary,
no markdown fences."""

FEEDBACK_TEMPLATE = """Your previous draft was REJECTED by the verification gate.
Violations found (rule ID — evidence):
{violations}

Fix every violation. Do not introduce new ones.

"""


def draft(provider, model: str, brief: str, rules: str,
          violations: list[dict] | None = None) -> str:
    feedback_block = ""
    if violations:
        lines = "\n".join(f"- {v['rule']} — {v['evidence']}" for v in violations)
        feedback_block = FEEDBACK_TEMPLATE.format(violations=lines)
    prompt = WORKER_PROMPT.format(
        brief=brief, rules=rules, feedback_block=feedback_block)
    return provider.complete(prompt, model=model)
