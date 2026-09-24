"""Turn labelled corrections into preference pairs (prompt / chosen / rejected).

For a correction C in a session ... P, [agent turn R], C, [agent turn A], N ...

    prompt   = P, the message the agent was answering
    rejected = R, the agent turn you corrected
    chosen   = A, the agent's reply to C, kept only if your next message N exists and is NOT a correction
    feedback = C, your correction itself

"You didn't correct it again" is weak evidence that A was good, and A was
written after seeing your feedback. Treat these pairs as a personal dataset
to inspect and filter, not as clean ground truth.

Only agent *text* is exported. Edits and commands the agent ran are tool
calls, so a code correction's pair may carry the explanation but not the
diff. The tool-call counts are kept so you can filter those out.
"""

from __future__ import annotations

import re
from collections import Counter

# Best-effort scrub of common credential shapes. It will miss things; read your export.
SECRET_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{30,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{20,}"),
    re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),  # JWT
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
]
# NAME_API_KEY=value / SECRET: value with a long value. The name is kept so the text still reads;
# placeholders like "your-key-here" are shorter than 24 characters and pass through.
ASSIGNMENT = re.compile(
    r"(?i)((?:api[_-]?key|secret|token|password|passwd)\w*\s*[:=]\s*['\"]?)[A-Za-z0-9_\-./+]{24,}")


def redact(text: str) -> tuple[str, int]:
    hits = 0
    for pat in SECRET_PATTERNS:
        text, n = pat.subn("[REDACTED]", text)
        hits += n
    text, n = ASSIGNMENT.subn(r"\1[REDACTED]", text)
    return text, hits + n


def _order_key(message_id: str) -> tuple[str, int]:
    session, _, n = message_id.rpartition(":")
    return session, int(n)


def build_pairs(
    messages: list[dict],
    labels: dict[str, dict],
    turns: dict[str, dict],
    tasks: set[str] | None = None,
    ctypes: set[str] | None = None,
    high_only: bool = False,
    max_tools: int | None = None,
) -> tuple[list[dict], Counter]:
    skipped: Counter = Counter()
    by_id = {m["id"]: m for m in messages}
    ids = sorted(by_id, key=_order_key)
    pos = {i: k for k, i in enumerate(ids)}
    pairs = []

    for mid in ids:
        lab = labels.get(mid)
        if not lab or not lab["correction"]:
            continue
        if tasks and lab["task"] not in tasks:
            skipped["task filtered"] += 1
            continue
        if ctypes and lab["ctype"] not in ctypes:
            skipped["correction type filtered"] += 1
            continue
        if high_only and lab.get("conf") != "high":
            skipped["low confidence"] += 1
            continue
        session, n = _order_key(mid)
        prev_id, next_id = f"{session}:{n - 1}", f"{session}:{n + 1}"
        if prev_id not in pos:
            skipped["no earlier message"] += 1
            continue
        # Your next message (n+1) is both what follows the agent's new reply and your verdict on it.
        if next_id not in pos:
            skipped["session ended after correction"] += 1
            continue
        verdict = labels.get(next_id)
        if verdict is None:
            skipped["reaction not labelled"] += 1
            continue
        if verdict["correction"]:
            skipped["new reply was corrected too"] += 1
            continue

        rejected = turns.get(mid, {}).get("prev_turn", "")
        chosen = turns.get(next_id, {}).get("prev_turn", "")
        if not rejected.strip() or not chosen.strip():
            skipped["agent turn had no text"] += 1
            continue
        r_tools = turns[mid].get("prev_turn_tools", 0)
        c_tools = turns[next_id].get("prev_turn_tools", 0)
        if max_tools is not None and max(r_tools, c_tools) > max_tools:
            skipped["too many tool calls"] += 1
            continue

        pairs.append({
            "prompt": turns.get(prev_id, {}).get("prompt", ""),
            "rejected": rejected,
            "chosen": chosen,
            "feedback": turns[mid].get("prompt", ""),
            "id": mid,
            "task": lab["task"],
            "ctype": lab["ctype"],
            "rejected_tool_calls": r_tools,
            "chosen_tool_calls": c_tools,
        })
    return pairs, skipped


def scrub(pairs: list[dict]) -> int:
    total = 0
    for p in pairs:
        for k in ("prompt", "rejected", "chosen", "feedback"):
            p[k], n = redact(p[k])
            total += n
    return total
