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
