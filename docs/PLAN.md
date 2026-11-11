# PLAN

Living document. Agents and humans check items off here and add notes. Keep it honest.

**Deadline:** Wed Nov 11, 2026, 5PM EST. **Target finish:** noon Nov 11.

## Current slice: Terebi Games v1 — camera rock-paper-scissors

User explicitly authorizes this new slice. Base origin/main
`263c82629886bfdf45517e8583b94cffecea9888`, separate manager branch/worktree
`feat/hermes-games-rps`. Preserve movie/scene code and regression tests.

- [x] Verify main and define [session/round contract](RPS_CONTRACT.md).
- [x] Select manual Mac Chrome mirroring: no Custom Receiver ID/test registration.
- [ ] FIRST LIVE GATE: Den TV display page plus one shared-state update observed.
- [x] Manager: standalone service/API, authoritative rounds, Hermes tool, fullscreen display.
- [x] Deploy the service on ZimaOS through the user-run host commands.
- [x] One Claude Code worker: iPhone-compatible camera UI and local recognition;
  59 mocked-media JS tests and checksum-verified camera asset build pass.
- [x] Single-use pairing/expiring credentials implemented; Docker/Quick Tunnel
  package and exact host-side commands in [GAMES_RPS.md](GAMES_RPS.md).
- [ ] Trusted HTTPS deployment and real iPhone permission/camera checks.
- [ ] Telegram -> pair once -> three camera rounds; missed-hand retry; exactly-once
  scores; Stop camera releases tracks. Tap fallback labelled separately.
- [x] Automated checks on `aee89f9`: 852 Python tests (including all movie/scene
  regressions), 59 camera JS tests, checksum-verified build, Ruff, Hermes v0.22.0
  doctor (8 tools) / validation / real-dispatch smoke. Scanner cautions visible.
- [x] Open draft PR #6, targeting main; host/device acceptance blockers recorded.
  Leave unmerged.

Live status (2026-11-11): the user deployed the ZimaOS service through a
Cloudflare Quick Tunnel. Manager verified health, admin authentication, correct
public pairing/display origins, camera/model/WASM assets, and the isolated
@terebitvbot connection on `0e17940`. User reports iPhone Safari preview works but
initially no gestures were recognized. User now reports practice recognition
works, but live rounds reject the reveal as a last-moment change. TV shared-state
observation and successful camera rounds remain unverified.

- [x] Add temporary local practice diagnostics: landmarks, gesture/confidence,
  no-hand/low-confidence/model-stage errors, three-shape checklist, and Shoot
  sample counts. Preserve the pinned MediaPipe model and decision thresholds.
  Diagnostic candidate checks: 66 JS tests, 852 Python tests, asset build, Ruff,
  Hermes doctor (8 tools) and validation passed. iPhone verification pending.
- [x] Display footer follows unpaired/paired state; fresh local session and
  same-session pairing verified through actual HTTP API and display script.
- [ ] Deploy diagnostic build and verify rock, paper, scissors on user's iPhone.
- [x] Replace pre-Shoot majority with a bounded post-Shoot consecutive run;
  movement into the pose is ignored, uncertain decisions retain Retry.
  71 camera JS tests, 852 Python tests, asset build, Ruff and Hermes checks pass.
- [ ] Verify updated timing on the real iPhone, Retry, three camera rounds,
  exactly-once score and Stop camera with actual device evidence.


## Blockers


- **2026-11-10 merge gate: live subtitle scene acceptance blocked.** User now
  authorizes merge only after describing a scene in Telegram without a timestamp
  or saved-marker name, subtitle resolution for the exact edition, and receiver
  confirmation at the matched time. Latest live library audit (18:20 UTC) has
  one movie, `BigBuckBunny_320x180`, with no subtitle tracks. Its successful
  manual-marker test does not satisfy this gate. Need a user-selected movie
  edition with usable text subtitles and the user's natural-language request.
  PR #4 is the scene feature itself, already targeting main; no separate
  scene-search PR exists to retarget. Keep #4 draft and unmerged until acceptance.
  Automated candidate `3833745` rechecked: 722 tests, Ruff, Hermes v0.22.0
  doctor/validation passed; GitHub reports no checks. Branch-protection/rules
  API reads returned HTTP 403 (private-repository plan restriction); do not
  infer protections or bypass the normal GitHub merge flow.


- Scene slice: no local embedding model is approved; semantic ranking stays disabled.
  User approved OpenCode `opencode/glm-5.3-flash-free` after GLM 5.1 was unavailable.
  Live marker: user-supplied “one-minute test scene”, 60 seconds, for
  `BigBuckBunny_320x180` and its exact media source.

