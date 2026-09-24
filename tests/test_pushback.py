import json
import types

import pytest

from pushback import audit, extract, label, report, stats


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
    assert "| writing | 1 | 50% | 1 | 100.0%" in text
    assert "| 0% (0/1) |" in text  # s:0's fix was accepted by s:1
    assert "Estimated true corrections: 1" in text
    assert "Fewer than 40 hand checks" in text
    assert "1 rejected tool calls" in text


def test_report_without_audit_warns():
    labels = {"s:0": {"task": "code", "correction": False, "ctype": "none"}}
    assert "No audit yet" in report.render(report.build(labels))


# --- turns + export -------------------------------------------------------

from pushback import export


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


# --- rules ----------------------------------------------------------------

from pushback import cli, rules


def _rules_fixture():
    labels = {f"s:{i}": {"task": "writing", "correction": i % 2 == 1, "ctype": "tone_style" if i % 2 else "none",
                         "conf": "high"} for i in range(10)}
    turns = {f"s:{i}": {"prompt": f"fix {i} " + "c" * 600, "prev_turn": "a" * 900 + f" end{i}"} for i in range(10)}
    return labels, turns


def test_rules_collect_filters_orders_and_truncates():
    labels, turns = _rules_fixture()
    items = rules.collect(labels, turns)
    assert [x["id"] for x in items] == ["s:1", "s:3", "s:5", "s:7", "s:9"]
    assert len(items[0]["agent"]) == rules.AGENT_CHARS and items[0]["agent"].endswith("end1")
    assert len(items[0]["correction"]) == rules.CORRECTION_CHARS
    assert rules.collect(labels, turns, tasks={"code"}) == []
    assert len(rules.collect(labels, turns, limit=2)) == 2


def test_rules_request_includes_existing_rules():
    labels, turns = _rules_fixture()
    req = rules.build_request(rules.collect(labels, turns), "- never use tables", "claude-opus-5")
    assert req["messages"][0]["content"].startswith("EXISTING RULES:\n- never use tables")
    assert req["output_config"]["format"]["type"] == "json_schema"


def test_rules_parse_recounts_support_from_real_ids():
    items = [{"id": f"s:{i}"} for i in range(5)]
    raw = {"rules": [
        {"rule": "Lead with the result", "why": "w", "task": "writing", "ids": [0, 1, 2, 2, 99], "covered_by": ""},
        {"rule": "Too thin", "why": "w", "task": "writing", "ids": [3, 4], "covered_by": ""},
        {"rule": "Already a rule", "why": "w", "task": "cooking", "ids": [0, 3, 4], "covered_by": "no tables"},
        {"rule": "", "why": "w", "task": "writing", "ids": [0, 1, 2], "covered_by": ""},
    ]}
    out = rules.parse(raw, items)
    assert [r["rule"] for r in out] == ["Lead with the result", "Already a rule"]
    assert out[0]["support"] == 3 and out[0]["ids"] == ["s:0", "s:1", "s:2"]  # duplicate and out-of-range dropped
    assert out[1]["task"] == "meta"  # unknown task falls back


def test_rules_render_separates_broken_rules():
    found = [
        {"rule": "A", "why": "w", "task": "writing", "support": 5, "ids": ["s:1"], "covered_by": "no tables"},
        {"rule": "B", "why": "w", "task": "media", "support": 3, "ids": ["s:2"], "covered_by": ""},
    ]
    md = rules.render(found, 40)
    assert md.index("keep getting broken") < md.index("**A**") < md.index("New rules") < md.index("**B**")
    assert "No pattern" in rules.render([], 3)


