# AGENTS.md

Instructions for any coding agent (Claude Code, Codex, Cursor, Hermes itself) working in this repo. Read this file fully before writing code. Humans should read it too.

## What this project is

**Hermes Screen** is a plugin for [Hermes Agent](https://github.com/NousResearch/hermes-agent) (Nous Research) that gives Hermes a TV. A user asks Hermes what to watch from any surface (CLI, Telegram, Discord, Desktop). Hermes picks something they will actually like from the services they pay for, then turns on the TV and plays it. Hermes can also put anything else on the TV: a YouTube tutorial at a timestamp, a web page, a briefing.

It is our entry for the **Hermes Agent Plugin Hackathon**. Hard deadline: **Nov 11, 2026, 5PM EST**. Judges score usefulness, reliability, polish, creativity, and favor plugins that do more than a prompt or a skill could.

Read these before starting a task:

1. `SOUL.md` for what we care about and how the plugin should feel.
2. `docs/PRD.md` for what we are building.
3. `docs/ARCHITECTURE.md` for how it fits together.
4. `docs/PLAN.md` for what is next and what is done.
5. `docs/RESEARCH.md` for verified facts vs things still unverified.

## Golden rules

1. **Verify, don't assume.** The Hermes plugin API, Roku channel IDs, TMDB provider IDs, and deep link behavior are listed in `docs/RESEARCH.md` with a status. If something is marked `UNVERIFIED`, check the real docs or real device before relying on it, then update the status.
2. **Scope is sacred.** The deadline is fixed. Only work on items in `docs/PLAN.md`. If you think something new is needed, add it under "Proposed" in the plan and keep going on the current task.
3. **Reliability over features.** Every network call has a timeout. Every failure returns a clear, human message. Never tell the user something is playing without checking the device afterward.
4. **No hardware in tests.** Unit tests mock Roku, Chromecast, and TMDB. Catalog CI will not have a TV.
5. **No secrets in git.** API keys come from config or environment. See `.env.example`.
6. **Small, reviewable changes.** One concern per commit. Keep the tree runnable at every commit.
7. **Write it down.** Non obvious choices go in `docs/DECISIONS.md`. Finished tasks get checked off in `docs/PLAN.md`. New facts go in `docs/RESEARCH.md`.

## Repo layout (target)

```
hermes-screen/
├── AGENTS.md              # you are here
├── CLAUDE.md              # points Claude Code to this file
├── SOUL.md                # project values, voice, product taste
├── README.md              # user facing: install, configure, use
├── docs/
│   ├── BRIEF.md           # original one page brief
│   ├── PRD.md             # product requirements
│   ├── ARCHITECTURE.md    # modules, tools, data flow
│   ├── PLAN.md            # milestones + task checklist (living)
│   ├── DECISIONS.md       # decision log (living)
│   ├── RESEARCH.md        # verified facts + open questions (living)
│   ├── DEMO.md            # 90 second demo script
│   └── SUBMISSION.md      # hackathon submission checklist
├── hermes_screen/         # plugin package (created when building starts)
│   ├── devices/           # roku.py, chromecast.py, discovery
│   ├── catalog/           # tmdb.py, provider mapping
│   ├── taste/             # history + taste profile store
│   ├── watcher.py         # background "what's playing" poller
│   └── tools.py           # tools registered with Hermes
└── tests/
```

The exact plugin manifest and entry point depend on the Hermes plugin API. Confirm them from the official developer guide before creating `hermes_screen/`, and record what you find in `docs/RESEARCH.md`.

## Stack and conventions

- **Language:** Python 3.11+ (Hermes is Python).
- **HTTP:** `httpx` with explicit timeouts (default 5s for LAN, 10s for TMDB).
- **Chromecast:** `pychromecast`.
- **Discovery:** SSDP for Roku (raw UDP socket), zeroconf for Chromecast (via pychromecast).
- **Tests:** `pytest`, with `respx` for mocking httpx.
- **Lint/format:** `ruff` (lint + format). Type hints on public functions.
- **Data:** plain JSON or SQLite in the plugin's data directory. No external database.
- Keep dependencies minimal. Every new dependency needs a one line reason in `docs/DECISIONS.md`.

## Tool design rules (for Hermes tools)

- Tool names are `snake_case` and start with a clear domain: `tv_`, `find_`, `taste_`.
- Descriptions are written for the model: say when to use the tool and what it returns.
- Return structured, small results (dicts with short fields), not raw API dumps.
- Errors come back as data the model can explain (`{"ok": false, "reason": "...", "hint": "..."}`), not stack traces.
- Tools must be safe to call twice. Launching the same title twice should not break anything.

## Commands

These will be filled in once the package exists. Keep this section accurate.

```bash
# setup
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# test
pytest -q

# lint
ruff check . && ruff format --check .

# try against a real Roku (manual)
python -m hermes_screen.devices.roku discover
```

## Definition of done (for any task)

- Code works against mocks in tests, and against the real device if it touches hardware.
- `pytest` and `ruff` pass.
- `docs/PLAN.md` updated (task checked, notes added).
- Any new fact in `docs/RESEARCH.md`, any choice in `docs/DECISIONS.md`.
- README updated if user facing behavior changed.

## When you are stuck

Write the blocker at the top of `docs/PLAN.md` under "Blockers" with what you tried, then move to the next unblocked task. Do not silently work around a hardware or API limitation; surface it.
