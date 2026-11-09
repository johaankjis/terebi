# PLAN

Living document. Agents and humans check items off here and add notes. Keep it honest.

**Deadline:** Wed Nov 11, 2026, 5PM EST. **Target finish:** noon Nov 11.

## Blockers

- Actual runtime is ZimaOS `192.168.0.126`, Docker container `hermes` on
  `hermes_default`; installed Hermes is **v0.16.0** (user-confirmed 2026-11-09),
  below the plugin floor v0.22.0. A separate v0.22.0 runtime passed smoke checks;
  the installed container was not upgraded. Remote execution access from this
  T3 container (`172.23.0.2`, no Docker socket or SSH key) remains unavailable.
  Earlier probes inside `hermes` were executed by the user in the ZimaOS terminal.
- Authorized Roku is Roku 3 / 4200X at `192.168.0.104`, advertising OS 15.3.4.
  Direct reachability from `hermes` to Roku port 8060 is proven. Jellyfin runs on
  ZimaOS at `http://192.168.0.126:8097` (`ServerName: "terebi"`, `Version: "12.2.0"`).
  Authenticated `library_status` and `library_pick(max_minutes=20)` are verified
  against the live server (`homelab-hp`, `BigBuckBunny_320x180` /
  `e5d6c471a8a4ea26e00a3694f91bf8d1`). Roku 3 signed in via Quick Connect, played
  `BigBuckBunny_320x180`, and live `/Sessions` + `JellyfinClient.verify_playback`
  confirmed exact item identity (`verified: true`, `playing: true`, `paused: false`,
  `DeviceName: "Roku 3 (4200X)"`, `Client: "Jellyfin Roku"` `3.2.4`).
- Reconcile the current ECP third-party restriction with the proposed shipping
  path. Live `/Sessions` confirms `SupportsMediaControl: false` and
  `SupportsRemoteControl: false` on `Jellyfin Roku` `3.2.4`, so programmatic launch
  and pause require Roku ECP on port `8060`. Jellyfin source deep-link support
  establishes receiver behavior, not an exception to Roku's restriction.
- No programmatic Hermes launch, pause, resume or TV wake evidence yet (manual
  playback and live `/Sessions` item verification succeeded on 2026-11-09). Roku 3
  is an external player, not a Roku TV; do not promise TV power control. See
  HARDWARE.md for carried-forward observations.

## Milestone 0: Setup + proof (Sun Nov 8, morning)

- [x] Repo scaffold with agent docs
- [x] Pivot docs to Jellyfin on Roku
- [x] Existing repo synced: main and origin/main at `4fd89d1b0cad82284f960be146bab444cfc9ff13` (further pushes remain user-owned)
- [x] Identify authorized Roku and actual Hermes runtime; preserve probe evidence
- [ ] Confirm applicable network-control setting and resolve ECP shipping restriction (kept separate from Roku connection diagnosis)
- [x] Confirm actual Jellyfin host/URL/version/user (`http://192.168.0.126:8097`, Jellyfin `12.2.0` `"terebi"`, single enabled user `homelab-hp` / `682764864adc45bbb6b981837f790812` verified live via `library_status` and `library_pick`)
- [x] Add legal demo library (`BigBuckBunny_320x180`, `e5d6c471a8a4ea26e00a3694f91bf8d1`, 10 min Movie verified live)
- [x] Install Jellyfin app on Roku; sign in to the server (Roku 3 signed in via Quick Connect and played `BigBuckBunny_320x180`; verified via live `/Sessions` on 2026-11-09)
- [ ] `curl http://ROKU_IP:8060/query/apps` → record Jellyfin channel ID in RESEARCH.md
- [ ] **Sequential proof:** one known Jellyfin item on authorized Roku, from actual
  Hermes container. Test launch, then input while open, episode, resume, and pause.
  Use bounded requests (3s Roku / 8s Jellyfin) and a bounded verification loop.
  Record app, player state, exact item evidence and human screen confirmation
  separately. Cross-check the matching Roku Jellyfin session if Roku omits identity.
- [ ] Test standby/CEC wake separately; report unsupported/unknown if it cannot be
  established. Neither HTTP success nor generic playing state proves title identity.
- [ ] Install Hermes; `hermes plugins list` works; note version for `requires_hermes`

## Milestone 1: Skeleton that validates (Sun Nov 8)