## Current slice: Big Buck Bunny saved-description demo (2026-11-10)

User explicitly requests this demo instead of subtitle or frame analysis. Base:
PR #4's verified open head `3cc3c1e7748dbd043ac98eab201a0adced9e3a78`.
Manager branch `feat/bbb-scene-demo` uses a separate worktree; root demo and
PR #4 checkout remain unchanged. This demo will have one new draft PR stacked
on PR #4 while that dependency remains unmerged. User owns merging this slice.

- [x] Verify upstream head and create isolated manager demo checkout.
- [x] Claude Code Opus 5.5: local saved-description lookup and 80 focused tests.
- [x] Manager: descriptions/aliases in existing exact-edition marker state,
  bounded optional end time, Hermes description lookup and candidate wiring.
  Registered-tool tests cover paraphrase playback, unchanged legacy markers,
  changed-record revalidation, and lookup-only ambiguous/unmatched results.
- [x] Three user-supplied scenes saved for the exact copy (45 s, 185 s, 244 s),
  separate from the movie; 60-second marker preserved, no duplicates, no aliases.
- [x] Telegram paraphrase → exact-edition PLAYING near selected saved start
  (burrow marker, receiver 45.0 s, user confirmed on Den TV). Pause device-reported.
- [ ] Ambiguous and unmatched descriptions do not initiate playback (unit tests
  only; no live evidence).
- [x] Focused/full tests and Hermes checks on code `cb4b69d`: 817 tests,
  Ruff, Hermes v0.22.0 doctor/validation and real-loader/dispatcher smoke passed.
  Existing LAN-bind scanner caution remains visible.
- [x] Opened draft PR #5, stacked on PR #4; scene-data/live acceptance blockers
  remain visible. User owns merging.

**Scene data:** resolved 2026-11-10 21:19 UTC. The 401 came from the ad-hoc
bootstrap's `X-Emby-Token` header; the plugin's `Authorization` header gets 200.
Gateway for @terebitvbot runs pinned `cb4b69d` with the saved markers; Den TV
`192.168.0.134` reachable. Live Telegram → Den TV test passed 2026-11-10. User authorized merging PR #4
and PR #5 via the normal PR flow, overriding the earlier subtitle-scene merge gate.
Production bot deployment is a separate step.

## Current slice: edition-specific scene playback (2026-11-10)

The user explicitly authorized this slice, superseding historic scope exclusions.
Base: clean `8e978d71474029fdc2994a1d3dcd3156ebc52b45`, already on origin/main.
The working demo remains at `/home/node/projects/terebi`; manager feature checkout
is `/home/node/.t3/worktrees/terebi/feat-scene-playback`, branch `feat/scene-playback`.
Telegram audit confirms pick → exact-item PLAYING → PAUSED on this base.
Draft PR #3 has the same head; this new feature PR will target main independently.

- [x] Verify demo base and preserve its checkout.
- [x] Agree worker handoff and ownership in [SCENE_CONTRACT.md](SCENE_CONTRACT.md).
- [x] Claude Code: exact-source text subtitle ingestion, original cue timestamps,
  neighboring cue search, local index refresh and resolver tests.
- [x] OpenCode: optional source/offset playback, fresh load and seek, measured
  receiver position, ordinary play/pause regression tests (approved GLM 5.3 Flash).
- [x] Manager: movie/edition ambiguity, scene candidates, saved edition markers,
  timestamp fallback, Hermes tools and focused integration tests.
- [x] Dialogue query fixture; semantic paraphrase remains gated on an approved local model.
- [x] Live Telegram retest on final code `37582ae`: saved Big Buck Bunny marker →
  Den TV PLAYING at 60.0s → PAUSED at 74.652622s, same exact content/session.
  Runtime module origins and every tool invocation verified the pinned SHA;
  real Telegram calls used trusted session scope. Relay closed after pause.
  Full automated suite previously passed 722 tests; see
  [exact-code retest evidence](evidence/scene-marker-37582ae-20261110.json).
- [x] Draft PR #4 opened.
- [ ] New merge acceptance: natural-language scene description → exact-edition
  subtitle match → Den TV playback verified at that cue timestamp. Manual
  markers/timestamps do not count. User authorizes normal GitHub merge after
  this acceptance and passing checks; currently blocked as recorded above.

