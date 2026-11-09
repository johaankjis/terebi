# SUBMISSION CHECKLIST

Due **Wed Nov 11, 2026, 5PM EST**. Aim to submit by noon.

This document tracks catalog submission readiness. It is not a claim that the
plugin is catalog-ready or playback-ready; see the publication gates below.

## Current state (as of 2026-11-09)

- Registered tools: `library_status` and `library_pick` (2). No `tv_*` tool, `/watch`
  or Roku control exists.
- Hermes floor verified: `>=0.22.0` against upstream
  `e06df9c2eae6901f4c88f464e0ae6e753c0428b8`.
- Installed ZimaOS Hermes is `v0.16.0`, below the declared minimum; a separate
  v0.22.0 runtime is used for verification.
- Jellyfin upstream OpenAPI `12.4.0`; live server `terebi` `12.2.0` at
  `http://192.168.0.126:8097` (public endpoint reachable; authenticated access
  unverified).
- Historical checks at integration SHA `4362ed1ecdb2a3606695925e24a79b3949063414`:
  220 tests passed, Ruff check/format passed, `git diff --check` passed, doctor
  and validate passed, mocked Hermes smoke passed.
- Historical independent review of `4362ed1` reported zero blocking findings.
- The prior published `9320c3638d9f7d8579326e1a622a205523b395d1` differs from
  that reviewed integration by docs only.
- Combined picker integration tree: 328 tests, Ruff, diff check, official doctor,
  validate (security verdict **safe**) and mocked loader smoke passed with the picker
  still internal.
- Current tree with `library_pick` registered: 385 tests, Ruff, diff check, official
  doctor (2 tools, 0 hooks), validate (security verdict **safe**) and mocked loader
  smoke pass. Independent review of this registration remains pending. See
  INTEGRATION.md.

## Plugin quality

- [x] `hermes plugins doctor . --ci` passes
- [ ] `hermes plugins validate . --install-deps` passes at the exact publication commit
  (publication commit not selected; integration validation recorded below)
- [x] `provides_tools` / hooks / `requires_env` match what `register()` registers
  (`library_status`, `library_pick`)
- [x] `requires_hermes` SemVer floor in `plugin.yaml` (`>=0.22.0`)
- [x] No secrets in repo; secrets read only through Hermes
- [x] All tests pass; lint clean (385 tests, Ruff)
- [ ] README: what it does, GIF, requirements (Roku Permissive setting), install,
  config, troubleshooting, disclosures (GIF and Roku steps pending hardware)
- [x] LICENSE present; `version` in `plugin.yaml` matches the manifest (`0.1.0`; publication pin pending)

## Security scan state

The earlier published tree passed validation with a documentation false positive
(`context_exfil`, HARDWARE.md provenance line). The upstream v0.22.0
`tools/skills_guard.py` pattern was inspected; the adopted provenance clarification
uses “thread” and preserves the historical evidence. No scanner suppression is
used. Combined-tree validate exits 0 with security verdict **safe**, with no
caution warning. This is not a claim that the scanner reports no lower-severity
findings. Exact commands and logs are in INTEGRATION.md.

Catalog rule 7 treats `dangerous` as a failure and `caution` as requiring review;
a zero-caution result is not a separate catalog requirement.

## Catalog PR

- [ ] Fork `NousResearch/hermes-agent`
- [ ] Add exactly one file: `plugin-catalog/hermes-screen.yaml` (check name is free)
- [ ] Fields: `name`, `title`, `repo` (https), `sha` (full 40 chars), `description`
  (with disclosure lines), `maintainer`, `tier: community`, `category: tools`,
  `requires_hermes`, `docs_url` (README at the SHA), `version` (quoted),
  `platforms`, `capabilities`
- [ ] `capabilities.provides_tools` must list exactly `library_status` and `library_pick`
  until more tools are registered and verified.
- [ ] PR description: what it does, Hermes surfaces used, disclosures, screenshots
- [ ] Wait for catalog CI to go green; respond to reviewer

## Entry steps

1. [ ] Catalog PR open: http://hermes-agent.nousresearch.com/docs/developer-guide/plugins/catalog-submission
2. [ ] Demo video (under 90s) on X, tag @NousResearch
3. [ ] Both links in the form: http://form.typeform.com/to/FwJLvOln

## Historical source provenance (select a new publication pin)

- Prior published plugin tree: `9320c3638d9f7d8579326e1a622a205523b395d1`.
- Integration review SHA: `4362ed1ecdb2a3606695925e24a79b3949063414`.
- Jellyfin client worker: `c4c6c83e171a646b830b418cda79b6e420ecdf77`.
- Native skeleton worker: `4ebcb722500fffea9f1af65f909298a1b294d888`.
- Hermes upstream verified: `v0.22.0` /
  `e06df9c2eae6901f4c88f464e0ae6e753c0428b8`.
- Jellyfin OpenAPI: `12.4.0`, SHA256
  `02a6064916b7e08f1f1d8d7ffc1fb1c7623df0e378729fcd7fd353766868036e`.
- Jellyfin server: `terebi` `12.2.0` at `http://192.168.0.126:8097`.
- Roku: model 4200X at `192.168.0.104` (read-only probes only).

## Publication gates (must all be true before submitting)

- [ ] Hardware gate closed: Roku app signed in, one manual playback demonstrated,
  launch/in-app play/pause and exact target-session item ID verified; wake tested
  separately and reported as supported or unknown for this external Roku player.
- [ ] Roku ECP third-party shipping restriction resolved or explicitly accepted.
- [ ] Authenticated Jellyfin compatibility verified against the live server.
- [ ] Review scan verdict at the publication SHA; document any caution findings.
- [x] Deterministic picker integrated internally.
- [x] `library_pick` registered (mocked Jellyfin only).
- [ ] Verify `library_pick` through Hermes against the live server, then Telegram
  pick/play/pause; `/watch` follows.
- [ ] Independent review of the combined integration SHA (pending).
- [ ] Catalog PR CI green at the pinned SHA.
- [ ] Demo video under 90s recorded and posted.

## After submitting

- [ ] Nous Research Discord (http://discord.gg/nousresearch): watch for the entry thread
- [ ] Any SHA bump is a new PR
