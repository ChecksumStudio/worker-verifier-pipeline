#!/usr/bin/env python3
"""Gated outreach pipeline: worker drafts, verifier gates, only passing output ships.

Usage:
    python3 run_pipeline.py briefs/acme_intro.md
    python3 run_pipeline.py briefs/acme_intro.md --verify-only fixtures/bad_draft.md

Flow per attempt (max 3):
    worker draft -> deterministic checks (free) -> LLM verifier (cheap model)
Any violation at any tier: the draft is rejected, the violations go back to the
worker verbatim, and the next attempt must clear the same gate. Three failed
attempts means NOTHING ships — an empty outbox is a result, not an error.

Every step is logged to receipts/<run_id>.jsonl with the draft's sha256.
The receipt is the product as much as the email is.
"""

import argparse
import datetime
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from pipeline import checks, verifier, worker
from pipeline.providers import get_provider

ROOT = Path(__file__).parent
RULES = (ROOT / "rules" / "outreach_style.md").read_text()

WORKER_MODEL = "sonnet"
VERIFIER_MODEL = "haiku"   # different + cheaper than the worker, deliberately
MAX_ATTEMPTS = 3


def sender_from_brief(brief: str) -> str:
    match = re.search(r"^Sender:\s*(.+)$", brief, re.M)
    if not match:
        sys.exit("brief must contain a `Sender: <name>` line (needed for check R8)")
    return match.group(1).strip()


class Receipts:
    def __init__(self, run_id: str):
        self.path = ROOT / "receipts" / f"{run_id}.jsonl"
        self.run_id = run_id

    def log(self, stage: str, **fields):
        entry = {
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "run_id": self.run_id,
            "stage": stage,
            **fields,
        }
        with self.path.open("a") as f:
            f.write(json.dumps(entry) + "\n")
        # Terse mirror to the terminal so a watcher can follow the run.
        summary = {k: v for k, v in fields.items()
                   if k in ("attempt", "verdict", "violations", "sha256", "model")}
        print(f"  [{stage}] {json.dumps(summary, default=str)}")


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def gate(draft_text: str, brief: str, sender: str, provider, receipts, attempt: int):
    """Run the full gate on one draft. Returns (verdict, violations)."""
    digest = sha(draft_text)

    det = checks.run_checks(draft_text, sender_name=sender)
    receipts.log("deterministic-checks", attempt=attempt, sha256=digest,
                 verdict="FAILED" if det else "HELD", violations=det, cost="none")
    if det:
        return "FAILED", det

    llm = verifier.verify(provider, VERIFIER_MODEL, brief, draft_text)
    receipts.log("llm-verifier", attempt=attempt, sha256=digest,
                 model=VERIFIER_MODEL, verdict=llm["verdict"],
                 violations=llm["violations"], not_checked=llm["not_checked"])
    return llm["verdict"], llm["violations"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("brief", help="path to the brief file")
    parser.add_argument("--verify-only", metavar="DRAFT",
                        help="skip the worker; run the gate on an existing draft file")
    args = parser.parse_args()

    brief = Path(args.brief).read_text()
    sender = sender_from_brief(brief)
    run_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    receipts = Receipts(run_id)
    provider = get_provider()
    receipts.log("start", provider=provider.name, brief=args.brief,
                 mode="verify-only" if args.verify_only else "full")
    print(f"run {run_id} — receipts/{run_id}.jsonl")

    if args.verify_only:
        draft_text = Path(args.verify_only).read_text()
        verdict, violations = gate(draft_text, brief, sender, provider,
                                   receipts, attempt=0)
        print(f"\nverdict: {verdict}"
              + (f" — {len(violations)} violation(s)" if violations else ""))
        sys.exit(0 if verdict == "HELD" else 1)

    violations = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        draft_text = worker.draft(provider, WORKER_MODEL, brief, RULES,
                                  violations=violations)
        receipts.log("worker-draft", attempt=attempt, model=WORKER_MODEL,
                     sha256=sha(draft_text), words=len(draft_text.split()))
        verdict, violations = gate(draft_text, brief, sender, provider,
                                   receipts, attempt=attempt)
        if verdict == "HELD":
            out = ROOT / "outbox" / f"{run_id}_attempt{attempt}.md"
            out.write_text(draft_text + "\n")
            receipts.log("shipped", attempt=attempt, sha256=sha(draft_text),
                         outbox=str(out.relative_to(ROOT)))
            print(f"\nHELD on attempt {attempt} — shipped to {out.relative_to(ROOT)}")
            print("(HELD means the gate could not break it — not that it is good. Read it.)")
            return

    receipts.log("abstained", attempts=MAX_ATTEMPTS)
    print(f"\nFAILED {MAX_ATTEMPTS} attempts — nothing shipped. "
          "The empty outbox is the honest result.")
    sys.exit(1)


if __name__ == "__main__":
    main()
