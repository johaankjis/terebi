# DECISIONS

Lightweight decision log. Newest at the bottom.

Format:

```
## D-NNN: Title
Date: YYYY-MM-DD · Status: accepted | superseded by D-NNN
Context: what forced the decision
Decision: what we chose
Why: the reasoning, alternatives considered
```

---

## D-001: Roku is the primary device
Date: 2026-11-07 · Status: accepted
Context: We need to start playback on a TV from code.
Decision: Roku via External Control Protocol (ECP).
Why: Plain HTTP on the LAN with launch, input (deep link while running), keypress and status endpoints. No auth. Chromecast can't play most apps' content from third party code.

## D-002: TMDB for catalog and availability
Date: 2026-11-07 · Status: superseded by D-005
Context: Picks had to come from the user's streaming services.
Decision: TMDB search/discover + watch providers.
Why superseded: We dropped streaming services as the play target.

## D-003: Background watcher to learn from behavior
Date: 2026-11-07 · Status: superseded by D-005
Context: Needed watch history to improve picks.
Decision: Poll the Roku and record outcomes.
Why superseded: Jellyfin already stores watched state, resume position and Next Up, reported by its Roku app.

## D-004: Python, httpx, pytest, ruff
Date: 2026-11-07 · Status: accepted
Context: Hermes is Python; we need fast, testable HTTP.
Decision: Python 3.11+, httpx with explicit timeouts, pytest + respx, ruff.
Why: Matches the host, minimal deps, CI never needs hardware.

## D-005: Pivot to Jellyfin as library and history
Date: 2026-11-08 · Status: accepted
Context: Netflix and other streaming apps don't expose content IDs, so Roku deep links into them are unreliable. That was the core risk of the project.
Decision: Play from the user's Jellyfin library via the official Jellyfin Roku app. Jellyfin API is the source of truth for items and watch history.
Why: The Jellyfin Roku app implements Roku deep linking with Jellyfin item IDs for movie, episode, series, season, video, audio and more (source/MainEventHandlers.bs, onDeepLinkingEvent), on launch and while running. We get IDs from the Jellyfin API, so play is deterministic. Zero Jellyfin plugins in the Hermes catalog. Tradeoff: only plays the user's own library.

## D-006: Deterministic picker, no extra LLM calls
Date: 2026-11-08 · Status: accepted
Context: Picks must be fast, cheap and reliable.
Decision: Rank with explainable rules (resume, Next Up, unwatched in most finished genres, runtime fit). The rule that fired becomes the reason.
Why: Reliability is scored; Hermes's own model already handles conversation and mood interpretation.

## D-007: Roku control via ECP, not Jellyfin remote control
Date: 2026-11-08 · Status: accepted
Context: Jellyfin has a server side "remote control" for sessions.
Decision: Use Roku ECP keypress for pause/play/volume.
Why: The Jellyfin Roku app reports `SupportsMediaControl: false` (source/utils/deviceCapabilities.bs), so server side remote control won't work for it.

## D-008: Legal demo content only
Date: 2026-11-08 · Status: accepted
Context: Need a library to demo with.
Decision: Blender open movies and public domain films. No `.strm` links to pirate, debrid or Stremio sources.
Why: Public catalog PR and video under our names; it also keeps the project clean for the marketplace.

## D-009: Rebase planning on the Jellyfin pivot; carry evidence selectively
Date: 2026-11-08 · Status: accepted
Context: Main is now 4fd89d1b0cad82284f960be146bab444cfc9ff13. Older checkpoints
and stash describe the superseded streaming-subscription design.
Decision: All new worker checkouts start at this exact base. Retain observed
hardware/network results, honest playback states and session isolation; discard
old TMDB/watcher/Chromecast assignments. Manager owns sequential hardware tests
and shared docs; workers get disjoint implementation files after the backend gate.
Why: Whole-stash application would overwrite the new product direction and collide
with decision numbers. Jellyfin solves item IDs/history; real playback and the
previously observed ECP shipping restriction still require explicit resolution.

