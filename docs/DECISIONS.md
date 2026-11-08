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
