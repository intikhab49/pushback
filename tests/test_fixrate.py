import json
import types

import pytest

from fixrate import audit, extract, label, report, stats


def _write_session(tmp_path, name, entries):
    proj = tmp_path / "proj"
    proj.mkdir(exist_ok=True)
    with open(proj / f"{name}.jsonl", "w", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e) + "\n")


def _asst(text=None, tool=None):
    content = []
    if text:
        content.append({"type": "text", "text": text})
    if tool:
        content.append({"type": "tool_use", "id": tool[0], "name": tool[1], "input": tool[2]})
    return {"type": "assistant", "message": {"content": content}}


def _user(content, **kw):
    return {"type": "user", "message": {"content": content}, **kw}


SESSION = [
    _user("write me a post about the launch"),
    _asst("Here is the post: Big news today..."),
    _user("no, you didn't mention it's open source"),
    _user("<system-reminder>injected</system-reminder>"),
    _user("hidden meta", isMeta=True),
    {"type": "user", "isSidechain": True, "message": {"content": "subagent traffic"}},
    _asst("Editing the file.", tool=("t1", "Edit", {"file_path": "app.py"})),
    _user([{"type": "tool_result", "tool_use_id": "t1", "content": "The user doesn't want to proceed with this tool use."}]),
    _asst(tool=("t2", "Bash", {"command": "npm test"})),
    _user([{"type": "text", "text": "[Request interrupted by user]"}]),
    _user([{"type": "text", "text": "<pasted_content>log</pasted_content> what is this"}]),
]


def test_extract_keeps_only_human_text(tmp_path):
    _write_session(tmp_path, "abc123456789", SESSION)
    ex = extract.extract(str(tmp_path))
    users = [m["user"] for m in ex.messages]
    assert users == [
        "write me a post about the launch",
        "no, you didn't mention it's open source",
        "<pasted_content>log</pasted_content> what is this",
    ]
    assert ex.messages[1]["prev_assistant"] == "Here is the post: Big news today..."
    assert ex.rejections == {"edit-code": 1}
    assert ex.interrupts == {"shell-build": 1}


def test_extract_ids_are_stable_when_sessions_are_added(tmp_path):
    _write_session(tmp_path, "bbb", SESSION)
    before = {m["id"]: m["user"] for m in extract.extract(str(tmp_path)).messages}
    _write_session(tmp_path, "aaa", SESSION)  # sorts first, would shift positional ids
    after = {m["id"]: m["user"] for m in extract.extract(str(tmp_path)).messages}
    assert all(after[k] == v for k, v in before.items())


def test_extract_exclude(tmp_path):
    _write_session(tmp_path, "keep", SESSION)
    _write_session(tmp_path, "skipme", SESSION)
    ex = extract.extract(str(tmp_path), exclude_sessions=("skip",))
    assert ex.sessions == 1


def test_validate_maps_batch_numbers_and_drops_junk():
    keys = ["s:0", "s:1", "s:2"]
    raw = [
        {"id": 0, "task": "writing", "correction": True, "ctype": "tone_style", "conf": "high"},
        {"id": 0, "task": "code", "correction": False, "ctype": "none", "conf": "high"},  # duplicate
        {"id": 1, "task": "code", "correction": False, "ctype": "scope", "conf": "low"},  # ctype reset
        {"id": 7, "task": "code", "correction": False, "ctype": "none", "conf": "high"},  # out of range
        {"id": 2, "task": "cooking", "correction": False, "ctype": "none", "conf": "high"},  # bad task
    ]
    out = label.validate(raw, keys)
    assert [d["id"] for d in out] == ["s:0", "s:1"]
    assert out[1]["ctype"] == "none"