- [x] `plugin.yaml` + `__init__.py` with one tool (`library_status`); loads in Hermes (verified against upstream Hermes `v0.22.0` at `e06df9c2eae6901f4c88f464e0ae6e753c0428b8`; ZimaOS host is v0.16.0; separate v0.22.0 smoke passes)
- [x] `hermes plugins doctor . --ci` green (verified on integration SHA `4362ed1ecdb2a3606695925e24a79b3949063414`)
- [x] `hermes plugins validate . --install-deps` green (verified on integration SHA `4362ed1ecdb2a3606695925e24a79b3949063414`)
- [x] Settings via `config_schema`, secret API key read the sanctioned way (`agent.secret_scope.get_secret`)
- [x] Test harness with respx

## Milestone 2: Core (Sun Nov 8 to Mon Nov 9)

- [x] Jellyfin client: server info, user lookup, items search/filter, resume, Next Up, session identity — implementation, mocked tests, live `library_status` + `library_pick(max_minutes=20)`, and live Roku 3 `/Sessions` + `verify_playback` verified against Jellyfin `12.2.0` at `22d28304f787c339b20e137975193d91e88d8e89`
- [ ] Roku client: SSDP, apps, active app, media player, keypress, launch, input
- [ ] Tools: `tv_discover`, `tv_status`, `tv_control`, `tv_play`, `library_find`, `library_continue`
- [ ] `tv_play` verification loop: exact title, unknown-title playback, app-opened, failure; no duplicate toggle on retry
- [ ] End to end from Hermes CLI: "play Sintel" starts it on the TV

## Milestone 3: Smart + surfaces (Mon Nov 9)

- [x] Internal deterministic picker with grounded reasons and exact client runtime filtering
- [x] Register `library_pick` (tool, schema, manifest parity; mocked Jellyfin tests, official loader smoke, and live Jellyfin 12.2.0 verification at `22d28304f787c339b20e137975193d91e88d8e89`)
- [ ] Verify `library_pick` through Telegram (live Jellyfin 12.2.0 tool call passed in isolated Hermes v0.22.0 runtime; no Telegram gateway configured in isolated runtime)
- [ ] `/watch` slash command with `ctx.ask_choice`; handle None/cancellation
- [ ] Text fallback choices expire and are scoped to trusted conversation/requester
  and profile; never trust a session ID supplied in model arguments
- [ ] Works from Telegram (or Discord) through the Hermes gateway
- [ ] `tv_youtube` (P1)
- [ ] Movie night blueprint (P1), after core: define vote collection/expiry; cron cannot wait on ask_choice

## Milestone 4: Polish + reliability (Tue Nov 10)

- [ ] Error model everywhere; timeouts; friendly hints
- [ ] Demo flow 5 times in a row on real hardware
- [ ] README: GIF, install, config, Roku setting, troubleshooting, disclosures
- [ ] Tag a release commit; record full SHA
- [ ] Stretch: Desktop poster directive (P2.1)

## Milestone 5: Ship (Wed Nov 11)

- [ ] Record demo per DEMO.md
- [ ] Post on X tagging @NousResearch
- [ ] Open catalog PR (one YAML file, full SHA pin)
- [ ] Submit typeform with both links
- [ ] Walk SUBMISSION.md checklist

## Worker assignments and integration contract

All **new workers start at `4fd89d1b0cad82284f960be146bab444cfc9ff13`** in separate,
verified worktrees. The user subsequently authorized two independent workers in parallel with the
manager-owned hardware test. T3 worktree delegation preserves the single manager
thread. Parallelism never includes device commands; hardware acceptance remains open.

| Owner | Exclusive files | Assignment / dependency |
|---|---|---|
| Manager | `docs/**`, README, AGENTS, `hermes_screen/roku.py`, `tests/test_roku.py`, `tests/test_playback.py` | Resolve hardware/shipping gate; Roku client and post-launch evidence; review and integrate exact worker commits |
| Worker A: native host | `plugin.yaml`, root `__init__.py`, `schemas.py`, `tools.py`, `pyproject.toml`, `.gitignore`, `.env.example`, `LICENSE`, `hermes_screen/__init__.py`, `hermes_screen/config.py`, `hermes_screen/errors.py`, `tests/test_plugin.py`, `tests/test_config.py` | M1 skeleton with library_status, secret/config adapters, packaging, doctor/validate; later wire M2/M3 tools and /watch after core integration |
| Worker B: Jellyfin | `hermes_screen/jellyfin.py`, `tests/test_jellyfin.py` | M2 version-verified API, user lookup, items, resume, Next Up, session identity; 8s HTTP timeouts and respx failures |
| Worker C: picker | `hermes_screen/picker.py`, `tests/test_picker.py` | M3 pure deterministic ranking of normalized Jellyfin records; strict runtime, actual watch-state reasons, at most three picks; starts after data contract is fixed |