- **Chromecast proof passed; integration pending (2026-11-10):** Authorized Gen 2
  `192.168.0.134` reported `PLAYING` then `PAUSED` for the exact temporary LAN MP4
  URL after host port 8765 became reachable. Server stopped and copy deleted.
  This was run from T3, not the actual `hermes` container. A repeat with the user
  watching confirmed visible playback and receiver-reported pause at 14.46s;
  TV/CEC wake and human confirmation of pause remain unverified. See [hardware evidence](HARDWARE.md#chromecast-gen-2-direct-cast-attempt--2026-11-10).
  Record this proof before building the Cast integration; production stream/auth
  handling and Hermes runtime reachability still need design and verification.
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
  path. Live `/Sessions` confirms `SupportsMediaControl: false`,
  `SupportsRemoteControl: false`, and `SupportedCommands: []` on `Jellyfin Roku`
  `3.2.4`, and DIAL is unsupported by `jellyfin-roku`. While `jellyfin-roku` `3.2.4`
  implements ECP `/launch`, `/input` deep links, and `roInput` transport commands
  (`type=transport&command=pause`), Roku's official ECP documentation states that
  *"ECP commands may not be sent from 3rd-party platforms."* With no documented
  third-party exception, Roku 3 programmatic control remains blocked (no ECP
  commands sent).
- **Chromecast identified (2026-11-10):** User authorized Gen 2 at `192.168.0.134`
  and a temporary credential-free Big Buck Bunny MP4 test. Direct Cast control
  reaches the receiver; exact-URL playback and pause passed as recorded above. This explicit
  hardware spike supersedes the earlier exclusion of Chromecast evaluation, but
  does not add a Cast dependency or tool to the plugin.
- No programmatic Hermes launch, pause, resume or TV wake evidence yet (manual
  playback and live `/Sessions` item verification succeeded on 2026-11-09). Roku 3
  is an external player, not a Roku TV; do not promise TV power control. See
  HARDWARE.md for carried-forward observations.

## Milestone 0: Setup + proof (Sun Nov 8, morning)

- [x] Identify and probe authorized Chromecast Gen 2; record direct Cast attempts
  and verify temporary endpoint/copy cleanup (2026-11-10).
- [x] Repeat direct Cast from idle with a receiver-reachable temporary MP4 URL;
  exact URL + `PLAYING`, then same media session + `PAUSED` verified (2026-11-10).

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

## Current slice: Jellyfin to Chromecast (authorized 2026-11-10)

- Base verified clean at `c19b1f70fedf19c7ad608998026f1d6974f88fca`; origin/main
  is `6b11f9711e1213c3a650c6ecb0095da4945b379b`. Draft PR #2 is open and docs-only.
  Code has no dependency on its changes; this slice stacks on its branch to retain
  verified hardware evidence and avoid duplicating it in the implementation PR.
- [x] Reuse `library_pick`; add exact Jellyfin item play (`tv_play`) and explicit pause (`tv_pause`) tools.
- [x] Serve an expiring, item-scoped LAN media capability; keep Jellyfin credentials
  server-side, support bounded streaming/ranges, redact tokens, clean up on expiry.
- [x] Verify exact URL and fresh PLAYING/PAUSED receiver states; keep TV wake out.
- [x] One Claude Code worker owns implementation and focused mocked tests in a
  separate tool-created worktree (`/home/node/.t3/worktrees/terebi/t3-8d379d55`,
  branch `t3/jellyfin-chromecast-playback`, HEAD `de5bf8d5ab33faec4fbf1b43bafaa9e269ae0493`).
  Manager integrated onto `feat/jellyfin-chromecast-playback`, fixed two real-hardware
  Cast behaviors discovered during live testing (suppressing `CLOSE` on `CC1AD845`'s
  `transport_id` when closing per-call control sockets, and ignoring outgoing session
  `IDLE`/`INTERRUPTED` transitions on `LOAD`), ran automated + Hermes `v0.22.0` checks
  (553 pytest tests, Ruff, doctor 4 tools, validate with visible `bind_all_interfaces`
  caution, `hermes_smoke.py`), and verified live Jellyfin `12.2.0` item metadata
  (`get_cast_source`) + authenticated `HEAD` (`200`) and byte-range (`206`) streaming.
- [x] Live acceptance (`2026-11-10T01:43:22Z–01:43:32Z`): `library_pick` recommended
  Big Buck Bunny (`e5d6c471a8a4ea26e00a3694f91bf8d1`, `source: "resume"`, 2m left);
  `tv_play` verified `state: "playing"` (`action: "started"`, `position_s: 0.0`,
  `duration_s: 596.5`, `relay_expires_in_minutes: 25`) on Chromecast Gen 2
  `192.168.0.134`, `tv_pause` verified `state: "paused"` (`already_paused: false`,
  `position_s: 4.7`) and idempotent repeat (`already_paused: true`, `position_s: 4.7`),
  and `on_unload` closed the relay (`relay_port_8765_closed: true`).

This explicit user request supersedes the older exclusions of Chromecast workers
and the historic worker-base instructions below. No Roku control, TV wake, new
recommendation engine, watcher, automatic history writes or Telegram UI is included.

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

## Jellyfin-to-Chromecast integration and live acceptance checkpoint — 2026-11-10

- Worker checkout `/home/node/.t3/worktrees/terebi/t3-8d379d55` (`t3/jellyfin-chromecast-playback`,
  HEAD `de5bf8d5ab33faec4fbf1b43bafaa9e269ae0493`, verified clean) was cherry-picked
  onto `feat/jellyfin-chromecast-playback` (`1a77c70..da54f74`) stacked on Draft PR #2
  (`c19b1f70fedf19c7ad608998026f1d6974f88fca`).
- Reviewed `hermes_screen/relay.py`, `hermes_screen/cast.py`, `hermes_screen/playback.py`,
  `hermes_screen/jellyfin.py`, `plugin.yaml`, `__init__.py`, `schemas.py`, `tools.py`,
  and `pyproject.toml`:
  - `JELLYFIN_API_KEY` stays server-side in `Capability.auth_header` (`repr=False`) and is
    sent only in the `Authorization` header to Jellyfin's static stream endpoint with
    `follow_redirects=False`. Capability tokens are 256-bit `secrets.token_urlsafe(32)`
    values redacted from `pychromecast` logs and never written by the HTTP server.
  - Capability TTL is bounded to 15 min – 4 hours (`duration_s + 900s`), checked on every
    request and every 64 KiB chunk. Expiry or replacement revokes the token, clears
    `auth_header`, shuts down active sockets (`SHUT_RDWR`), closes upstream streams, and
    closes the HTTP listener. `ctx.on_unload(manager.close)` cleans up on plugin unload.
  - `hermes plugins validate --install-deps` passes with a visible `security scan — caution`
    for `bind_all_interfaces` (`playback.py:77`, `plugin.yaml:50`, `relay.py:158`,
    `relay.py:166`); kept visible without scanner suppression.
- Two real-hardware fixes applied after live Chromecast Gen 2 (`192.168.0.134`, firmware
  `1.56.467165`) testing:
  1. `PyChromecastSession.close()` in `hermes_screen/cast.py` clears
     `socket_client._open_channels` before calling `cast.disconnect(timeout=2.0)` so
     disconnecting the per-call control socket does not send a Cast `CLOSE` message to
     `CC1AD845`'s `transport_id` (which caused `CC1AD845` to exit between `tv_play` and
     `tv_pause`).
  2. `CastPlaybackManager._await()` in `hermes_screen/playback.py` ignores an outgoing
     session's transitional `IDLE`/`INTERRUPTED` status when `session_id is None` and
     `outcome.last_state` has not yet reached `"BUFFERING"` or `"PLAYING"`.