## D-010: Integration conventions for native loader, secrets, and session bounds
Date: 2026-11-08 · Status: accepted
Context: Combining the native Hermes skeleton (`4ebcb72`) and Jellyfin client (`c4c6c83`) at `4362ed1`.
Decision:
- Use released Hermes `v0.22.0` (`e06df9c2eae6901f4c88f464e0ae6e753c0428b8`) as the verified source floor; installed ZimaOS version remains to be confirmed on host.
- Bind handlers by closure and read settings/secrets each call; avoid global context/client caches across profiles. Relative imports match the official `hermes_plugins.<slug>` loader.
- Keep only `library_status` in `plugin.yaml` until Roku tools are built; document all other product flows as planned.
- Use `PyYAML>=6,<7` as a dev dependency to test actual manifest parsing; `httpx` remains the sole production dependency.
- Enforce exact case-sensitive username matching (or normalized GUID) and fail session verification when responses hit the 200-session scan cap rather than hiding possible device ambiguity. Separate item identity (`verified`) from `playing`/`paused` evidence.
Why: Prevents cross-profile state leaks, guarantees valid manifest parsing under `hermes plugins validate`, and preserves strict verification semantics.

## D-011: Picker uses returned watch state and exact client runtime filtering
Date: 2026-11-09 · Status: accepted
Context: Integrating the deterministic picker against the existing Jellyfin client.
Decision: Rank resume, then Next Up, then explicitly unwatched Movies/Videos; no
genre affinity ranking because no history query supplies evidence for it.
Pass the runtime float unchanged to the client, which filters raw ticks: remaining
runtime for resume/Next Up, full runtime for new picks. Rounded minutes are display
only, labeled when rounding exceeds the window; Next Up reasons say time left.
Why: Avoid fabricated taste/history and preserve fractional limits. The picker
stays internal; only library_status is registered. D-006's genre-affinity ambition
is deferred until supported by actual history. No dependency or tool API added.

## D-012: Register `library_pick` with a strict two-argument contract
Date: 2026-11-09 · Status: accepted
Context: Exposing the internal picker (D-011) as a Hermes tool.
Decision: Register `library_pick(max_minutes, limit?)` beside `library_status`;
`plugin.yaml` `provides_tools` lists both. The handler accepts a dict or its JSON
text, rejects any other argument (the ARCHITECTURE sketch's `mood` and `type` do not
exist yet, and silently ignoring a constraint would break the "strictly fits"
promise) and passes values to `pick_titles` for validation. Settings and the secret
are read on every call and a fresh client is opened per call, as in `library_status`;
no exception text is returned. The tool only reads the library and starts no playback.
Why: Same isolation and redaction guarantees as `library_status`, a deterministic and
predictable model-facing contract, and `provides_tools` parity for catalog validation.
No dependency added. Validation order: argument shape, then configuration, then
`pick_titles` value checks, so a bad `max_minutes` on an unconfigured install reports
`not_configured` first.

## D-013: Hold Roku 3 programmatic control on the ECP third-party restriction; evaluate Chromecast
Date: 2026-11-09 · Status: accepted
Context: Manual playback of `BigBuckBunny_320x180` (`e5d6c471a8a4ea26e00a3694f91bf8d1`)
on Roku 3 (`192.168.0.104`) and exact item verification via Jellyfin `/Sessions`
(`JellyfinClient.verify_playback`) succeeded. We then checked whether there is a
documented, supported way for Terebi to start and pause Jellyfin on this Roku 3.
Decision: Do not send ECP launch or pause commands to the Roku 3 while Roku's
third-party platform restriction remains unresolved; assess the user's Chromecast as
the next playback target once its LAN IP, model, and control mode are confirmed.
Why:
1. Live `/Sessions` on `Jellyfin Roku` `3.2.4` confirmed `SupportsMediaControl: false`,
   `SupportsRemoteControl: false`, and `SupportedCommands: []`, ruling out Jellyfin
   server-side remote control (`/Sessions/{id}/Playing`).
2. `jellyfin-roku` does not implement a DIAL receiver, and DIAL does not define
   post-launch pause control.
3. Although `jellyfin-roku` `3.2.4` implements ECP `/launch`, `/input` deep links,
   and `roInput` transport events (`type=transport&command=pause`), Roku's official
   ECP docs state that *"ECP commands may not be sent from 3rd-party platforms (for
   example, mobile applications)."*