Manager publishes shared error/result and item contracts before workers edit;
workers do not create shared conftest or change another owner's files. B/C may use
local fixtures in their owned tests. Workers report evidence and proposed doc text
for manager integration rather than editing docs concurrently. No TMDB client,
independent watch-history store, polling watcher, or Chromecast worker.

For every new worker, record tool-created checkout path, branch and full HEAD;
verify clean status and exact base before work. Return full result SHA, changed
files, checks and limitations. Review `base..result` and file ownership before
integration; keep the original stash and backup refs intact. Once integrated,
record the exact integration SHA and run pytest, Ruff, Hermes doctor and validate
against that tree, plus actual Hermes invocation and hardware acceptance. Source
review and mock tests never substitute for the real-device gate. Pushes, merges,
PR creation, tagging/public release and public posting remain user-owned.

## Prior-work review (2026-11-08)

- Checkout verified clean at the base above. Git and T3 each report only the main
  worktree; project thread inventory contains no child workers. No older worker
  implementation commits were found in available branches, refs or reflogs.
- Reviewed T3 checkpoints `5a84292`, `66a4fae`, `20b69c3`, `c67bb49`, `f91bd78`,
  `b07b1a8`, `010177f`, `b1e3eca`, `da13ee7`: documentation only, no Python package.
  `da13ee7` has the same tracked edits as stash `af18510`.
- Reviewed `stash@{0}` / `af18510` ("T3 edits before GitHub sync"), including its
  untracked HARDWARE.md. Carry forward specific network/device evidence, the
  exact-title verification distinction, trusted expiring choices, and pinned
  Hermes API references. Rewritten into current docs; stash not applied or popped.
- Do not carry the old TMDB/subscription roadmap, local taste watcher, Chromecast
  fallback, stale "no probes" statements, or old D-005/D-006 decision numbering.
  These conflict with the new Jellyfin scope or later evidence.
- Backup commit `460147a` changes only README branding to Terebi. Do not carry it:
  current instructions explicitly name the product Hermes Screen.

## Proposed (not scheduled)

- Chromecast / Google TV via Jellyfin's own cast sessions
- Multi room support
- Kodi as a second output

## Notes

- 2026-11-08: Pivoted from streaming services (Netflix etc.) to Jellyfin. Reason: Jellyfin Roku app supports deep links with Jellyfin item IDs (verified in source), and Jellyfin gives us watch history. See D-005.

## Integration checkpoint (2026-11-08; superseded where noted below)

Base: `4fd89d1b0cad82284f960be146bab444cfc9ff13`; main retains manager documentation
edits, stash and backup refs. No pushes, merges to main, PRs or publication.

- Jellyfin worker: Claude, task suffix `51d02afa-ce94-4dbb-a8fc-ebc15e537bc3`,
  branch `t3/implement-jellyfin-client`, separate checkout
  `/home/node/.t3/worktrees/terebi/t3-4241fccf`, base verified in Git worktree list.
  Owns only `hermes_screen/jellyfin.py` and `tests/test_jellyfin.py`. Result `c4c6c83e171a646b830b418cda79b6e420ecdf77`; only the two owned
  paths changed, clean checkout. Worker reports 182 pytest tests and Ruff pass.
- Skeleton worker: OpenCode, task suffix `9e267373-8d04-488f-8df9-19065dcc1967`,
  branch `t3/native-plugin-skeleton`, clean separate checkout
  `/home/node/.t3/worktrees/terebi/t3-9ea13dee`; result
  `4ebcb722500fffea9f1af65f909298a1b294d888`. Owned-file scope verified.
  Worker reports 12 tests and Ruff pass.
- Integrator: Codex, task suffix `527a8343-4829-4996-acc9-78b8880aaff2`,
  branch `t3/integrate-jellyfin-client`, clean separate checkout
  `/home/node/.t3/worktrees/terebi/t3-e9bc44d9`. Cherry-picked `4ebcb72` (`310d83e`)
  then `c4c6c83` (`eb08f2d`) from `4fd89d1`, and committed integration fixes at
  exact SHA `4362ed1ecdb2a3606695925e24a79b3949063414`.
  - Fixed YAML quoting in `plugin.yaml`, non-text config rejection, structured
    config/secret/import/runtime error handling without raw exception text, closure-bound
    context isolation, package-relative imports, exact case-sensitive username matching,
    session scan-cap safety, and separated `verified` item identity from `playing`/`paused`.
  - Automated checks on `4362ed1ecdb2a3606695925e24a79b3949063414`: `pytest -q` (220 passed),
    `ruff check .`, `ruff format --check .`, `git diff --check`, and official Hermes `v0.22.0`
    (`e06df9c2eae6901f4c88f464e0ae6e753c0428b8`) `hermes plugins doctor --ci`,
    `hermes plugins validate --install-deps`, and `tests/hermes_smoke.py` (source + wheel) all pass.
