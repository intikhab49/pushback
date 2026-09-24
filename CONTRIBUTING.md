# Contributing

Thanks for helping. A few things keep this project honest.

## Setup

```bash
git clone https://github.com/intikhab49/pushback
cd pushback
pip install -e ".[test]"
python -m pytest -q
```

Tests never call a model. Anything that talks to an API takes a client you can
replace with a fake, as `tests/test_pushback.py` does.

## Most wanted

- **Readers for other agents' transcripts** (Codex, Cursor, Aider, OpenCode).
  An extractor only has to yield the messages a person typed, the agent turn
  before each one, and silent corrections (rejected tool calls, interrupts).
- **Audit data.** If you run `audit` on your own logs, the precision and recall
  you get, with no message text, helps show how well the rubric carries over.

## Rules for changes

- Never commit transcript text, labels or exports, even in test fixtures. Write
  synthetic ones.
- A change to the labelling rubric in `src/pushback/prompt.py` needs a fresh
  `audit` run, with the before and after precision/recall in the pull request.
- `report` output must stay counts only.
- If you change the art, edit `.github/scripts/art.py` and rerun it. Don't edit
  the SVGs by hand.