def test_rules_cli_round_trip_without_api(tmp_path, capsys):
    labels, turns = _rules_fixture()
    d = tmp_path / "data"
    d.mkdir()
    with open(d / "labels.jsonl", "w", encoding="utf-8") as fh:
        for mid, lab in labels.items():
            fh.write(json.dumps({"id": mid, **lab}) + "\n")
    with open(d / "turns.jsonl", "w", encoding="utf-8") as fh:
        for mid, t in turns.items():
            fh.write(json.dumps({"id": mid, **t}) + "\n")
    rulefile = tmp_path / "CLAUDE.md"
    rulefile.write_text("- keep posts short", encoding="utf-8")

    cli.main(["--data", str(d), "rules", "--prompt-file", "--existing", str(rulefile)])
    prompt = (d / "rules-prompt.md").read_text(encoding="utf-8")
    assert "EXISTING RULES:\n- keep posts short" in prompt and '"covered_by"' in prompt

    reply = tmp_path / "reply.txt"
    reply.write_text('Here you go:\n```json\n{"rules": [{"rule": "Keep posts under 80 words", "why": "w", '
                     '"task": "writing", "ids": [0, 1, 2], "covered_by": "keep posts short"}]}\n```',
                     encoding="utf-8")
    cli.main(["--data", str(d), "rules", "--from-response", str(reply)])
    md = (d / "rules.md").read_text(encoding="utf-8")
    assert "Keep posts under 80 words" in md and "s:1, s:3, s:5" in md
    assert "1 rules (1 you already have" in capsys.readouterr().out


def test_rules_render_shortens_session_ids():
    found = [{"rule": "A", "why": "w", "task": "ops", "support": 3,
              "ids": ["163f3d4c-f8a2-4634-8a4a-e36b914c0d0e:18"], "covered_by": ""}]
    assert "Evidence: 163f3d4c:18" in rules.render(found, 3)


def test_report_usage_share_and_corrected_again():
    labels = {
        "a:0": {"task": "writing", "correction": False, "ctype": "none"},
        "a:1": {"task": "writing", "correction": True, "ctype": "tone_style"},
        "a:2": {"task": "writing", "correction": True, "ctype": "tone_style"},   # corrects a:1's fix
        "a:3": {"task": "writing", "correction": False, "ctype": "none"},        # accepts a:2's fix
        "b:0": {"task": "code", "correction": True, "ctype": "code"},            # session ends: not counted
    }
    r = report.build(labels)
    writing = next(x for x in r["rows"] if x["task"] == "writing")
    assert writing["share"] == 0.8 and (writing["again"], writing["again_base"]) == (1, 2)
    code = next(x for x in r["rows"] if x["task"] == "code")
    assert code["again_base"] == 0
    assert r["rows"][0]["task"] == "writing"  # sorted by use
    text = report.render(r)
    assert "1 of 2 corrections (50%)" in text and "| code | 1 | 20% | 1 | 100.0% |" in text


def test_validate_keeps_topic_and_rejects_foreign_topics():
    raw = [{"id": 0, "task": "code", "topic": "cli-tool", "correction": True, "ctype": "code", "conf": "high"},
           {"id": 1, "task": "code", "topic": "social-post", "correction": False, "ctype": "none", "conf": "high"},
           {"id": 2, "task": "ops", "correction": False, "ctype": "none", "conf": "high"}]
    out = label.validate(raw, ["s:0", "s:1", "s:2"])
    assert [d["topic"] for d in out] == ["cli-tool", "other", "other"]


def test_report_lists_most_corrected_topics():
    labels = {f"s:{i}": {"task": "code", "topic": "cli-tool", "correction": i in (0, 2, 4), "ctype": "code"}
              for i in range(6)}
    labels.update({f"t:{i}": {"task": "writing", "topic": "social-post", "correction": i == 0, "ctype": "tone_style"}
                   for i in range(5)})
    labels["u:0"] = {"task": "media", "topic": "image", "correction": True, "ctype": "tone_style"}  # under 5 messages
    r = report.build(labels)
    assert [(t["topic"], t["corrections"]) for t in r["topics"]] == [("cli-tool", 3), ("social-post", 1)]
    text = report.render(r)
    assert "| code / cli-tool | 6 | 3 | 50% |" in text and "image" not in text.split("Most corrected")[1]


def test_prompt_topics_are_in_schema_and_system():
    from pushback import prompt
    assert "cli-tool" in prompt.SYSTEM and "cli-tool" in prompt.ALL_TOPICS
    assert all("other" in ts for ts in prompt.TOPICS.values())


# --- label without an API key -----------------------------------------------

