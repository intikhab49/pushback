"""Send batches of messages to Claude and store one label per message.

Resumable: labels are appended to labels.jsonl batch by batch, and a re-run
skips every id already present. A batch that fails is logged and left
unlabelled, so a network blip never becomes a silent "not a correction".
"""

from __future__ import annotations

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import anthropic

from .prompt import CTYPES, SCHEMA, SYSTEM, TASKS

DEFAULT_MODEL = "claude-opus-5"


def load_labels(path: str) -> dict[str, dict]:
    labels: dict[str, dict] = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    d = json.loads(line)
                    labels[d["id"]] = d
    return labels


def validate(raw: list[dict], keys: list[str]) -> list[dict]:
    """Map the model's per-batch numbers back to message ids, keeping only well-formed labels.

    Anything missing or malformed stays unlabelled and is retried on the next run.
    """
    good = []
    seen = set()
    for d in raw:
        try:
            i = int(d["id"])
        except (KeyError, TypeError, ValueError):
            continue
        if not 0 <= i < len(keys) or i in seen:
            continue
        if d.get("task") not in TASKS or d.get("ctype") not in CTYPES or not isinstance(d.get("correction"), bool):
            continue
        if not d["correction"]:
            d["ctype"] = "none"
        seen.add(i)
        good.append({"id": keys[i], **{k: d[k] for k in ("task", "correction", "ctype", "conf") if k in d}})
    return good


def _request_kwargs(model: str, batch: list[dict], effort: str) -> dict:
    items = [{"id": n, "prev_assistant": m["prev_assistant"], "user": m["user"]} for n, m in enumerate(batch)]
    return {
        "model": model,
        "max_tokens": 16000,
        "system": SYSTEM,
        "messages": [{"role": "user", "content": json.dumps(items, ensure_ascii=False)}],
        "output_config": {"effort": effort, "format": {"type": "json_schema", "schema": SCHEMA}},
    }


def label_batch(client, model: str, batch: list[dict], effort: str = "low") -> list[dict]:
    response = client.messages.create(**_request_kwargs(model, batch, effort))
    if response.stop_reason == "refusal":
        raise RuntimeError("model declined this batch (stop_reason=refusal)")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("output hit max_tokens; use a smaller --batch-size")
    text = next((b.text for b in response.content if b.type == "text"), "")
    return validate(json.loads(text).get("labels", []), [m["id"] for m in batch])


def run(
    messages: list[dict],
    labels_path: str,
    model: str = DEFAULT_MODEL,
    batch_size: int = 40,
    workers: int = 4,
    effort: str = "low",
    client=None,
    log=print,
) -> tuple[int, int]:
    done = load_labels(labels_path)
    todo = [m for m in messages if m["id"] not in done]
    batches = [todo[i:i + batch_size] for i in range(0, len(todo), batch_size)]
    if not batches:
        log(f"all {len(messages)} messages already labelled")
        return 0, 0

    client = client or anthropic.Anthropic()
    lock = threading.Lock()
    written = failed = 0

    def work(batch):
        return batch, label_batch(client, model, batch, effort)

    with ThreadPoolExecutor(max_workers=workers) as pool, open(labels_path, "a", encoding="utf-8") as out:
        futures = [pool.submit(work, b) for b in batches]
        for n, fut in enumerate(as_completed(futures), 1):
            try:
                batch, labels = fut.result()
            except anthropic.AuthenticationError:
                raise
            except (anthropic.APIError, RuntimeError, json.JSONDecodeError) as e:
                # APIError covers status errors AND connection errors; both leave the batch for a re-run.
                failed += 1
                log(f"[{n}/{len(batches)}] batch failed, will retry on next run: {type(e).__name__}: {e}")
                continue
            with lock:
                for d in labels:
                    out.write(json.dumps(d) + "\n")
                out.flush()
                written += len(labels)
            missing = len(batch) - len(labels)
            log(f"[{n}/{len(batches)}] labelled {len(labels)}" + (f", {missing} left for re-run" if missing else ""))
    return written, failed
