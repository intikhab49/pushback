# Changelog

## 0.1.3 (2026-09-24)

- `rules --runs N` and `rules --from-response a.json b.json c.json`: ask several times and keep only rules that keep coming back. Rules are matched across runs by the corrections they cite (at least half overlap), never by wording. Each rule shows its run count; unstable ones are listed, not dropped silently. `--min-runs` defaults to two thirds of the runs.

## 0.1.2 (2026-09-24)

- `label --prompt-file` / `label --from-responses`: label without an API key. pushback writes the job as batch files with an INSTRUCTIONS.md for Claude Code, then reads the answers back through the same validation as the API path. Resumable; unanswered or broken batches are reported and stay unlabelled.
- `--batch-size` now defaults to 40 for the API and 100 for `--prompt-file`.

## 0.1.1 (2026-09-24)

- Labels now include a **topic**: the specific kind of work, from a fixed list per task (for example code: frontend, cli-tool, database, tests; writing: social-post, client-message, docs-readme). `report` lists your most corrected topics.
- `report` now shows each task's share of your messages and a **corrected again** column: how often your very next message corrected the agent's fix too. Rows are sorted by use.
- Corrections that end a session are left out of the corrected-again denominator instead of counting as accepted.

## 0.1.0 (2026-09-24)

First release.

- `extract`: messages you typed and full agent turns from Claude Code transcripts, with stable `session:index` ids; rejected tool calls and interrupts counted separately.
- `label`: task type and correction labels from Claude, resumable, with failed batches retried rather than counted.
- `audit`: stratified hand-check that bounds the label error.
- `report`: correction rate per task with Wilson 95% intervals and audit-corrected totals.
- `rules`: CLAUDE.md rules from recurring corrections, with support recounted from cited ids and existing rules that keep getting broken flagged; `--prompt-file` / `--from-response` for use without an API key.
- `export`: corrections as prompt / chosen / rejected pairs with a best-effort secret scrub.