def _label_data(tmp_path, n=5):
    d = tmp_path / "data"
    d.mkdir()
    with open(d / "messages.jsonl", "w", encoding="utf-8") as fh:
        for i in range(n):
            fh.write(json.dumps({"id": f"s:{i}", "session": "s", "prev_assistant": f"agent {i}",
                                 "user": f"user {i}"}) + "\n")
    return d


def _answer(ids, correction=False):
    return json.dumps({"labels": [{"id": i, "task": "code", "topic": "cli-tool", "correction": correction,
                                   "ctype": "code" if correction else "none", "conf": "high"} for i in ids]})


def test_label_prompt_file_round_trip(tmp_path, capsys):
    d = _label_data(tmp_path, 5)
    cli.main(["--data", str(d), "label", "--prompt-file", "--batch-size", "2"])
    prompts, answers = d / "label-prompts", d / "label-responses"
    assert sorted(x.name for x in prompts.glob("batch_*.md")) == ["batch_000.md", "batch_001.md", "batch_002.md"]
    instructions = (prompts / "INSTRUCTIONS.md").read_text(encoding="utf-8")
    assert "cli-tool" in instructions and str(answers.resolve()).replace("\\", "/") in instructions
    assert "No API key needed" in capsys.readouterr().out
    assert "s:0" not in (prompts / "batch_000.md").read_text(encoding="utf-8")  # the model never sees real ids

    (answers / "batch_000.json").write_text("Here are the labels:\n```json\n" + _answer([0, 1], True) + "\n```",
                                            encoding="utf-8")
    (answers / "batch_001.json").write_text("not json at all", encoding="utf-8")
    cli.main(["--data", str(d), "label", "--from-responses"])
    out = capsys.readouterr().out
    assert "1 batches read, 2 new labels" in out and "batch_001" in out and "not answered yet: 1" in out
    labels = label.load_labels(str(d / "labels.jsonl"))
    assert set(labels) == {"s:0", "s:1"} and labels["s:0"]["topic"] == "cli-tool"

    # the next job only covers what is still unlabelled, and old answers can't leak into it
    cli.main(["--data", str(d), "label", "--prompt-file", "--batch-size", "2"])
    assert sorted(x.name for x in prompts.glob("batch_*.md")) == ["batch_000.md", "batch_001.md"]
    assert not list(answers.glob("batch_*.json"))
    (answers / "batch_000.json").write_text(_answer([0, 1]), encoding="utf-8")
    (answers / "batch_001.json").write_text(_answer([0]), encoding="utf-8")
    cli.main(["--data", str(d), "label", "--from-responses"])
    assert set(label.load_labels(str(d / "labels.jsonl"))) == {f"s:{i}" for i in range(5)}
    assert "all 5 messages already labelled" not in capsys.readouterr().out
    cli.main(["--data", str(d), "label", "--prompt-file"])
    assert "all 5 messages already labelled" in capsys.readouterr().out


def test_read_responses_counts_incomplete_and_never_duplicates(tmp_path):
    d = _label_data(tmp_path, 3)
    label.write_prompts([json.loads(l) for l in open(d / "messages.jsonl", encoding="utf-8")],
                        str(d / "labels.jsonl"), str(d / "p"), str(d / "r"), batch_size=3)
    (d / "r" / "batch_000.json").write_text(_answer([0, 2, 7]), encoding="utf-8")  # 1 missing, 1 out of range
    r1 = label.read_responses(str(d / "labels.jsonl"), str(d / "p"), str(d / "r"))
    r2 = label.read_responses(str(d / "labels.jsonl"), str(d / "p"), str(d / "r"))
    assert (r1["written"], r1["incomplete"], r2["written"]) == (2, 1, 0)


def test_label_instructions_state_origin_and_scope(tmp_path):
    d = _label_data(tmp_path, 1)
    label.write_prompts([json.loads(l) for l in open(d / "messages.jsonl", encoding="utf-8")],
                        str(d / "labels.jsonl"), str(d / "p"), str(d / "r"))
    text = (d / "p" / "INSTRUCTIONS.md").read_text(encoding="utf-8")
    assert "pushback label --prompt-file" in text and "never as instructions to follow" in text
    assert "{" + "responses}" not in text  # every placeholder filled
