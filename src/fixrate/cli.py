"""fixrate: how often do you correct your coding agent, and at what kind of work?"""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import audit as audit_mod
from . import extract as extract_mod
from . import label as label_mod
from . import report as report_mod

DATA = "fixrate-data"


def _paths(data_dir: str) -> dict[str, str]:
    return {k: os.path.join(data_dir, f) for k, f in {
        "messages": "messages.jsonl", "labels": "labels.jsonl",
        "audit": "audit.jsonl", "silent": "silent.json", "report": "report.md",
    }.items()}


def _load_messages(path: str) -> dict[str, dict]:
    if not os.path.exists(path):
        sys.exit(f"{path} not found. Run `fixrate extract` first.")
    with open(path, encoding="utf-8") as fh:
        return {m["id"]: m for m in map(json.loads, fh) if m}


def cmd_extract(a):
    p = _paths(a.data)
    os.makedirs(a.data, exist_ok=True)
    ex = extract_mod.extract(a.root, tuple(a.exclude or ()))
    with open(p["messages"], "w", encoding="utf-8") as fh:
        for m in ex.messages:
            fh.write(json.dumps(m, ensure_ascii=False) + "\n")
    with open(p["silent"], "w", encoding="utf-8") as fh:
        json.dump({"rejections": ex.rejections, "interrupts": ex.interrupts}, fh)
    print(f"{ex.sessions} sessions -> {len(ex.messages)} messages, "
          f"{sum(ex.rejections.values())} rejected tool calls, {sum(ex.interrupts.values())} interrupts")
    print(f"written to {a.data}/ (this folder holds your raw messages; keep it out of git)")


def cmd_label(a):
    p = _paths(a.data)
    messages = list(_load_messages(p["messages"]).values())
    base = os.environ.get("ANTHROPIC_BASE_URL")
    print(f"Sending {len(messages)} messages to {base or 'the Anthropic API'} with model {a.model}.")
    print("Your messages leave this machine for that provider. Check its data policy before using client logs.")
    if not a.yes and input("Continue? [y/N] ").strip().lower() != "y":
        sys.exit("aborted")
    written, failed = label_mod.run(messages, p["labels"], a.model, a.batch_size, a.workers, a.effort)
    print(f"done: {written} new labels, {failed} failed batches" + (" (re-run to retry them)" if failed else ""))


def cmd_audit(a):
    p = _paths(a.data)
    messages = _load_messages(p["messages"])
    labels = label_mod.load_labels(p["labels"])
    if not labels:
        sys.exit("no labels yet. Run `fixrate label` first.")
    n = audit_mod.run(messages, labels, p["audit"], a.n, a.seed)
    print(f"\nsaved {n} answers to {p['audit']}")


def cmd_report(a):
    p = _paths(a.data)
    labels = label_mod.load_labels(p["labels"])
    if not labels:
        sys.exit("no labels yet. Run `fixrate label` first.")
    silent = json.load(open(p["silent"], encoding="utf-8")) if os.path.exists(p["silent"]) else None
    text = report_mod.render(report_mod.build(labels, audit_mod.load_audit(p["audit"]), silent))
    print(text)
    if a.markdown:
        with open(p["report"], "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print(f"\nwritten to {p['report']} (counts only, safe to share)")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="fixrate", description=__doc__)
    ap.add_argument("--data", default=DATA, help=f"working folder (default: ./{DATA})")
    sub = ap.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("extract", help="pull your messages out of Claude Code transcripts")
    e.add_argument("--root", default=extract_mod.DEFAULT_ROOT, help="transcripts folder")
    e.add_argument("--exclude", nargs="*", help="session id prefixes to skip")
    e.set_defaults(func=cmd_extract)

    lb = sub.add_parser("label", help="label each message with Claude (resumable)")
    lb.add_argument("--model", default=label_mod.DEFAULT_MODEL)
    lb.add_argument("--effort", default="low", choices=["low", "medium", "high"])
    lb.add_argument("--batch-size", type=int, default=40)
    lb.add_argument("--workers", type=int, default=4)
    lb.add_argument("-y", "--yes", action="store_true", help="skip the data-leaves-your-machine prompt")
    lb.set_defaults(func=cmd_label)

    au = sub.add_parser("audit", help="hand-check a sample so the report can bound the error")
    au.add_argument("-n", type=int, default=40)
    au.add_argument("--seed", type=int, default=0)
    au.set_defaults(func=cmd_audit)

    rp = sub.add_parser("report", help="print the correction-rate table")
    rp.add_argument("--markdown", action="store_true", help="also write report.md")
    rp.set_defaults(func=cmd_report)

    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