class FakeClient:
    """Stands in for anthropic.Anthropic: labels every item, fails the batch containing 'boom'."""

    def __init__(self):
        self.messages = self
        self.calls = 0

    def create(self, **kw):
        self.calls += 1
        items = json.loads(kw["messages"][0]["content"])
        assert kw["output_config"]["format"]["type"] == "json_schema"
        if any("boom" in i["user"] for i in items):
            raise RuntimeError("simulated failure")
        labels = [{"id": i["id"], "task": "writing", "correction": i["user"].startswith("no"),
                   "ctype": "tone_style" if i["user"].startswith("no") else "none", "conf": "high"} for i in items]
        block = types.SimpleNamespace(type="text", text=json.dumps({"labels": labels}))
        return types.SimpleNamespace(stop_reason="end_turn", content=[block])


def test_label_run_is_resumable_and_keeps_failed_batches_for_retry(tmp_path):
    msgs = [{"id": f"s:{n}", "prev_assistant": "", "user": u} for n, u in enumerate(["no bad", "ok", "boom", "fine"])]
    path = str(tmp_path / "labels.jsonl")
    fake = FakeClient()
    written, failed = label.run(msgs, path, batch_size=2, workers=1, client=fake, log=lambda *_: None)
    assert (written, failed) == (2, 1)
    labels = label.load_labels(path)
    assert labels["s:0"]["correction"] is True and "s:2" not in labels

    msgs[2]["user"] = "recovered"
    written, failed = label.run(msgs, path, batch_size=2, workers=1, client=fake, log=lambda *_: None)
    assert (written, failed) == (2, 0)
    assert set(label.load_labels(path)) == {"s:0", "s:1", "s:2", "s:3"}
    assert fake.calls == 3  # the already-labelled batch was not re-sent


def test_wilson_bounds():
    lo, hi = stats.wilson(21, 354)
    assert 0.03 < lo < 0.06 < hi < 0.10
    assert stats.wilson(0, 0) == (0.0, 0.0)


def test_corrected_count():
    r = stats.corrected_count(flagged=100, unflagged=900, audit_pos_yes=18, audit_pos_n=20,
                              audit_neg_yes=1, audit_neg_n=20)
    assert r["estimate"] == pytest.approx(100 * 0.9 + 900 * 0.05)
    assert r["low"] < r["estimate"] < r["high"]
    assert stats.corrected_count(10, 10, 0, 0, 0, 5)["estimate"] is None


def test_audit_sample_is_stratified_and_skips_done():
    labels = {f"s:{i}": {"correction": i < 10} for i in range(100)}
    messages = {k: {} for k in labels}
    picked = audit.sample(messages, labels, done={"s:0"}, n=10, seed=1)
    strata = [s for _, s in picked]
    assert strata.count("flagged") == 5 and strata.count("unflagged") == 5
    assert "s:0" not in [i for i, _ in picked]


def test_audit_run_records_answers(tmp_path):
    labels = {"a": {"correction": True}, "b": {"correction": False}}
    messages = {k: {"prev_assistant": "x", "user": "y"} for k in labels}
    answers = iter(["y", "n"])
    path = str(tmp_path / "audit.jsonl")
    n = audit.run(messages, labels, path, n=2, ask=lambda _: next(answers), show=lambda *_: None)
    assert n == 2 and len(audit.load_audit(path)) == 2


def test_report_never_contains_message_text():
    labels = {
        "s:0": {"task": "writing", "correction": True, "ctype": "tone_style"},
        "s:1": {"task": "code", "correction": False, "ctype": "none"},
    }
    aud = {"s:0": {"stratum": "flagged", "human": True}, "s:1": {"stratum": "unflagged", "human": False}}
    text = report.render(report.build(labels, aud, {"rejections": {"edit-code": 1}, "interrupts": {}}))
    assert "| writing | 1 | 1 | 100.0%" in text
    assert "Estimated true corrections: 1" in text
    assert "Fewer than 40 hand checks" in text
    assert "1 rejected tool calls" in text


def test_report_without_audit_warns():
    labels = {"s:0": {"task": "code", "correction": False, "ctype": "none"}}
    assert "No audit yet" in report.render(report.build(labels))


# --- turns + export -------------------------------------------------------

from fixrate import export