4. On Chromecast, direct Cast control (`pychromecast` over TCP `8009` to a configured
   LAN IP) can launch the Default Media Receiver from idle over LAN HTTP and pause
   it, or Jellyfin `/Sessions/{id}/Playing` can control an already-open Jellyfin
   Android TV / Google TV session (`SupportsMediaControl: true`). Selecting between
   those paths requires the user's Chromecast model and LAN IP (and dependency
   approval if `pychromecast` is added).

## D-014: Gate Cast integration on a temporary, credential-free hardware proof
Date: 2026-11-10 · Status: accepted
Context: User identified Chromecast Gen 2 at `192.168.0.134` and requested a direct
idle → MP4 playback → pause test before integration, with endpoint removal afterward.
Decision: Use a disposable one-file HTTP server and `pychromecast` 14.1.1 in an
existing temporary venv for the spike only. No production dependency is added.
Require a fresh receiver `content_id` matching the exact test URL plus `PLAYING`,
then `PAUSED` for the same media session. A title label supplied by the sender,
accepted load, receiver launch or `IDLE` status is insufficient. Keep TV/CEC wake
and human screen confirmation separate. Record the initial failed media-reachability
attempt and subsequent successful exact-URL play/pause after host port forwarding
became available. The proof is recorded before integration work.
Why: Outbound Cast connectivity from a Docker bridge does not establish the
receiver's ability to fetch an inbound media URL. Exposing only a disposable MP4
avoids sending Jellyfin credentials or publishing a library directory.

## D-015: Jellyfin-to-Chromecast `tv_play`/`tv_pause` via expiring item-scoped LAN relay
Date: 2026-11-10 · Status: accepted
Context: Integrating the Jellyfin-to-Chromecast slice (`de5bf8d5ab33faec4fbf1b43bafaa9e269ae0493`) after the direct Cast hardware proof on Chromecast Gen 2 (`192.168.0.134`).
Decision:
- Register `tv_play(item_id)` and `tv_pause()` alongside `library_status` and `library_pick` (4 tools, 0 hooks), adding `pychromecast>=14,<15` as a second production dependency in `pyproject.toml`.
- Validate exact items before casting with `JellyfinClient.get_cast_source(item_id)`: only `Movie`, `Episode`, or `Video` items with a local `File` protocol MP4/M4V container, H.264 video (`<=1080p`), and AAC/MP3 (or no) audio are accepted; unsupported items fail with `unsupported_media` rather than attempting transcoding.
- Keep `JELLYFIN_API_KEY` server-side in `MediaRelay`: mint one 256-bit capability URL (`/cast/<token>/video.mp4`) at a time with TTL bounded to `[15 min, 4 hours]` (`duration_s + 900s`, or `3600s` when runtime is unknown). Forward `GET`/`HEAD` and single `bytes=` ranges to Jellyfin's static stream endpoint with `follow_redirects=False` and `Authorization` in the upstream header only. On expiry, replacement, `close_cast_relay()`, or `ctx.on_unload`, revoke the capability, clear the stored auth header, shut down active client sockets (`SHUT_RDWR`), close upstream streams, and close the HTTP listener when idle.
- Require fresh receiver media telemetry matching the exact capability URL (`content_id == capability_url`, `player_state == "PLAYING"` for `tv_play`, and `player_state == "PAUSED"` on the same session for `tv_pause`). Keep TV/CEC wake out of scope.
- Clear `socket_client._open_channels` before `cast.disconnect(timeout=2.0)` in `PyChromecastSession.close()` so closing a per-call control connection does not send a Cast `CLOSE` message to `CC1AD845`'s `transport_id` (which terminates the Default Media Receiver on Chromecast Gen 2 when the last sender disconnects), and ignore the outgoing session's transitional `IDLE`/`INTERRUPTED` event when `LOAD` replaces an existing session on the receiver.
- Keep the `hermes plugins validate` `security scan — caution` (`bind_all_interfaces` on `playback.py:77`, `plugin.yaml:50`, `relay.py:158`, `relay.py:166`) visible and documented rather than suppressing scanner rules or hiding the containerized `0.0.0.0:8765` bind option.
Why: The Chromecast Default Media Receiver fetches media over plain HTTP from the LAN and cannot safely receive the user's Jellyfin API key in a query string. An expiring single-item capability relay bounds exposure to the selected item and duration while preserving strict receiver verification.

