"""Pull human messages (with the assistant turn they respond to) out of Claude Code transcripts.

Claude Code writes one JSONL file per session under ~/.claude/projects/<project>/.
We keep only what a person typed: tool results, system reminders, slash-command
output and subagent (sidechain) traffic are dropped. Silent corrections -- a
rejected tool call or an interrupt -- carry no text, so they are counted
separately and attributed to the kind of action that was cut off.
"""

from __future__ import annotations

import glob
import json
import os
from collections import Counter
from dataclasses import dataclass, field

DEFAULT_ROOT = os.path.join(os.path.expanduser("~"), ".claude", "projects")

REJECTED = "doesn't want to proceed"
INTERRUPTED = "[Request interrupted by user"

CODE_EXT = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".sql", ".prisma", ".json", ".yml", ".yaml",
    ".sh", ".css", ".html", ".go", ".rs", ".toml", ".java", ".kt", ".rb", ".php", ".cs",
}


@dataclass
class Extracted:
    messages: list[dict] = field(default_factory=list)
    rejections: Counter = field(default_factory=Counter)
    interrupts: Counter = field(default_factory=Counter)
    sessions: int = 0


def action_kind(name: str, inp: dict | None) -> str:
    """Bucket a tool call so silent corrections can be attributed without storing its content."""
    inp = inp or {}
    if name in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        ext = os.path.splitext(inp.get("file_path") or "")[1].lower()
        return "edit-code" if ext in CODE_EXT else "edit-other"
    if name in ("Bash", "PowerShell"):
        cmd = inp.get("command") or ""
        if "git " in cmd or "gh " in cmd:
            return "shell-git"
        if any(k in cmd for k in ("npm", "pnpm", "yarn", "pytest", "python", "node", "tsc", "npx", "cargo", "go ")):
            return "shell-build"
        return "shell-other"
    if name.startswith("mcp__"):
        return "mcp"
    return "other-tool"


def _is_human_text(text: str) -> bool:
    if not text:
        return False
    # Harness-injected blocks (<system-reminder>, <command-name>, ...) start with a tag.
    # Pasted content is still something the person chose to send.
    return not (text.startswith("<") and not text.startswith("<pasted"))


def extract(
    root: str = DEFAULT_ROOT,
    exclude_sessions: tuple[str, ...] = (),
    max_user_chars: int = 500,
    max_context_chars: int = 400,
) -> Extracted:
    out = Extracted()
    files = sorted(glob.glob(os.path.join(root, "*", "*.jsonl")))
    for path in files:
        session = os.path.splitext(os.path.basename(path))[0]
        if any(session.startswith(x) for x in exclude_sessions):
            continue
        out.sessions += 1
        _extract_file(path, session, out, max_user_chars, max_context_chars)
    return out


def _extract_file(path, session, out, max_user_chars, max_context_chars):
    last_text = ""
    n = 0
    tools: dict[str, tuple[str, dict]] = {}
    last_tool: tuple[str, dict] | None = None
    with open(path, encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("isSidechain"):
                continue
            message = entry.get("message")
            content = message.get("content") if isinstance(message, dict) else None

            if entry.get("type") == "assistant" and isinstance(content, list):
                text = " ".join(b.get("text", "") for b in content if b.get("type") == "text").strip()
                if text:
                    last_text = text
                for b in content:
                    if b.get("type") == "tool_use":
                        tools[b.get("id")] = (b.get("name", ""), b.get("input"))
                        last_tool = tools[b.get("id")]
                continue

            if entry.get("type") != "user" or entry.get("isMeta"):
                continue

            if isinstance(content, list):
                texts = []
                for b in content:
                    if b.get("type") == "tool_result" and REJECTED in json.dumps(b.get("content")):
                        name, inp = tools.get(b.get("tool_use_id"), ("", None))
                        out.rejections[action_kind(name, inp)] += 1
                    elif b.get("type") == "text":
                        texts.append(b.get("text", ""))
            else:
                texts = [content or ""]

            for text in texts:
                text = text.strip()
                if INTERRUPTED in text:
                    out.interrupts[action_kind(*last_tool) if last_tool else "none"] += 1
                    continue
                if not _is_human_text(text):
                    continue
                out.messages.append({
                    # Stable across re-extracts: sessions only ever append, so session:index never shifts.
                    "id": f"{session}:{n}",
                    "session": session[:8],
                    "prev_assistant": last_text[-max_context_chars:].replace("\n", " "),
                    "user": text[:max_user_chars].replace("\n", " "),
                })
                n += 1