def test_extract_captures_full_multi_block_turns(tmp_path):
    long_reply = "x" * 900
    _write_session(tmp_path, "sess", [
        _user("draft the post"),
        _asst("First part."),
        _asst(long_reply, tool=("t9", "Write", {"file_path": "post.md"})),
        _user("no, too long"),
    ])
    ex = extract.extract(str(tmp_path))
    turn = ex.turns["sess:1"]
    assert turn["prompt"] == "no, too long"
    assert turn["prev_turn"] == "First part.\n\n" + long_reply  # nothing truncated
    assert turn["prev_turn_tools"] == 1
    assert ex.turns["sess:0"]["prev_turn"] == ""


def _pair_fixture(verdicts):
    """Session s: 0 ask, 1 correction, 2 reaction to the new reply (+ more)."""
    msgs = [{"id": f"s:{i}"} for i in range(len(verdicts))]
    labels = {f"s:{i}": {"task": "writing", "correction": v, "ctype": "tone_style" if v else "none",
                         "conf": "high"} for i, v in enumerate(verdicts) if v is not None}
    turns = {f"s:{i}": {"prompt": f"user {i}", "prev_turn": f"agent before {i}", "prev_turn_tools": 0}
             for i in range(len(verdicts))}
    return msgs, labels, turns


def test_export_builds_pair_from_accepted_fix():
    msgs, labels, turns = _pair_fixture([False, True, False])
    pairs, skipped = export.build_pairs(msgs, labels, turns)
    assert len(pairs) == 1
    p = pairs[0]
    assert p["prompt"] == "user 0"          # what the agent was answering
    assert p["rejected"] == "agent before 1"  # the turn that got corrected
    assert p["feedback"] == "user 1"        # the correction
    assert p["chosen"] == "agent before 2"    # the reply to the correction


def test_export_skips_when_fix_was_also_corrected():
    msgs, labels, turns = _pair_fixture([False, True, True])
    pairs, skipped = export.build_pairs(msgs, labels, turns)
    # message 1's fix was rejected; message 2 has no reaction after it
    assert pairs == []
    assert skipped["new reply was corrected too"] == 1
    assert skipped["session ended after correction"] == 1


def test_export_skips_edges_and_unlabelled_reactions():
    msgs, labels, turns = _pair_fixture([True, False])
    pairs, skipped = export.build_pairs(msgs, labels, turns)
    assert skipped["no earlier message"] == 1 and not pairs
    msgs, labels, turns = _pair_fixture([False, True, None])
    pairs, skipped = export.build_pairs(msgs, labels, turns)
    assert skipped["reaction not labelled"] == 1 and not pairs


def test_export_filters():
    msgs, labels, turns = _pair_fixture([False, True, False])
    turns["s:2"]["prev_turn_tools"] = 9
    assert export.build_pairs(msgs, labels, turns, max_tools=3)[1]["too many tool calls"] == 1
    assert export.build_pairs(msgs, labels, turns, tasks={"code"})[1]["task filtered"] == 1
    labels["s:1"]["conf"] = "low"
    assert export.build_pairs(msgs, labels, turns, high_only=True)[1]["low confidence"] == 1


def test_redact_common_secrets():
    text = ("key sk-ant-api03-" + "a" * 30 + " and ghp_" + "b" * 36 + " and AKIA" + "C" * 16
            + " Bearer " + "d" * 30)
    clean, n = export.redact(text)
    assert n == 4 and "sk-ant" not in clean and "ghp_" not in clean and "AKIA" not in clean
    assert export.redact("nothing secret here")[1] == 0


def test_redact_assignments_keeps_name_and_spares_placeholders():
    clean, n = export.redact("$env:XI_API_KEY='" + "Q" * 32 + "'")
    assert n == 1 and clean == "$env:XI_API_KEY='[REDACTED]'"
    assert export.redact("XI_API_KEY=your-key-here")[1] == 0


def test_export_ctype_filter():
    msgs, labels, turns = _pair_fixture([False, True, False])
    assert export.build_pairs(msgs, labels, turns, ctypes={"wrong_assumption"})[1]["correction type filtered"] == 1
    assert len(export.build_pairs(msgs, labels, turns, ctypes={"tone_style"})[0]) == 1
