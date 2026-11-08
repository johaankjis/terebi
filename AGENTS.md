# AGENTS.md

Instructions for any coding agent (Claude Code, Codex, Cursor, Hermes itself) working in this repo. Read this file fully before writing code. Humans should read it too.

## What this project is

**Hermes Screen** is a plugin for [Hermes Agent](https://github.com/NousResearch/hermes-agent) (Nous Research) that lets Hermes run your home theater. You ask Hermes what to watch from any surface (CLI, Telegram, Discord, Desktop). It picks from your own **Jellyfin** library using real watch history, then plays it on your **Roku** TV through the Jellyfin Roku app's deep link support. It also handles playback control, next episode, resume, a scheduled movie night vote, and YouTube to TV.

It is our entry for the **Hermes Agent Plugin Hackathon**. Hard deadline: **Wed Nov 11, 2026, 5PM EST**. Judges score usefulness, reliability, polish, creativity, and favor plugins that do more than a prompt or a skill could.

Read these before starting a task:

1. `SOUL.md` for what we care about and how the plugin should feel.
2. `docs/BRIEF.md` for the one page version.
3. `docs/PRD.md` for what we are building.
4. `docs/ARCHITECTURE.md` for how it fits together.
5. `docs/PLAN.md` for what is next and what is done.
6. `docs/RESEARCH.md` for verified facts vs things still unverified.

## Golden rules

1. **Verify, don't assume.** Facts in `docs/RESEARCH.md` have a status. If something is `UNVERIFIED`, check the real docs, real server or real Roku before relying on it, then update the status.
2. **Scope is sacred.** The deadline is fixed. Only work on items in `docs/PLAN.md`. New ideas go under "Proposed" in the plan.
3. **Reliability over features.** Every network call has a timeout. Every failure returns a clear, human message. Never tell the user something is playing without checking the Roku afterward.
4. **No hardware in tests.** Unit tests mock Jellyfin and Roku with `respx`. Catalog CI has no TV and no Jellyfin server.
5. **Follow the catalog rules.** We must pass `hermes plugins validate`. In particular: declared tools/hooks must match what `register()` registers, secrets come only through Hermes (`requires_env` / `config_schema` secrets read via the secret scope, never `.env` files or raw `os.environ`), no patching Hermes core, no self updating code, no `eval` in Desktop code. See `docs/RESEARCH.md` > Catalog rules.
6. **No secrets in git.** See `.env.example` for local dev only.
7. **Small, reviewable changes.** One concern per commit. Keep the tree runnable at every commit.
8. **Write it down.** Choices go in `docs/DECISIONS.md`. Finished tasks get checked off in `docs/PLAN.md`. New facts go in `docs/RESEARCH.md`.

## Repo layout (target)

```
hermes-screen/
├── AGENTS.md              # you are here
├── CLAUDE.md              # points Claude Code to this file
├── SOUL.md                # project values, voice, product taste
├── README.md              # user facing: install, configure, use (renders on the catalog page)
├── plugin.yaml            # Hermes manifest (created when building starts)
├── __init__.py            # register(ctx): tools, commands, hooks, blueprint
├── schemas.py             # tool schemas the model reads
├── tools.py               # thin handlers: validate, call core, shape results
├── hermes_screen/
│   ├── jellyfin.py        # Jellyfin API client
│   ├── roku.py            # Roku ECP client + SSDP discovery
│   ├── picker.py          # filtering + ranking + one line reasons
│   ├── config.py          # read settings and secrets through ctx
│   └── errors.py          # error model
├── desktop/               # optional: Desktop plugin (poster card directive)
├── docs/
│   ├── BRIEF.md  PRD.md  ARCHITECTURE.md  PLAN.md
│   ├── DECISIONS.md  RESEARCH.md  DEMO.md  SUBMISSION.md
└── tests/
```

The Hermes loader expects `plugin.yaml` and `__init__.py` at the plugin root (verified in the dev guide). Keep that.

## Stack and conventions

- **Language:** Python 3.11+.
- **HTTP:** `httpx` with explicit timeouts (3s for Roku on the LAN, 8s for Jellyfin).
- **Discovery:** SSDP for Roku (raw UDP socket, 3s window), with a manual IP setting as fallback.
- **Tests:** `pytest`, `respx` for mocking httpx.
- **Lint/format:** `ruff`. Type hints on public functions.
- **State:** `ctx.state` for small plugin state (10 MiB cap); `plugin_db("hermes-screen")` SQLite only if we outgrow it. Never write inside the plugin directory.
- Keep dependencies minimal. Every new dependency needs a one line reason in `docs/DECISIONS.md`, and must resolve under Hermes core constraints.

## Tool design rules

- Tool names are `snake_case` with a domain prefix: `tv_`, `library_`.
- Descriptions are written for the model: when to use it and what it returns.
- Return small structured results, not raw API dumps.
- Errors are data: `{"ok": false, "reason": "...", "hint": "..."}`, never stack traces.
- Tools are safe to call twice.
- `provides_tools` in `plugin.yaml` must list exactly the tools `register()` registers.

## Commands

Keep this section accurate as the package grows.

```bash
# setup
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"          # once pyproject exists

# test + lint
pytest -q
ruff check . && ruff format --check .

# Hermes checks (run from a machine with Hermes installed)
hermes plugins doctor . --ci
hermes plugins validate . --install-deps

# manual device checks
curl http://ROKU_IP:8060/query/apps
curl -d '' "http://ROKU_IP:8060/launch/JELLYFIN_CHANNEL_ID?contentId=ITEM_ID&mediaType=movie"
```

## Definition of done (for any task)

- Works against mocks in tests, and against the real Roku + Jellyfin if it touches them.
- `pytest`, `ruff`, and `hermes plugins doctor . --ci` pass.
- `docs/PLAN.md` updated; new facts in `RESEARCH.md`; choices in `DECISIONS.md`.
- README updated if user facing behavior changed.

## When you are stuck

Write the blocker at the top of `docs/PLAN.md` under "Blockers" with what you tried, then move to the next unblocked task. Never silently work around a device or API limitation; surface it.
