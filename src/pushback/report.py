"""Turn labels (and an optional audit) into the correction-rate table. Counts only, never message text."""

from __future__ import annotations

from collections import Counter, defaultdict

from .prompt import TASKS
from .stats import corrected_count, wilson


def build(labels: dict[int, dict], audit: dict[int, dict] | None = None, silent: dict | None = None) -> dict:
    total = Counter(d["task"] for d in labels.values())
    corr = Counter(d["task"] for d in labels.values() if d["correction"])
    ctypes = defaultdict(Counter)
    for d in labels.values():
        if d["correction"]:
            ctypes[d["task"]][d["ctype"]] += 1

    rows = []
    for task in TASKS:
        n, k = total[task], corr[task]
        if not n:
            continue
        lo, hi = wilson(k, n)
        rows.append({"task": task, "messages": n, "corrections": k, "rate": k / n, "low": lo, "high": hi,
                     "top": ctypes[task].most_common(3)})
    rows.sort(key=lambda r: r["rate"], reverse=True)

    flagged = sum(corr.values())
    out = {"messages": len(labels), "flagged": flagged, "rows": rows, "audit": None,
           "silent": silent or {}}

    if audit:
        pos = [a for a in audit.values() if a["stratum"] == "flagged"]
        neg = [a for a in audit.values() if a["stratum"] == "unflagged"]
        out["audit"] = {
            "n": len(audit),
            **corrected_count(
                flagged, len(labels) - flagged,
                sum(a["human"] for a in pos), len(pos),
                sum(a["human"] for a in neg), len(neg),
            ),
        }
    return out


def render(r: dict) -> str:
    lines = []
    n, f = r["messages"], r["flagged"]
    lines.append(f"{n} messages labelled, {f} flagged as corrections ({f / n:.1%})." if n else "no labels yet")
    lines.append("")
    lines.append("| task | messages | corrections | rate | 95% CI | most common |")
    lines.append("|---|---:|---:|---:|---|---|")
    for row in r["rows"]:
        top = ", ".join(f"{c} {k}" for c, k in row["top"])
        lines.append(f"| {row['task']} | {row['messages']} | {row['corrections']} | {row['rate']:.1%} "
                     f"| {row['low']:.1%}-{row['high']:.1%} | {top} |")

    a = r["audit"]
    lines.append("")
    if not a:
        lines.append("No audit yet: these are raw model labels. Run `pushback audit` before quoting any number.")
    elif a["estimate"] is None:
        lines.append(f"Audit has {a['n']} answers but needs both flagged and unflagged samples.")
    else:
        lines.append(f"Audit ({a['n']} hand checks): precision {a['precision']:.0%}, "
                     f"miss rate {a['miss_rate']:.1%} on unflagged messages.")
        lines.append(f"Estimated true corrections: {a['estimate']:.0f} "
                     f"(range {a['low']:.0f}-{a['high']:.0f}) = {a['estimate'] / n:.1%} of messages.")
        if a["n"] < 40:
            lines.append("Fewer than 40 hand checks: the range is wide. Audit more before posting.")

    s = r["silent"]
    if s and (s.get("rejections") or s.get("interrupts")):
        rej, intr = s.get("rejections", {}), s.get("interrupts", {})
        lines.append("")
        lines.append(f"Silent corrections (not in the table): {sum(rej.values())} rejected tool calls, "
                     f"{sum(intr.values())} interrupts.")
        both = Counter(rej) + Counter(intr)
        lines.append("By action: " + ", ".join(f"{k} {v}" for k, v in both.most_common()))
    return "\n".join(lines)
