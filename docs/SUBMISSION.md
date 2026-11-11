# SUBMISSION CHECKLIST

Catalog submission readiness for `hermes-screen`. This document states exactly
what was verified where; it is the disclosure and evidence summary a catalog
reviewer needs alongside the PR description.

## Current state (as of 2026-11-11, candidate main `cd6d54d`)

- Registered at the candidate tree: **12 tools, 0 hooks** — `library_status`,
  `library_pick`, `tv_play`, `tv_pause`, `library_scene_find`,
  `library_scene_save`, `tv_scene_play`, `tv_game_start`, `tv_game_stop`,
  `tv_youtube_play`, `tv_youtube_pause`, `library_youtube_search`
  (toolset `hermes_screen`).
- Hermes floor: `requires_hermes: ">=0.22.0"` in `plugin.yaml` and the catalog
  entry; verified against upstream `v0.22.0`
  (`e06df9c2eae6901f4c88f464e0ae6e753c0428b8`). The plugin uses `ctx.on_unload`,
  session/conversation identity injection and secret-scope reads, all on the
  v0.22.0 public surface.
- Candidate checks at `cd6d54d`: **943 Python tests**, **73 camera JS tests**,
  Ruff check/format clean, `hermes plugins doctor . --ci` (12 tools / 0 hooks),
  `hermes plugins validate . --install-deps` **passes**.
- Live verification runs in an isolated Hermes v0.22.0 gateway; the installed
  ZimaOS Hermes container is v0.16.0 and is not touched by this work.

## Security scan state

`hermes plugins validate --install-deps` exits 0 with
`✓ security scan — caution`:

```
bind_all_interfaces (playback.py:85)
bind_all_interfaces (plugin.yaml:58)
bind_all_interfaces (relay.py:158)
bind_all_interfaces (relay.py:166)
tunnel_service (games/deploy/compose.yaml:22)
```

