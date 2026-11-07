# RESEARCH

Facts we rely on, with a status. **Do not depend on anything `UNVERIFIED` without checking it first.** When you verify something, change the status, add the date and how you checked.

Statuses: `VERIFIED` (checked against docs or real device), `UNVERIFIED` (from memory or secondhand), `FALSE` (checked and wrong; keep for history).

## Hermes Agent plugin API

| Fact | Status | Source / notes |
|---|---|---|
| Plugins managed via `hermes plugins list / install / enable / remove` | VERIFIED (secondhand) | Third party docs and Hermes CLI help text seen in search results, 2026-11-06 |
| Installed plugins start disabled; `hermes plugins enable <name>` turns them on | VERIFIED (secondhand) | You.com plugin install docs, 2026-11-06 |
| Manifest file name and fields | UNVERIFIED | Check developer guide |
| How tools are registered (entry point, `register(ctx)`?) | UNVERIFIED | Check developer guide |
| Can a plugin run a background task (for the watcher)? | UNVERIFIED | Alternatives: hook on each turn, Hermes cron |
| Can a plugin read/write Hermes memory? | UNVERIFIED | Else use our own store |
| Plugin config / secrets mechanism | UNVERIFIED | |
| Hermes Desktop UI extension API | UNVERIFIED | Only needed for P2.3 |
| Catalog submission requirements (files, tests, license, CI checks) | UNVERIFIED | Check catalog submission page |

Docs: http://hermes-agent.nousresearch.com/docs/developer-guide/plugins and `/catalog-submission`. Note: fetching these through an automated tool hit an http/https redirect loop on 2026-11-06; open in a browser.

## Roku ECP

| Fact | Status | Notes |
|---|---|---|
| HTTP on port 8060, no auth | UNVERIFIED | Roku ECP docs |
| SSDP discovery with `ST: roku:ecp` on 239.255.255.250:1900 | UNVERIFIED | |
| Endpoints: `/query/device-info`, `/query/apps`, `/query/active-app`, `/query/media-player` | UNVERIFIED | |
| `POST /keypress/{key}` (Home, Play, Back, Select, VolumeUp, PowerOn, ...) | UNVERIFIED | |
| `POST /launch/{appId}?contentId=..&mediaType=..` deep link | UNVERIFIED | |
| `POST /search/browse?keyword=..&type=..&launch=true&provider-id=..` | UNVERIFIED | |
| Settings > System > Advanced system settings > Control by mobile apps > Network access must be Permissive for full control | UNVERIFIED | |
| Channel IDs: Netflix 12, YouTube 837, Prime Video 13, Hulu 2285, Disney+ 291097, Max 61322 | UNVERIFIED | Confirm via `/query/apps` on device |

### Deep link test matrix (fill on real device)

| Service | Deep link with contentId | `/search/browse` launch | App launch only | Notes |
|---|---|---|---|---|
| YouTube | | | | |
| Netflix | | | | |
| Hulu | | | | |
| Max | | | | |
| Prime Video | | | | |

Roku model / OS version tested: _fill in_

## Chromecast

| Fact | Status | Notes |
|---|---|---|
| `pychromecast` discovers via zeroconf | UNVERIFIED | |
| `YouTubeController` plays by video ID | UNVERIFIED | Check timestamp support |
| `media_controller.play_media(url, mime)` for direct media | UNVERIFIED | |
| `DashCastController` loads arbitrary URLs | UNVERIFIED | |
| Netflix/Disney+/Max cannot be cast by third party senders | UNVERIFIED (high confidence) | |

## TMDB

| Fact | Status | Notes |
|---|---|---|
| Base URL `https://api.themoviedb.org/3`, free API key | UNVERIFIED | |
| `/search/multi`, `/discover/movie`, `/discover/tv` | UNVERIFIED | |
| Discover filters: `with_watch_providers`, `watch_region`, `with_runtime.lte`, `with_genres` | UNVERIFIED | |
| `/{type}/{id}/watch/providers` returns per region availability | UNVERIFIED | |
| Provider IDs: Netflix 8, Prime 9, Hulu 15, Disney+ 337, Max 1899 | UNVERIFIED | Confirm via `/watch/providers/movie?watch_region=US` |
| Watch provider data must be attributed to JustWatch | UNVERIFIED (high confidence) | |
| TMDB does not give Netflix/Hulu native content IDs | UNVERIFIED | Drives the search fallback |

## Open questions

1. Exact Hermes plugin structure and whether background tasks are allowed.
2. Which services deep link on our Roku.
3. How the catalog CI tests plugins (do we need a test command?).
4. Does Roku `/query/media-player` expose title info for all channels, or just state/position?
