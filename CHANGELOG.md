# Changelog

## 0.1.0 (2026-09-24)

First release.

- `extract`: messages you typed and full agent turns from Claude Code transcripts, with stable `session:index` ids; rejected tool calls and interrupts counted separately.
- `label`: task type and correction labels from Claude, resumable, with failed batches retried rather than counted.
- `audit`: stratified hand-check that bounds the label error.
- `report`: correction rate per task with Wilson 95% intervals and audit-corrected totals.
- `rules`: CLAUDE.md rules from recurring corrections, with support recounted from cited ids and existing rules that keep getting broken flagged; `--prompt-file` / `--from-response` for use without an API key.
- `export`: corrections as prompt / chosen / rejected pairs with a best-effort secret scrub.