All five are deliberate, documented behavior: the movie relay may bind
`0.0.0.0:8765` inside a bridge-networked Hermes container (the Chromecast then
connects to the host's LAN IP via `cast_media_base_url`), and the game deploy
runs a Cloudflare tunnel sidecar (`tunnel_service`) because the phone camera
needs a trusted HTTPS origin. No scanner suppression is used; the cautions stay
visible for review. No `dangerous` findings.

## Credentials

- All secrets read via `agent.secret_scope.get_secret` through declared
  `config_schema` secret entries: `JELLYFIN_API_KEY`, `TEREBI_GAMES_API_KEY`,
  `YOUTUBE_API_KEY` (optional). Never `.env`, never `os.environ`, never other
  credential stores.
- No OAuth flows. No subscription sign-ins. No tokens written to disk by the
  plugin. The game admin token is generated host-side by the standalone service
  and never committed or printed.
- Capability URLs are random, single-item/single-session and expire (movie
  relay: bounded TTL; game pairing: one-use/3 minutes; viewer capabilities
  expire with the session).

## Disclosure summary (rule 13)

- **Network calls:** configured Jellyfin server; configured Chromecast on TCP
  8009 (Cast protocol); YouTube served by YouTube on the TV; `www.gstatic.com`
  (CAF SDK, receiver page only); the user's own game service origin; optional
  YouTube Data API v3; optional Cloudflare Quick Tunnel exposure.
- **Listeners/background:** temporary HTTP relay bound only while a movie
  plays (revoked on expiry/unload); the game service is a separate two-container
  Docker Compose deployment the user opts into (loopback-published port +
  tunnel sidecar).
- **Local data:** scene markers, subtitle indexes, game session records in
  Hermes per-profile plugin state and the service's private config. Nothing
  syncs or phones home.
- **Reads outside plugin data:** only the configured Jellyfin server and the
  user's own game service.
- **Telemetry:** none, opt-in or otherwise.
- **Shell commands:** none executed on the user's machine by the plugin; the
  game deploy scripts run only on the host the user chooses.
- **Bundled assets:** the game background track `games/display/hydrate.mp3`
  (see provenance below).

## Public tree and history scan

Full scan of all commits/refs and the candidate tree found **no credentials**:
no API keys, bot tokens, OAuth/SSH secrets, `.env`/key files, or committed
test-credential lookalikes beyond fixtures. Findings worth disclosure:

- A Cloudflare Quick Tunnel hostname and LAN IPs exist in **pushed history
  only** (evidence file later redacted at main). Tunnel hostnames rotate on
  restart, so the residual risk is low; noted here for the reviewer.
- LAN IPs, Jellyfin server name/user, and item/user IDs remain in internal
  dev-record docs (`docs/HARDWARE.md`, `docs/PLAN.md`,
  `docs/INTEGRATION.md`, `docs/RESEARCH.md`, evidence JSONs). These are
  infrastructure details, not credentials; the user-facing docs (README,
  SETUP, SUBMISSION) use placeholders only.
- `.DS_Store` was tracked; untracked in this PR.
- Screenshots reviewed: no pairing URLs/tokens visible (phone screenshot shows
  only a truncated proof hash). The two evidence MP4s still need a manual
  frame review before any catalog use.

## Bundled asset provenance

- Camera WASM/model assets are **not committed**: they are built at Docker
  image build time from pinned npm sources with checksum validation
  (`games/camera/scripts/build.mjs`, `games/camera/assets.manifest.json`). No
  `.wasm`/`.task`/`.pyc`/binaries are committed; the tree is scanner-readable.
- **Release blocker to resolve before pinning:** the game background track
  `games/display/hydrate.mp3` (39.5 MB, 192 kbps MP3, user-supplied
  "frutiger aero" playlist mix) has **no documented redistribution license**.
  Options before the catalog PR pins a SHA: (a) confirm the track is
  self-made/public-domain/CC0 and record it here, (b) replace it with a
  known-license track, or (c) drop the music feature. Shipping it as-is without
  provenance is not acceptable for redistribution.

## Screenshots / media review

- `docs/evidence/rps-aero/` PNGs: reviewed — the TV screenshots contain no
  URLs or tokens; the phone screenshot shows only a truncated proof hash
  (`proof 1addc90370...`, already truncated by the UI) and no pairing link.
- `docs/evidence/rps-aero/*.mp4` (2 files): **frame-by-frame review pending** —
  they are screen recordings of the phone/TV flow and could contain a pairing
  URL if captured during pairing. Review before any catalog screenshot uses
  them; the catalog entry below uses static PNGs only.
- Catalog `image`/`screenshots` must be `raw.githubusercontent.com` URLs pinned
  to the entry SHA.

## Draft catalog entry (`plugin-catalog/hermes-screen.yaml`)

Pin `<PUBLISHED_SHA>` to the final public 40-character commit of this
repository after this PR merges, and re-run
`hermes plugins validate <checkout> --install-deps` on that exact tree before
opening the upstream PR.

```yaml
name: hermes-screen
repo: https://github.com/johaankjis/terebi
sha: <PUBLISHED_SHA>
description: >-
  Pick what to watch from your own Jellyfin library using real watch history,
  play movies and saved scenes on your Chromecast with receiver-verified
  status, send YouTube links to the TV, and play camera rock-paper-scissors
  against Hermes. Network calls: your Jellyfin server, your Chromecast
  (Cast protocol, TCP 8009), YouTube on the TV, www.gstatic.com (receiver
  SDK), your own optional game service, and optional YouTube Data API.
  Listeners: a temporary expiring movie relay while something plays, and an
  opt-in two-container game service you deploy yourself. No telemetry.
  Secrets only via Hermes; no .env reads. Camera frames never leave the phone.
maintainer: Johaan Jis
tier: community
category: tools
requires_hermes: ">=0.22.0"
version: "0.1.0"
title: Hermes Screen
platforms: []                 # plugin itself is platform-neutral; the game service needs a Linux host with Docker
screenshots:
  - https://raw.githubusercontent.com/johaankjis/terebi/<PUBLISHED_SHA>/docs/evidence/rps-aero/tv-reveal.png
  - https://raw.githubusercontent.com/johaankjis/terebi/<PUBLISHED_SHA>/docs/evidence/rps-aero/tv-ready.png
  - https://raw.githubusercontent.com/johaankjis/terebi/<PUBLISHED_SHA>/docs/evidence/rps-aero/phone-controller.png
capabilities:
  provides_tools:
    - library_status
    - library_pick
    - tv_play
    - tv_pause
    - library_scene_find
    - library_scene_save
    - tv_scene_play
    - tv_game_start
    - tv_game_stop
    - tv_youtube_play
    - tv_youtube_pause
    - library_youtube_search
  provides_hooks: []
  provides_middleware: []
  requires_env: []
```

Slug availability: no `plugin-catalog/hermes-screen.yaml` exists upstream
(checked `NousResearch/hermes-agent` on 2026-11-11); the `name` matches
`plugin.yaml`'s manifest name. Category `tools` (home-theater control tools).

## Verified on hardware vs mocked

| Feature | Verified on real hardware | Mocked/browser only |
|---|---|---|
| `library_status` / `library_pick` | Jellyfin 12.2.0 live | — |
| `tv_play` / `tv_pause` (movie) | Chromecast Gen 2, receiver-confirmed PLAYING/PAUSED, Telegram | — |
| Scene save/find/play | Telegram end-to-end, receiver-confirmed seek positions | paraphrase vocabulary coverage |
| `tv_game_start` (Custom Receiver) | Den TV receiver launch + render acknowledgement | Cast transport mocks |
| `tv_game_start` (manual mirroring) | Den TV via Chrome cast tab | — |
| Camera rounds / practice / Retry | iPhone Safari, real hand poses | frame-injection unit tests |
| `tv_game_stop` | Telegram + phone camera release + receiver exit | — |
| Game music on TV | ZimaOS deploy verified via tunnel (served files); audible playback check pending on TV | audio element logic (vm tests) |
| `tv_youtube_play` / `tv_youtube_pause` | Chromecast Gen 2, exact video ID + PLAYING/PAUSED evidence, Telegram link request | — |
| `library_youtube_search` | — | mocked official API (key unconfigured) |
| TV wake / HDMI switching | separate manual checks, not claimed by tools | — |

Unverifiable-from-here fresh-device steps: Google Cast developer registration
(user account), tunnel hostname stability, other Jellyfin versions/servers,
other Chromecast models/generations.

## Catalog PR steps

1. [ ] Resolve the game-music provenance blocker (above).
2. [ ] Frame-review the two `.mp4` evidence files (or exclude them from the PR).
3. [ ] Land this PR; record the final public SHA below.
4. [ ] Validate that exact tree from a fresh clone + empty Hermes profile
       (doctor + `validate --install-deps`).
5. [ ] Fork `NousResearch/hermes-agent`, add exactly
       `plugin-catalog/hermes-screen.yaml` with the pinned SHA.
6. [ ] PR description: what it does, Hermes surfaces used, disclosure lines,
       screenshots.
7. [ ] Wait for catalog CI green; respond to review.

Final public SHA: _to be recorded after this PR lands_.
