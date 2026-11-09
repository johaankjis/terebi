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

## Remaining limits at the first integration (historical)

- Hermes **source** floor v0.22.0 is verified; installed ZimaOS version unknown.
- Jellyfin 12.4.0 API source checked; laptop URL/version and live compatibility unknown.
- No hardware contact. Roku 3 4200X `192.168.0.104` is reserved for manager testing
  from the Hermes container on ZimaOS `192.168.0.126`.
- Roku ECP shipping restriction unresolved; no workaround implemented.
- Catalog submission and live-device acceptance remain open. Passing local
  catalog tooling does not claim catalog publication or end-to-end playback.
- Priorities remain Telegram pick/play/pause, then `/watch`, then YouTube and
  Friday vote after repeatable core. No TMDB, watcher or Chromecast implementation.

## Repeat smoke on published build — 2026-11-09

Plugin tested: `9320c3638d9f7d8579326e1a622a205523b395d1`, clean `main` at test
start in `/home/node/projects/terebi`. Compared against independently reviewed
integration `4362ed1ecdb2a3606695925e24a79b3949063414`: only four documentation
files differ, no product/test changes.

Reused separate official upstream checkout (clean) and Python 3.14.10 venv from
above, verified exact upstream HEAD `e06df9c2eae6901f4c88f464e0ae6e753c0428b8`.
Fresh `HERMES_HOME=/tmp/terebi-v022-smoke-20261109-ryh46ak4`; no existing profile,
ZimaOS v0.16.0 container or credentials modified. Working directory `/tmp`;
PATH prepended `/tmp/hermes-screen-hermes-venv/bin` and
`/tmp/hermes-screen-integrator-bin`.

```sh
hermes --version
hermes plugins doctor /home/node/projects/terebi --ci
hermes plugins validate /home/node/projects/terebi --install-deps
/tmp/hermes-screen-hermes-venv/bin/python /home/node/projects/terebi/tests/hermes_smoke.py /home/node/projects/terebi
```

All four commands exit 0. Version v0.22.0; doctor reports one tool, zero hooks.
Validate passes with one non-blocking warning:
`security scan caution: context_exfil (HARDWARE.md:4)`.
Unlike the prior integration-tree scan, this published tree includes the hardware
notes. The warning is recorded without changing the scanner or suppressing it.
Logs: `check-0.log` through `check-3.log` in the isolated home above.
Smoke output: `PASS: official namespaced loader, YAML, real client + respx, scoped secret rotation`.
This uses actual upstream loading/secrets, a small registration context, and mocked
HTTP. It is not live authenticated Jellyfin, Telegram or hardware acceptance.

Also reran from the project root with integration worktree `.venv/bin` tools:
`pytest -q` — 220 passed; `ruff check .` — pass;
`ruff format --check .` — 25 files already formatted.
Documentation updates after this test do not change product code.

User separately confirmed HTTP 200 for Jellyfin `/System/Info/Public` from the
ZimaOS Hermes container. Installed Hermes v0.16.0 remains below the required floor.
Roku sign-in/manual playback and exact target session evidence remain pending.

## Picker and documentation integration — 2026-11-09

Checkout: `/home/node/.t3/worktrees/terebi/t3-1ac1002f`, branch
`t3/integrate-picker-workers-docs`. T3 confirmed this attached worktree is separate
from `/home/node/projects/terebi`; Git status was clean at starting base
`9320c3638d9f7d8579326e1a622a205523b395d1` before edits.

Ordered cherry-picks (scope inspected before adoption):

- A: `934802476d9b8682463c412a7a60c050b9ecf6cf` →
  `6edf9ae7ab1be654a02ff4eeda2bab08c0964017` (picker + picker tests only).
- B: `b8fa6108d95033cb6177a3d50416ef565e812e58` →
  `fda219045547dd5a76372102cb735c143defeeb1` (README + SUBMISSION only).