- Independent reviewer: Claude, task suffix `212af8f1-bcc5-4380-8ba7-2a5cbc345193`,
  reviewed exact SHA `4362ed1ecdb2a3606695925e24a79b3949063414` in `/home/node/.t3/worktrees/terebi/t3-e9bc44d9`.
  Re-ran all 220 pytest tests, Ruff check/format, `git diff --check`, `hermes plugins doctor --ci`,
  `hermes plugins validate --install-deps`, and `tests/hermes_smoke.py`. Reported **zero blocking findings**
  and 5 minor non-blocking observations (per-phase 8s httpx timeout vs total wall-clock, GUID lookup
  not filtering `isDisabled`, 32-hex username treated as GUID, `.env.example` presence, and `hermes_smoke.py`
  being a standalone CLI script).
- Hardware: Jellyfin is on ZimaOS at `http://192.168.0.126:8097` (`ServerName: "terebi"`,
  `Version: "12.2.0"` verified from T3 container; check from inside the `hermes` container
  and installed `hermes` version check against `>=0.22.0` await user command output from
  ZimaOS). The Roku Jellyfin app still reports `"Server not found"`; user is finishing a
  Roku packet capture separately, and **manual playback is the next Roku milestone**.
  Keep the third-party ECP restriction question separate from the Roku connection diagnosis.
  Exact title must match requested item ID in the target Roku's Jellyfin session; absent
  session evidence is unverified.
- Demo order: Telegram picks/play/pause first; /watch next; YouTube and Friday vote
  only after the core repeats reliably. No third picker worker launched.

## Published-tree checkpoint — 2026-11-09 (historical)

- User confirmed HTTP 200 from `hermes` to
  `http://192.168.0.126:8097/System/Info/Public`. Public reachability is proven;
  authenticated library/session compatibility is still open.
- Installed Hermes is v0.16.0; leave it unchanged. Separate v0.22.0 runtime at
  upstream SHA `e06df9c2eae6901f4c88f464e0ae6e753c0428b8` smoke-tested published
  plugin SHA `9320c3638d9f7d8579326e1a622a205523b395d1` (same product code as
  reviewed integration `4362ed1ecdb2a3606695925e24a79b3949063414`).
- Doctor, validate --install-deps and official-loader mocked tool invocation pass;
  220 pytest tests and Ruff check/format pass. Validate emits non-blocking
  `context_exfil` caution for `docs/HARDWARE.md:4`; do not describe this as a
  warning-free security scan. Full commands/log locations in INTEGRATION.md.
- Roku sign-in and manual playback remain pending per user. No launch, in-app
  playback, pause, wake or exact target-session item match has been verified.
- This turn changes documentation only; no upgrade/deployment or push performed.

## Picker/catalog worker checkpoint — 2026-11-09 (before integration)

Both assignments start at `9320c3638d9f7d8579326e1a622a205523b395d1`.
Manager root remains on main with prior uncommitted documentation preserved.
Roku sign-in and manual playback remain manager-owned and pending.

- Worker A task suffix `bf98620e-fe9c-4d28-a579-79d476cee253`: picker module and
  focused mocked tests only; completion pending. No polling of the running delegate.
- Worker B task suffix `18bc2ec3-df3a-471f-8194-71785a89b838`: completed at
  `b8fa6108d95033cb6177a3d50416ef565e812e58`, branch
  `t3/catalog-submission-readiness`, clean worktree
  `/home/node/.t3/worktrees/terebi/t3-7b4f8168`. Only README.md and
  docs/SUBMISSION.md changed; ownership and diff reviewed.
- Scanner cause confirmed in official v0.22.0 tools/skills_guard.py: a transfer-verb
  pattern accidentally matches the provenance sentence in HARDWARE.md. Manager
  changed the provenance noun to “thread”, preserving its meaning and all evidence.
  No scanner suppression or policy bypass. This local fix must be included during
  integration; final README/SUBMISSION scan text must describe the integrated tree,
  not the worker's intermediate caution state.
- Integration review must correct README's blanket statement that all config values
  use ctx.get_config: the secret uses agent.secret_scope.get_secret. Trim internal
  worker ownership/proposed-patch prose from the final user-facing README, and update
  picker availability only as proven. Preserve the existing local version facts.
