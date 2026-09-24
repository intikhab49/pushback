"""Turn labels (and an optional audit) into the correction-rate table. Counts only, never message text."""

from __future__ import annotations

from collections import Counter, defaultdict

from .prompt import TASKS
from .stats import corrected_count, wilson


def _next_id(message_id: str) -> str:
    session, _, n = message_id.rpartition(":")
    return f"{session}:{int(n) + 1}"


def build(labels: dict[str, dict], audit: dict[str, dict] | None = None, silent: dict | None = None,
          top_topics: int = 10, min_topic_messages: int = 5) -> dict:
    total = Counter(d["task"] for d in labels.values())
    corr = Counter(d["task"] for d in labels.values() if d["correction"])
    ctypes = defaultdict(Counter)
    # Corrected again: your very next message corrected the agent's fix too.
    # Only corrections followed by a labelled message count, so a session that ends on a correction isn't a success.
    again, again_base = Counter(), Counter()
    topic_n, topic_k, topic_again, topic_base = Counter(), Counter(), Counter(), Counter()
    for d in labels.values():
        if d.get("topic"):
            topic_n[(d["task"], d["topic"])] += 1
    for mid, d in labels.items():
        if not d["correction"]:
            continue
        key = (d["task"], d.get("topic"))
        topic_k[key] += 1
        ctypes[d["task"]][d["ctype"]] += 1
        nxt = labels.get(_next_id(mid))
        if nxt is not None:
            again_base[d["task"]] += 1
            again[d["task"]] += bool(nxt["correction"])
            topic_base[key] += 1
            topic_again[key] += bool(nxt["correction"])

    rows = []
    for task in TASKS:
        n, k = total[task], corr[task]
        if not n:
            continue
        lo, hi = wilson(k, n)
        rows.append({"task": task, "messages": n, "share": n / len(labels), "corrections": k, "rate": k / n,
                     "low": lo, "high": hi, "again": again[task], "again_base": again_base[task],
                     "top": ctypes[task].most_common(3)})
    rows.sort(key=lambda r: r["messages"], reverse=True)  # what you use the agent for most comes first

    flagged = sum(corr.values())
    topics = [{"task": t, "topic": tp, "messages": n, "corrections": topic_k[(t, tp)], "rate": topic_k[(t, tp)] / n,
               "again": topic_again[(t, tp)], "again_base": topic_base[(t, tp)]}
              for (t, tp), n in topic_n.items() if topic_k[(t, tp)] and n >= min_topic_messages]
    topics.sort(key=lambda x: (x["corrections"], x["rate"]), reverse=True)

    out = {"messages": len(labels), "flagged": flagged, "rows": rows, "topics": topics[:top_topics], "audit": None,
           "again": sum(again.values()), "again_base": sum(again_base.values()), "silent": silent or {}}

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
    lines.append("| task | messages | share of use | corrections | rate | 95% CI | corrected again | most common |")
    lines.append("|---|---:|---:|---:|---:|---|---:|---|")
    for row in r["rows"]:
        top = ", ".join(f"{c} {k}" for c, k in row["top"])
        again = f"{row['again'] / row['again_base']:.0%} ({row['again']}/{row['again_base']})" if row["again_base"] else "-"
        lines.append(f"| {row['task']} | {row['messages']} | {row['share']:.0%} | {row['corrections']} | {row['rate']:.1%} "
                     f"| {row['low']:.1%}-{row['high']:.1%} | {again} | {top} |")
    if r["again_base"]:
        lines.append("")
        lines.append(f"Corrected again: {r['again']} of {r['again_base']} corrections "
                     f"({r['again'] / r['again_base']:.0%}) were followed by another correction of the fix.")

    if r.get("topics"):
        lines.append("")
        lines.append("Most corrected topics (at least 5 messages each):")
        lines.append("")
        lines.append("| topic | messages | corrections | rate | corrected again |")
        lines.append("|---|---:|---:|---:|---:|")
        for t in r["topics"]:
            again = f"{t['again']}/{t['again_base']}" if t["again_base"] else "-"
            lines.append(f"| {t['task']} / {t['topic']} | {t['messages']} | {t['corrections']} | {t['rate']:.0%} | {again} |")

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