## D-016: Scene resolution is bound to one edition and preserves evidence
Date: 2026-11-10 · Status: accepted
Decision: Search the selected media source's own text subtitles, preserving cue
text, language and millisecond timestamps; exact and approximate lexical results
remain labelled. Keep a bounded local profile cache, refresh content/metadata on
lookup, and revalidate caption evidence before playing a chosen scene. No embedding
model is enabled without explicit local-model approval. No new dependency.

Movie/edition ambiguity returns choices. Scene candidates expire in 15 minutes and
are scoped to trusted conversation context. Manual markers are local, idempotent
by edition and label, and explicitly user supplied; they do not claim visual
understanding. A user timestamp is an honest fallback for captionless scenes.
The user approved OpenCode GLM 5.3 Flash after requested GLM 5.1 was unavailable.


## D-018: Local lookup of verified saved scene descriptions (2026-11-10)

Reuse exact-edition marker storage and timestamp playback. Optional description,
aliases, and end metadata extend existing marker evidence without replacing other
markers or altering movie files. A small deterministic phrase/synonym matcher
returns clear, ambiguous, or none; no model, dependency, network lookup, subtitle
indexing, or frame analysis is added. An ambiguous description requires choice;
unmatched descriptions offer a timestamp. Revalidate the edition fingerprint and
saved record before consuming a conversation-bound playback candidate. Scene
start times must come from exact-copy inspection or explicit user verification.


## D-019: Merge scene playback on live saved-description acceptance (2026-11-10)

The user authorized merging PR #4 (edition-specific scene playback) and PR #5
(saved-description matching) through the normal GitHub PR flow. This replaces
the earlier PR #4 gate that required live subtitle-derived scene resolution. The
library still has no subtitled movie, so subtitle scene search remains verified by
tests only. Live acceptance verified that a Telegram paraphrase reached a confirmed
burrow marker on Den TV at 45 s. Pause is device-reported. No-match behavior is
covered by unit tests only. PR #4 merges with a merge commit so that the stacked
PR #5 diff contains only its own commits. Deploying to the production bot is a
separate step.


## D-019: Standalone RPS session authority and manual TV mirroring (2026-11-11)

Serve one game session to both the local-camera player and TV display. A Python
standard-library service owns all round phases, locks Hermes's move before
countdown, commits it with a random nonce, rejects stale/duplicate/early/late moves,
and scores once under a lock. Retry retains the move and score while rotating
attempt ID. One-use 3-minute pairing yields separate player/read-only display
credentials expiring at 30 minutes; all sessions are memory-only. Hermes adds one
`tv_game_start` tool with scoped secret access and bounded httpx calls.

User chose Mac Chrome manual mirroring because no Custom Receiver app or test
registration exists. iPhone Safari camera needs trusted HTTPS. Use a separately
containerized, localhost-published service and optional account-free Quick Tunnel;
its public hostname is not a credential. Camera assets are pinned/self-hosted,
frames never go to the service, and score events contain only move/state data and
hashed session/attempt IDs. Existing movie tools remain independently configured.
No new Python production dependency. The separate camera build pins MediaPipe
0.10.35 to avoid the newer bundles' usage logger; a same-origin CSP also blocks
third-party browser network connections. Containerized deployment and real device
acceptance remain unverified until the user runs the host commands.


### RPS iPhone practice diagnostics (2026-11-11)

Add temporary practice before camera rounds to distinguish recognition failure
from countdown timing. Keep the current MediaPipe runtime/model and thresholds.
Render the latest landmarks locally; retain only compact predictions in the
bounded round window. Clear practice predictions before rounds and on Stop.
Expose local loading stages and Shoot sample counts without new API fields or
telemetry. Require three locally recognized shapes in the practice UI before
continuing. This is diagnostic instrumentation, not a claim of iPhone accuracy.


### Accept a post-Shoot stable run (2026-11-11)

User's practice now recognizes gestures but a live round rejects the reveal.
Replace round-only majority across pre/post-Shoot frames with a rolling suffix
of consecutive confident predictions from +150 to +900 ms. Require >=3 frames
spanning >=120 ms, maximum 250 ms gap and age; reset on an unclear or different
prediction. Submit the first stable run once. At deadline, Retry without a move
if still unclear. Keep the existing model, confidence threshold, server-owned
score, attempt IDs and practice decision unchanged. Timing constants are explicit
and reported locally for iPhone diagnosis; device success remains unverified.