- Final combined commit and checks pending Worker A completion.

Manager verification after the provenance clarification: isolated Hermes v0.22.0
`plugins validate /home/node/projects/terebi --install-deps` exits 0 with
`security scan — safe`. The fix is uncommitted alongside preserved manager docs;
repeat validation on the final integration SHA after adopting worker documentation.

## Combined integration checkpoint — 2026-11-09

- Separate tool-created checkout `/home/node/.t3/worktrees/terebi/t3-1ac1002f`,
  branch `t3/integrate-picker-workers-docs`, clean start at
  `9320c3638d9f7d8579326e1a622a205523b395d1`.
- Worker A completed at `934802476d9b8682463c412a7a60c050b9ecf6cf`, adopted as
  `6edf9ae7ab1be654a02ff4eeda2bab08c0964017`; worker B
  `b8fa6108d95033cb6177a3d50416ef565e812e58`, adopted second as
  `fda219045547dd5a76372102cb735c143defeeb1`.
- Adopted checksum-verified manager snapshots for HARDWARE, INTEGRATION, PLAN and
  RESEARCH; reconciled snapshot README facts with worker B. Manager root, worker
  checkouts and snapshot files were not changed.
- Internal picker integrated; only `library_status` registered. Clarified remaining
  time and display rounding in reasons; oversized integer limits return errors.
  Added real-client Next Up boundary/missing-history tests. No genre affinity.
- Focused picker + Jellyfin tests: 297 passed. Full checks and scan evidence in
  INTEGRATION.md. Independent exact-SHA review follows; it is not complete yet.
- Hardware and credentials untouched. ZimaOS v0.16.0 unchanged; authenticated
  Jellyfin 12.2.0, Roku sign-in/manual playback, exact session match and ECP shipping
  question remain open. Telegram pick/play/pause precedes /watch, then YouTube/vote.

## library_pick registration checkpoint — 2026-11-09

- Worker checkout `/home/node/.t3/worktrees/terebi/t3-register-library-pick`, branch
  `t3/register-library-pick`, clean start at
  `895f28b8c1b813bb204d6429f14f4e151eaa3141`. Final SHA is given in the handoff.
- `library_pick` is registered next to `library_status` (2 tools, 0 hooks):
  `plugin.yaml`, `PROVIDES_TOOLS`, `register(ctx)`, `schemas.LIBRARY_PICK`,
  `tools.library_pick`. Hermes-facing arguments are only `max_minutes` (required) and
  `limit` (1 to 3); anything else is `invalid_argument`. See D-012.
- Tests: 385 passed, Ruff check/format and diff check clean; official Hermes v0.22.0
  doctor (2 tools), validate (`declared tools — matches registrations`,
  `security scan — safe`) and `tests/hermes_smoke.py` pass. Details in INTEGRATION.md.
- Still open: live Hermes session, authenticated Jellyfin 12.2.0, Telegram surface,
  `/watch`, every `tv_*` tool and all Roku/hardware work. No hardware was contacted.

## Live Jellyfin and Roku 3 session verification checkpoint — 2026-11-09

- Tested SHA `22d28304f787c339b20e137975193d91e88d8e89` in the isolated Hermes
  `v0.22.0` runtime against live Jellyfin `12.2.0` (`http://192.168.0.126:8097`).
  `JELLYFIN_API_KEY` was supplied via a one-time secret file read into memory only
  and immediately deleted.
- Live `library_status({})` and `library_pick({"max_minutes": 20})` passed for user
  `homelab-hp` (`682764864adc45bbb6b981837f790812`), returning
  `BigBuckBunny_320x180` (`e5d6c471a8a4ea26e00a3694f91bf8d1`, 10 min Movie,
  `source: "unwatched"`, `complete: true`, `truncated: false`, `errors: []`).
- User signed in on Roku 3 (`192.168.0.104`) via Quick Connect and played
  `BigBuckBunny_320x180`. Live `/Sessions` and `JellyfinClient.verify_playback`
  confirmed exact item identity (`NowPlayingItem.Id == "e5d6c471a8a4ea26e00a3694f91bf8d1"`,
  `verified: true`, `playing: true`, `paused: false`, `position_s: 84`,
  `DeviceName: "Roku 3 (4200X)"`, `Client: "Jellyfin Roku"`, `ApplicationVersion: "3.2.4"`).
- Live `/Sessions` also confirmed `SupportsMediaControl: false` and
  `SupportsRemoteControl: false` on `Jellyfin Roku` `3.2.4`, so programmatic launch
  and pause require Roku ECP on port `8060` (gated on the third-party ECP shipping
  restriction).
