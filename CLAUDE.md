# CLAUDE.md

All agent instructions for this repo live in [AGENTS.md](./AGENTS.md). Read it first, then [SOUL.md](./SOUL.md).

Quick reminders:

- Check `docs/PLAN.md` for the current task before writing code.
- Anything marked `UNVERIFIED` in `docs/RESEARCH.md` must be checked before you depend on it.
- Run `pytest -q`, `ruff check .` and `hermes plugins doctor . --ci` before you call a task done.
- Jellyfin is the source of truth for the library and watch history; the Roku is only the output.
- Update `docs/PLAN.md`, `docs/DECISIONS.md`, and `docs/RESEARCH.md` as you go.
