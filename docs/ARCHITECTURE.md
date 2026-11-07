# Architecture

## Overview

```
User (CLI / Telegram / Discord / Desktop)
        │
        ▼
   Hermes Agent ───────────── Hermes memory (if exposed to plugins)
        │  calls tools
        ▼
┌──────────────── hermes_screen plugin ─────────────────┐
│ tools.py      thin layer: validate input, call core,  │
│               shape small results for the model       │
│                                                       │
│ devices/      roku.py        ECP over HTTP :8060      │
│               chromecast.py  pychromecast             │
│               discovery.py   SSDP + zeroconf, cache   │
│               base.py        Device interface         │
│                                                       │
│ catalog/      tmdb.py        search, discover,        │
│                              watch providers          │
│               providers.py   TMDB provider ↔ Roku     │
│                              channel mapping          │
│                                                       │
│ taste/        store.py       history + profile        │
│                              (JSON or SQLite)         │
│               profile.py     summarize into reasons   │
│                                                       │
│ watcher.py    polls tv_status, writes outcomes        │
│ config.py     services, region, default device, keys  │
└───────────────────────────────────────────────────────┘
        │                       │
        ▼                       ▼
   Roku / Chromecast       TMDB API (JustWatch data)
   on the local network
```

## Device interface

Every device implements the same small interface so tools don't care what the TV is.

```python
class Device(Protocol):
    name: str
    kind: Literal["roku", "chromecast"]

    def status(self) -> DeviceStatus: ...            # app, title if known, state, position
    def control(self, action: str) -> DeviceStatus: ...
    def launch(self, target: PlayTarget) -> PlayResult: ...
    def capabilities(self) -> set[str]: ...          # e.g. {"deeplink", "youtube", "url_cast"}
```

`PlayTarget` holds what we know about a title: TMDB id, title, type, service, season/episode, and any service specific content id. Each device decides the best way to play it and reports which method it used.

## Play strategy (Roku)

1. If we have a service content id: `POST /launch/{channel}?contentId=..&mediaType=..`
2. Else: `POST /search/browse?keyword=..&type=..&launch=true&provider-id=..`
3. Else: launch the channel and tell the user it's open at the app home.
4. Always confirm with `/query/active-app` and `/query/media-player` after a short wait. Report what actually happened.

Which step works per service is recorded in `docs/RESEARCH.md` after testing.

## Tools (model facing)

| Tool | Input | Output |
|---|---|---|
| `tv_discover` | none | list of `{name, kind, ip}` |
| `tv_status` | `device?` | `{app, state, title?, position?, duration?}` |
| `tv_control` | `action`, `device?` | confirmed status |
| `tv_apps` | `device?` | installed apps |
| `find_titles` | `query?`, `genres?`, `max_runtime?`, `mood?`, `type?` | 3 to 5 `{tmdb_id, title, year, runtime, service, why}` |
| `where_to_watch` | `title` or `tmdb_id` | services in region, flag for user's own |
| `tv_play` | `tmdb_id` or `title`, `season?`, `episode?`, `device?` | `{ok, method, playing}` |
| `tv_cast_youtube` | `video_id` or `query`, `start_seconds?` | `{ok}` |
| `tv_cast_url` | `url` | `{ok}` (Chromecast only) |
| `taste_get` | none | short profile + recent history |
| `taste_update` | `likes?`, `dislikes?`, `services?` | updated profile |

## Watcher

- Runs only while a device is reachable and on.
- Polls every 30 to 60 seconds.
- Ties a play session to the last `tv_play` call (we know the title for sure); ignores unknown content rather than guessing.
- On session end, writes outcome: abandoned (<15% watched), finished (>85%), binged (2+ episodes in one sitting), partial otherwise.
- How it runs depends on the Hermes plugin API (background task, hook, or cron). See RESEARCH.md.

## Data

- `config`: services, region, default device, manual IPs, TMDB key (env).
- `history`: list of sessions `{tmdb_id, title, type, started, watched_min, runtime_min, outcome}`.
- `profile`: stated likes/dislikes plus derived summary used for the one line reasons.
- Stored in the plugin data dir. Nothing leaves the machine except TMDB lookups.

## Error model

All tools return `{"ok": true, ...}` or `{"ok": false, "reason": str, "hint": str}`. Common reasons: `device_unreachable`, `device_permission` (Roku network access not Permissive), `not_on_your_services`, `deeplink_unsupported`, `tmdb_unavailable`, `not_found`.
