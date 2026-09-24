# pushback

How often do you correct your coding agent, and on what kind of work?

`pushback` reads your Claude Code transcripts, labels every message you sent
with Claude, and tells you what share of your messages were corrections,
broken down by the kind of work in progress (code, writing, media, research,
ops, meta). A hand-check step tells you how far to trust the labels.

On the author's own 1,633 messages:

| task | messages | corrections | rate | 95% CI |
|---|---:|---:|---:|---|
| media | 114 | 49 | 43.0% | 34.3%–52.2% |
| writing | 429 | 106 | 24.7% | 20.9%–29.0% |
| research | 188 | 13 | 6.9% | 4.1%–11.5% |
| code | 340 | 20 | 5.9% | 3.8%–8.9% |
| meta | 297 | 14 | 4.7% | 2.8%–7.8% |
| ops | 265 | 12 | 4.5% | 2.6%–7.7% |

Against 91 hand-checked messages the labels had precision 0.97 and recall 0.80.
That's one person's logs. Run it on yours.

These rates describe a workflow, not a model. The author's code work runs
through skills, reference files, memory and a plan before the agent writes
anything, and CI catches mistakes before a human has to. Writing got none of
that. A low rate means the process around the agent is doing its job.

## Run it

```
pip install pushback          # or, from a clone: pip install -e .
pushback extract            # reads ~/.claude/projects, writes ./pushback-data/
pushback label              # sends your messages to Claude, resumable
pushback audit              # hand-check 40 messages
pushback report --markdown  # the table, with the audit folded in
pushback rules              # draft CLAUDE.md rules from your recurring corrections
pushback export             # your corrections as prompt/chosen/rejected pairs
```

`label` uses the Anthropic SDK, so it picks up `ANTHROPIC_API_KEY` or an
`ant auth login` profile. It defaults to `claude-opus-5` at low effort. Change
it with `--model`. To send through a gateway, set `ANTHROPIC_BASE_URL`.

## Turn recurring corrections into rules

```
pushback rules                                  # drafts rules into pushback-data/rules.md
pushback rules --existing CLAUDE.md notes/*.md  # also check against the rules you already have
pushback rules --prompt-file                    # no API key? writes the request to a file instead
pushback rules --from-response reply.json       # ...and reads Claude's answer back
```

The model groups corrections that share a cause and drafts one CLAUDE.md
instruction per group. Support is counted from the correction ids it cites,
not from its own numbers, and a rule needs at least 3 real corrections.

When you pass your existing rule files, the output splits in two:

- **Rules you already have that keep getting broken.** These are the useful
  ones. A rule that exists and still gets corrected isn't working: it's too
  vague, or the agent doesn't read it at the right moment.
- **New rules to consider.** Recurring corrections with no rule behind them.

No API key: `--prompt-file` writes the whole request to `rules-prompt.md`.
Ask Claude Code to answer it, save the JSON reply, then run `--from-response`.

## Export your corrections as preference pairs

```
pushback export                                        # all pairs -> pushback-data/dpo.jsonl
pushback export --ctype writing_content tone_style     # the cleanest pairs
pushback export --minimal                              # only prompt/chosen/rejected (TRL DPO columns)
```

Each correction you made becomes one row:

- `prompt`: your message the agent was answering
- `rejected`: the agent turn you corrected
- `chosen`: the agent's reply to your correction, kept only if your next message wasn't another correction
- `feedback`: the correction itself, for critique-and-revise formats

On the author's logs, 214 corrections gave 124 pairs. The biggest loss:
70 corrections (a third) had their fix corrected too, so there was no
accepted answer to pair with.

What to know before you train on it:

- "You didn't correct it again" is weak evidence that the fix was good.
- The fix was written after seeing your feedback. For corrections of a wrong
  assumption ("I already sent that"), `chosen` answers the correction rather
  than the prompt. Those make poor DPO pairs, so filter with `--ctype`.
- Only agent text is exported. File edits and commands are tool calls, so a
  code correction's pair may hold the explanation without the diff. Use
  `--max-tools` to drop tool-heavy turns.
- Secrets are scrubbed on a best-effort basis (API key shapes, tokens,
  `NAME_KEY=value`). Read the file before you use it.
- Your transcripts probably contain other people's information. Keep the
  export local unless every conversation in it is yours to share.
- If the agent is Claude, Anthropic's terms restrict using its outputs to
  build competing models. Treat this as a personal dataset or eval set.

## What counts as a correction

A message where you reject, fix or redirect something the agent just did,
said, wrote or proposed. New tasks, answers to its questions, picking between
its options, approvals and pasted logs don't count. The full rubric is in
`src/pushback/prompt.py`. If you change it, run `audit` again.

Rejected tool calls and interrupts carry no text, so they're counted
separately and bucketed by the action you stopped (a code edit, a shell
command, and so on).

## Privacy

- `extract` and `report` never leave your machine. `report` prints counts only.
- `label` sends each message, plus the end of the agent reply before it, to the
  model provider. If your logs contain client work, check that provider's data
  policy first. `label` asks before it sends anything.
- `pushback-data/` holds your raw messages. It's in `.gitignore`. Keep it there.

## Your history is shorter than you think

Claude Code deletes transcripts older than 30 days by default. To keep more,
set `cleanupPeriodDays` in `~/.claude/settings.json`, for example
`"cleanupPeriodDays": 365`. It only affects transcripts that still exist.

## How the numbers are computed

- Rates per task come with Wilson 95% intervals.
- `audit` samples half from messages the model flagged and half from the rest.
  The report estimates the true count as
  `flagged × precision + unflagged × miss rate`, with a range built from both
  strata's intervals.
- A batch that fails stays unlabelled and is retried on the next run. It's
  never counted as "not a correction".

## Limits

- Claude Code transcripts only, for now.
- Task type is judged from the last agent reply and your message, not the whole session.
- The rubric was tuned on one person's logs.

MIT licensed.
