# Integration evidence — 2026-11-08

## Checkout and adoption

- Path: `/home/node/.t3/worktrees/terebi/t3-e9bc44d9`
- Branch: `t3/integrate-jellyfin-client`
- Initial HEAD: `4fd89d1b0cad82284f960be146bab444cfc9ff13`, clean.
- Verified with `pwd`, `git status --short`, `git branch --show-current`,
  `git rev-parse HEAD`, and `git worktree list`: separate from manager
  `/home/node/projects/terebi` and workers `t3-4241fccf`, `t3-9ea13dee`.
- Inspected then cherry-picked in order, without conflicts:
  - `4ebcb722500fffea9f1af65f909298a1b294d888` → `310d83e52fbcc0d7e991ff41f5c78c6b134d6fc0`
  - `c4c6c83e171a646b830b418cda79b6e420ecdf77` → `eb08f2d6444ccbb098ff52386a3a105d0c5bbf13`
- No manager/worker file edits, stash, main changes, pushes or PRs.

## Integration changes

Quoted YAML description; removed unimplemented Roku settings; retained exactly
`library_status`. Settings reject non-text values. Reads, imports, construction
and runtime failures return structured errors without arbitrary exception text.
Handlers capture their own context, read secrets per call, and keep no global
context/client. Imports are package-relative; the entry point imports siblings
inside `register`, which also allows pytest collection in hyphenated directories.

Username matching is exact and case-sensitive (GUIDs remain normalized). Ambiguity
errors no longer enumerate server-supplied user names. Session responses over the
scan cap cannot verify a target, because unseen entries could be duplicates.
`verified` is explicitly item identity, separately from `playing`/`paused`.

Setuptools maps a complete native layout into `hermes_screen_plugin` in wheels;
repository installation remains native-directory based. Production dependency is
only httpx. Ruff formatting uses the skeleton's 100-column policy.

## Automated checks

Python 3.11.2; uv 0.13.7 installed through Astral's official installer into
`/tmp/hermes-screen-integrator-bin` (system Python lacked pip).

```bash
uv venv .venv
uv pip install --python .venv/bin/python -e '.[dev]'
.venv/bin/pytest -q
.venv/bin/ruff check .
.venv/bin/ruff format --check .
git diff --check
uv build --wheel --out-dir /tmp/hermes-screen-integration-dist
```

Results: **220 passed**; Ruff check and format check pass; diff check passes.
Tests include real handler → real JellyfinClient → respx, real YAML parsing,
config/secret/import/runtime error redaction, context isolation, exact usernames,
scan-cap ambiguity and paused/unknown playback semantics. All HTTP is mocked.
Editable install and wheel build/install succeeded. Wheel contains entry point,
manifest, tools, schemas and nested client/config/error package.

## Official Hermes checks

Upstream: https://github.com/NousResearch/hermes-agent, released tag **v0.22.0**,
SHA **e06df9c2eae6901f4c88f464e0ae6e753c0428b8**.
Checkout: `/tmp/hermes-screen-integrator-upstream` (detached).
Installed with uv into `/tmp/hermes-screen-hermes-venv`, using Python 3.14.10 and
upstream dependencies; isolated `HERMES_HOME=/tmp/hermes-screen-integrator-home`.
No edits to upstream source. CLI version output:

```text
Hermes Agent v0.22.0 (2026.9.24) · stable · local e06df9c2eae6
Install directory: /tmp/hermes-screen-integrator-upstream
Install method: git
Python: 3.14.10
OpenAI SDK: 2.24.0
```

Commands (PATH includes the temporary uv and Hermes venv bins):

```bash
hermes --version
hermes plugins doctor /home/node/.t3/worktrees/terebi/t3-e9bc44d9 --ci
hermes plugins validate /home/node/.t3/worktrees/terebi/t3-e9bc44d9 --install-deps
```

Doctor output:

```text
manifest: hermes-screen 0.1.0 (standalone)
OK: runtime discovery, manifest parsing, import, and registration passed
registrations: 1 tool(s), 0 hook(s)
```

Validate passed: manifest parsing/fields, `requires_hermes`, config schema,
requires_env, loadable entry, one Python dependency, isolated capability probe,
exact tools/hooks/middleware declarations, no built-in tool collisions, safe
security scan, no core overrides. Isolation reports plugin host mode.
An intermediate rerun while packaging reported “Dependency inputs changed while
preparing publication; retry”; files were settled before the final rerun.

Final validate output (exit 0):

```text
→ Resolving Python dependencies…
  ✓ Resolving Python dependencies
  → Installing Python dependencies…
  ✓ Installing Python dependencies

✓ manifest — plugin.yaml parses
✓ manifest fields — name, version, description present
✓ requires_hermes — spec '>=0.22.0' parses
✓ config schema — shape valid
✓ requires_env — all entries UPPER_SNAKE
✓ loadable — entry: __init__.py
✓ python dependencies — 1 requirements from pyproject
✓ capability probe — register() ran in isolation
✓ declared tools — matches registrations
✓ declared hooks — matches registrations
✓ declared middleware — matches registrations
✓ built-in tool collisions — no collisions
✓ security scan — safe
✓ no core override — no runtime rebinds of Hermes core
◆ Isolation — runs in the plugin host (plugins.isolation: host)

Validation passed.
```

Additional smoke script: [tests/hermes_smoke.py](../tests/hermes_smoke.py).
Run from `/tmp`, with the upstream venv, respx installed, and plugin root absent
from `sys.path`:

```bash
python /home/node/.t3/worktrees/terebi/t3-e9bc44d9/tests/hermes_smoke.py /home/node/.t3/worktrees/terebi/t3-e9bc44d9
python /home/node/.t3/worktrees/terebi/t3-e9bc44d9/tests/hermes_smoke.py /tmp/hermes-screen-hermes-venv/lib/python3.14/site-packages/hermes_screen_plugin
```

Both output:
`PASS: official namespaced loader, YAML, real client + respx, scoped secret rotation`.
This calls actual `PluginLoaderMixin._load_directory_module` and actual
`agent.secret_scope.set_secret_scope/get_secret/reset_secret_scope`; registration
collection uses a small test context and all HTTP is respx. Doctor/validate above
provide the separate actual runtime-registration checks.

## Remaining limits

- Hermes **source** floor v0.22.0 is verified; installed ZimaOS version unknown.
- Jellyfin 12.4.0 API source checked; laptop URL/version and live compatibility unknown.
- No hardware contact. Roku 3 4200X `192.168.0.104` is reserved for manager testing
  from the Hermes container on ZimaOS `192.168.0.126`.
- Roku ECP shipping restriction unresolved; no workaround implemented.
- Catalog submission and live-device acceptance remain open. Passing local
  catalog tooling does not claim catalog publication or end-to-end playback.
- Priorities remain Telegram pick/play/pause, then `/watch`, then YouTube and
  Friday vote after repeatable core. No TMDB, watcher or Chromecast implementation.
