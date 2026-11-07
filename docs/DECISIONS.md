# DECISIONS

Lightweight decision log. Newest at the bottom. One entry per decision that someone might later ask "why did we do it this way?"

Format:

```
## D-NNN: Title
Date: YYYY-MM-DD · Status: accepted | superseded by D-NNN
Context: what forced the decision
Decision: what we chose
Why: the reasoning, alternatives considered
```

---

## D-001: Roku is the primary device, Chromecast secondary
Date: 2026-11-07 · Status: accepted
Context: We need to launch streaming titles on a TV from code.
Decision: Build Roku first via ECP; add Chromecast for YouTube and URL casting.
Why: Roku ECP is plain HTTP on the LAN with launch, deep link, search, and status endpoints. Chromecast can't play Netflix, Disney+, Max etc. from third party senders, so it can't carry the main demo.

## D-002: TMDB for catalog and availability
Date: 2026-11-07 · Status: accepted
Context: Picks must only include titles on the user's services in their region.
Decision: Use TMDB search/discover and watch providers (JustWatch data).
Why: Free, well documented, includes per region provider data. Requires attribution to TMDB and JustWatch.

## D-003: Learn from behavior, not ratings
Date: 2026-11-07 · Status: accepted
Context: Recommendations need to improve without user effort.
Decision: A watcher records finished/abandoned/binged outcomes for titles we launched.
Why: Ratings are rarely given; outcomes are free signal. Only titles we launched are tracked, so we never guess what's on screen.

## D-004: Python, httpx, pytest, ruff
Date: 2026-11-07 · Status: accepted
Context: Hermes is Python; we need fast, testable HTTP.
Decision: Python 3.11+, httpx with explicit timeouts, pytest + respx for mocks, ruff for lint/format.
Why: Matches the host, minimal deps, easy mocking so CI never needs hardware.