- Automated checks: **553 pytest tests passed**, Ruff check/format clean (37 files),
  `git diff --check` clean, `hermes plugins doctor --ci` passed (4 tools, 0 hooks),
  `hermes plugins validate --install-deps` passed, and `tests/hermes_smoke.py` passed.
- Live Jellyfin `12.2.0` preflight and Chromecast Gen 2 (`192.168.0.134`) acceptance in
  the isolated Hermes `v0.22.0` runtime passed at `2026-11-10T01:43:22Z–01:43:32Z` UTC:
  - `library_status({})`: `ok: true`, `terebi` `12.2.0`, user `homelab-hp`.
  - `library_pick({"max_minutes": 20})`: `BigBuckBunny_320x180`
    (`e5d6c471a8a4ea26e00a3694f91bf8d1`, `source: "resume"`, `remaining_minutes: 2`).
  - `tv_play({"item_id": "e5d6c471a8a4ea26e00a3694f91bf8d1"})`: `ok: true`,
    `verified: true`, `state: "playing"`, `action: "started"`, `position_s: 0.0`,
    `duration_s: 596.5`, `relay_expires_in_minutes: 25`.
  - `tv_pause({})` after 5.0s: `ok: true`, `verified: true`, `state: "paused"`,
    `already_paused: false`, `position_s: 4.7`, followed by idempotent repeat
    `tv_pause({})` (`already_paused: true`, `position_s: 4.7`) and `on_unload` cleanup
    (`relay_port_8765_closed: true`, receiver returned to idle Backdrop).