Adopted four manager snapshot docs from
`/tmp/terebi-manager-docs-picker-fkkgfonh`, verified against `checksums.json`, and
reconciled the fifth (README) with worker B. Preserved historical evidence and
D-009; added D-011 for the picker refinement. HARDWARE retains the one-word
provenance clarification. All five manager files and all snapshots still match
the original checksums. No manager/worker checkout edits, stash/reset, upstream
changes, push, PR, main merge, hardware calls or credential access.

Product inspection: real client filters remaining ticks for resume and Next Up,
full ticks for unwatched. Runtime float is not truncated; unknown duration cannot
fit. Missing Played never becomes an unwatched claim. Tier ordering, deterministic
ties, deduplication, max-three results, errors and truncation are covered. No
history query means no genre affinity. Fixed an oversized integer argument raising
OverflowError, clarified Next Up time left, and labeled display rounding when it
exceeds the exact window. Added real-client tests for fractional Next Up boundaries,
one-tick overruns, missing runtime and missing history. Only library_status remains
registered; this does not expose library_pick or Telegram flows.

Verification commands, executed from the integration checkout:

```sh
/home/node/.t3/worktrees/terebi/t3-e9bc44d9/.venv/bin/pytest -q tests/test_picker.py tests/test_jellyfin.py
/home/node/.t3/worktrees/terebi/t3-e9bc44d9/.venv/bin/pytest -q
/home/node/.t3/worktrees/terebi/t3-e9bc44d9/.venv/bin/ruff check .
/home/node/.t3/worktrees/terebi/t3-e9bc44d9/.venv/bin/ruff format --check .
git diff --check
```

Results: **297 focused tests; 328 full tests passed**. Ruff check and format pass
(27 files); diff check passes. Executables in the earlier worker venv were used
read-only, with imports from this integration checkout. An initial Ruff line-length
finding in a changed test assertion was fixed before the passing rerun.

Official upstream HEAD reverified as `e06df9c2eae6901f4c88f464e0ae6e753c0428b8`.
Fresh isolated home `/tmp/terebi-picker-integration-home-poaiiq__`. From `/tmp`:

```sh
export HERMES_HOME=/tmp/terebi-picker-integration-home-poaiiq__
export PATH=/tmp/hermes-screen-hermes-venv/bin:/tmp/hermes-screen-integrator-bin:$PATH
hermes --version
hermes plugins doctor /home/node/.t3/worktrees/terebi/t3-1ac1002f --ci
hermes plugins validate /home/node/.t3/worktrees/terebi/t3-1ac1002f --install-deps
/tmp/hermes-screen-hermes-venv/bin/python /home/node/.t3/worktrees/terebi/t3-1ac1002f/tests/hermes_smoke.py /home/node/.t3/worktrees/terebi/t3-1ac1002f
```

All exit 0. Version v0.22.0, Python 3.14.10; version command includes an update
available notice (no update performed). Doctor: one tool, zero hooks. Validate:
all checks pass, **security scan — safe**, no caution warning; host isolation
notice remains. This verdict does not imply zero medium/low scanner findings.
Smoke: `PASS: official namespaced loader, YAML, real client + respx, scoped secret rotation`.
Logs `check-0.log` through `check-3.log` in the home above. Final committed-tree
reruns use `final-doctor.log`, `final-validate.log`, `final-smoke.log` in the same
home; the handoff supplies the full final SHA. No independent review is claimed.

Limits unchanged: ZimaOS Hermes v0.16.0 was not upgraded. Jellyfin 12.2.0 public
HTTP 200 is user-confirmed from Hermes, but authenticated endpoints remain
unverified. Roku 3 sign-in/manual playback, launch/in-app playback/pause/wake and
exact target-session match remain pending; ECP restriction is a separate unresolved
question. Hardware belongs to the manager. Priority: Telegram pick/play/pause,
then /watch, then YouTube and Friday vote. No publication pin or catalog PR.
