"""The labelling instructions and the JSON schema the model must answer in.

These are the instructions that scored precision 0.97 / recall 0.80 against 91
hand labels on the author's own logs. Change them and re-run `pushback audit`
before trusting new numbers.
"""

TASKS = ["code", "writing", "media", "research", "ops", "meta"]

# A fixed topic list per task keeps labels consistent across batches and comparable across users.
TOPICS = {
    "code": ["frontend", "backend-api", "cli-tool", "database", "tests", "auth-security", "integrations",
             "data-ml", "scripts-automation", "agent-prompts", "debugging", "pr-workflow", "other"],
    "writing": ["social-post", "client-message", "email", "docs-readme", "video-script", "proposal-report",
                "spec-plan", "other"],
    "media": ["image", "video", "diagram", "ui-design", "other"],
    "research": ["benchmark-experiment", "data-analysis", "market-leads", "paper-reading", "trading-analysis",
                 "other"],
    "ops": ["deploy-hosting", "git-github", "accounts-credentials", "config-settings", "browser-automation",
            "ci", "other"],
    "meta": ["planning", "memory-context", "advice", "status-check", "other"],
}
ALL_TOPICS = sorted({t for ts in TOPICS.values() for t in ts})

CTYPES = [
    "none", "writing_content", "tone_style", "wrong_assumption", "scope",
    "broken_output", "code", "misread_request", "process",
]

TOPIC_LINES = "\n".join(f"- {task}: {', '.join(topics)}" for task, topics in TOPICS.items())

SYSTEM = """You label messages a user sent to an AI coding agent. The agent is also used for writing, research and ops.

Each item has: id, prev_assistant (the end of the agent's previous reply), user (the user's next message).
Give every item four labels.

task: the work in progress, judged from BOTH prev_assistant and user. Pick one.
- code: writing, fixing or reviewing code, tests, builds, PRs, schemas
- writing: prose for humans, such as social posts, business messages, emails, scripts, docs, READMEs, proposals
- media: images, thumbnails, video, animation, design visuals
- research: benchmarks, experiments, data analysis, paper reading, market research
- ops: deploys, git/GitHub admin, accounts, config, credentials, infra, tool setup, browser automation
- meta: planning and strategy talk, advice, saving memory or context, chit-chat, session management

topic: the specific kind of work, chosen from the list for the task you picked. Use "other" if none fits.
""" + TOPIC_LINES + """

correction: true ONLY if the user rejects, fixes or redirects something the agent just did, said, wrote or proposed because it was wrong, unwanted, incomplete or not what they asked.
It is false for all of these:
- new tasks, next steps, "now do X", moving on, "save to memory"
- answers to the agent's questions (a plain "no" to a yes/no question is an answer)
- choosing between options the agent offered, or reprioritising ("first do X")
- approvals, thanks, reassurance, jokes
- pasted logs or content with no reaction to the agent's work
- complaints about third parties or tools
- the user's own new idea or realisation

ctype: "none" unless correction is true, otherwise one of:
- writing_content: the text missed or misstated content ("you didn't mention X", "start it with Y")
- tone_style: voice, length, format, "sounds AI", "looks AI", design style
- wrong_assumption: the agent assumed something false about the user, their state or their facts
- scope: did too much, added unrequested things, offered unwanted things
- broken_output: a non-code output (file, image, video, deploy) is missing, stale or broken
- code: a code bug, failing build or test, or wrong technical implementation
- misread_request: misunderstood what was asked
- process: how the agent works (tool or model choice, don't ask, verify first)

conf: "high" or "low".
Return exactly one label per input id, and never repeat message text."""

SCHEMA = {
    "type": "object",
    "properties": {
        "labels": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "task": {"type": "string", "enum": TASKS},
                    "topic": {"type": "string", "enum": ALL_TOPICS},
                    "correction": {"type": "boolean"},
                    "ctype": {"type": "string", "enum": CTYPES},
                    "conf": {"type": "string", "enum": ["high", "low"]},
                },
                "required": ["id", "task", "topic", "correction", "ctype", "conf"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["labels"],
    "additionalProperties": False,
}
