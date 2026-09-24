"""Turn recurring corrections into rules you can paste into CLAUDE.md.

The model groups corrections that share a cause and drafts one instruction per
group. Two checks keep that honest:

- Support is counted here from the correction ids the model cites, never taken
  from the model's own numbers, and a rule needs `min_support` real corrections.
- Given your existing rule files, the model marks rules you already have. Those
  are the interesting ones: a rule that exists and still gets broken isn't working.
"""

from __future__ import annotations

import json

from .prompt import TASKS

AGENT_CHARS = 500
CORRECTION_CHARS = 400

SYSTEM = """You are given corrections a user made to their AI agent. Each item has an id, the task type, the end of the agent's turn that was corrected, and the user's correction.

Find recurring patterns: the same kind of mistake corrected at least 3 times. For each pattern, write one rule the agent can follow to avoid it.

Rules:
- Write each rule as an instruction for a CLAUDE.md file, in plain words. Make it specific and checkable. "Be careful" or "write better" is not a rule.
- Generalise. Never include client names, company names, people's names, credentials or quoted message text in a rule.
- "why" is one sentence on what kept going wrong.
- "ids" lists every correction that supports the pattern. Only cite ids that really show the same mistake.
- If existing rules are provided and one of them already asks for this, put a short quote of it (15 words max) in "covered_by". Otherwise leave "covered_by" as an empty string.
- Prefer fewer, sharper rules. Skip one-off corrections."""

SCHEMA = {
    "type": "object",
    "properties": {
        "rules": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "rule": {"type": "string"},
                    "why": {"type": "string"},
                    "task": {"type": "string", "enum": TASKS},
                    "ids": {"type": "array", "items": {"type": "integer"}},
                    "covered_by": {"type": "string"},
                },
                "required": ["rule", "why", "task", "ids", "covered_by"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["rules"],
    "additionalProperties": False,
}


def collect(labels: dict[str, dict], turns: dict[str, dict], tasks=None, ctypes=None, limit=400) -> list[dict]:
    """Every labelled correction with the context the model needs. Newest last, capped at `limit`."""
    items = []
    for mid, lab in labels.items():
        if not lab["correction"] or (tasks and lab["task"] not in tasks) or (ctypes and lab["ctype"] not in ctypes):
            continue
        turn = turns.get(mid, {})
        items.append({
            "id": mid,
            "task": lab["task"],
            "agent": turn.get("prev_turn", "")[-AGENT_CHARS:],
            "correction": turn.get("prompt", "")[:CORRECTION_CHARS],
        })
    items.sort(key=lambda x: (x["id"].rpartition(":")[0], int(x["id"].rpartition(":")[2])))
    return items[-limit:]


def build_request(items: list[dict], existing: str, model: str, effort: str = "high") -> dict:
    payload = [{"n": n, "task": x["task"], "agent": x["agent"], "correction": x["correction"]}
               for n, x in enumerate(items)]
    content = "CORRECTIONS (the \"n\" field is the id to cite):\n" + json.dumps(payload, ensure_ascii=False)
    if existing.strip():
        content = "EXISTING RULES:\n" + existing.strip() + "\n\n" + content
    return {
        "model": model,
        "max_tokens": 16000,
        "system": SYSTEM,
        "messages": [{"role": "user", "content": content}],
        "output_config": {"effort": effort, "format": {"type": "json_schema", "schema": SCHEMA}},
    }


def parse(raw: dict, items: list[dict], min_support: int = 3) -> list[dict]:
    """Map cited numbers back to correction ids, recount support, drop weak or malformed rules."""
    rules = []
    for r in raw.get("rules", []):
        if not isinstance(r, dict) or not str(r.get("rule", "")).strip():
            continue
        ids = []
        for i in r.get("ids", []):
            if isinstance(i, int) and 0 <= i < len(items) and items[i]["id"] not in ids:
                ids.append(items[i]["id"])
        if len(ids) < min_support:
            continue
        rules.append({
            "rule": r["rule"].strip(),
            "why": str(r.get("why", "")).strip(),
            "task": r.get("task") if r.get("task") in TASKS else "meta",
            "support": len(ids),
            "ids": ids,
            "covered_by": str(r.get("covered_by", "")).strip(),
        })
    rules.sort(key=lambda r: r["support"], reverse=True)
    return rules


def ask(client, request: dict) -> dict:
    response = client.messages.create(**request)
    if response.stop_reason == "refusal":
        raise RuntimeError("model declined (stop_reason=refusal)")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("output hit max_tokens; narrow the input with --task or --limit")
    text = next((b.text for b in response.content if b.type == "text"), "")
    return json.loads(text)


def _short(message_id: str) -> str:
    """session-uuid:12 -> first 8 chars of the session, which is enough to find it."""
    session, _, n = message_id.rpartition(":")
    return f"{session[:8]}:{n}"


def render(rules: list[dict], n_corrections: int) -> str:
    broken = [r for r in rules if r["covered_by"]]
    new = [r for r in rules if not r["covered_by"]]
    out = [f"# Rules from {n_corrections} corrections", ""]
    out.append("Each rule is backed by at least the number of corrections shown. Read the evidence ids "
               "in your own data before adopting a rule; the model drafted these, you decide.")

    def block(title, note, group):
        if not group:
            return
        out.extend(["", f"## {title}", "", note, ""])
        for r in group:
            out.append(f"- **{r['rule']}**  ")
            out.append(f"  {r['why']} ({r['task']}, {r['support']} corrections)")
            if r["covered_by"]:
                out.append(f"  You already have: \"{r['covered_by']}\"")
            shown = [_short(i) for i in r["ids"][:8]]
            out.append(f"  Evidence: {', '.join(shown)}" + (" …" if len(r["ids"]) > 8 else ""))

    block("Rules you already have that keep getting broken",
          "A rule that exists and still gets corrected isn't working. Make it more specific, "
          "move it somewhere the agent reads at the right moment, or turn it into a check.", broken)
    block("New rules to consider", "Recurring corrections with no rule behind them yet.", new)
    if not rules:
        out.extend(["", "No pattern reached the minimum support. Try more data or a lower --min-support."])
    return "\n".join(out) + "\n"
