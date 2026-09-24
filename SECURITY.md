# Security and privacy

pushback reads your coding-agent transcripts, which can hold client work,
personal data and credentials.

- `extract`, `audit`, `report` and `export` run locally and send nothing.
- `label` and `rules` send message text to the model provider you configure,
  and ask before they do. `rules --prompt-file` lets you avoid that entirely.
- The export's secret scrub is best effort. Read an export before sharing it.

To report a vulnerability, for example a path where message text could leave
your machine without that prompt, use GitHub's private vulnerability reporting
on this repository (Security tab → Report a vulnerability). Please don't open
a public issue for it.
