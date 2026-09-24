"""Hand-check a stratified sample so the report can say how far to trust the labels.

Half the sample comes from messages the model called corrections, half from
the rest. Your answers never leave your machine.
"""

from __future__ import annotations

import json
import os
import random

PROMPT = "Is this a correction of the agent? [y]es / [n]o / [s]kip / [q]uit: "


def load_audit(path: str) -> dict[str, dict]:
    audit: dict[str, dict] = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    d = json.loads(line)
                    audit[d["id"]] = d
    return audit


def sample(messages: dict[str, dict], labels: dict[str, dict], done: set[str], n: int, seed: int) -> list[tuple[str, str]]:
    rng = random.Random(seed)
    pos = sorted(i for i, d in labels.items() if d["correction"] and i not in done and i in messages)
    neg = sorted(i for i, d in labels.items() if not d["correction"] and i not in done and i in messages)
    rng.shuffle(pos)
    rng.shuffle(neg)
    half = n // 2
    picked = [(i, "flagged") for i in pos[:half]] + [(i, "unflagged") for i in neg[: n - half]]
    rng.shuffle(picked)  # don't let the order hint at the model's answer
    return picked


def run(messages, labels, audit_path, n=40, seed=0, ask=input, show=print) -> int:
    done = load_audit(audit_path)
    todo = sample(messages, labels, set(done), n, seed)
    if not todo:
        show("nothing left to audit")
        return 0
    answered = 0
    with open(audit_path, "a", encoding="utf-8") as out:
        for k, (i, stratum) in enumerate(todo, 1):
            m = messages[i]
            show(f"\n--- {k}/{len(todo)} ---")
            show(f"AGENT: ...{m['prev_assistant'][-300:]}")
            show(f"YOU:   {m['user']}")
            while True:
                a = ask(PROMPT).strip().lower()[:1]
                if a in ("y", "n", "s", "q"):
                    break
            if a == "q":
                break
            if a == "s":
                continue
            out.write(json.dumps({"id": i, "stratum": stratum, "human": a == "y"}) + "\n")
            out.flush()
            answered += 1
    return answered
