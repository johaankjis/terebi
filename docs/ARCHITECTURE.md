# Architecture

## Overview

```
User (CLI / Telegram / Discord / Desktop)
        │  message, /watch, or scheduled blueprint
        ▼
   Hermes Agent
        │  tool calls / slash command handler
        ▼
┌──────────────── hermes-screen plugin ────────────────┐
│ __init__.py   register(ctx): tools, /watch command,  │
│               movie night blueprint                  │
│ tools.py      thin handlers, small results, errors   │
│                                                      │
│ hermes_screen/                                       │
│   jellyfin.py  items, search, resume, next up,       │
│                user data, server info                │
│   roku.py      SSDP discovery, apps, active app,     │
│                media player, keypress, launch, input │
│   picker.py    filter + rank + one line reasons      │
│   config.py    settings + secrets via ctx            │
│   errors.py    {ok:false, reason, hint}              │
└──────────────────────────────────────────────────────┘
        │                           │
        ▼                           ▼
  Jellyfin server (LAN)      Roku (LAN, ECP :8060)
        ▲                           │
        └──── playback progress ────┘  (Jellyfin Roku app reports it)
```

Key idea: **Jellyfin is the source of truth** for the library and watch history. The Roku is the output. We never track history ourselves.

## Play path

1. Resolve the item in Jellyfin → `ItemId` + `Type` (Movie, Episode, Series, Season, Video).
2. Map type to the Roku app's `mediaType` (lowercase: `movie`, `episode`, `series`, `season`, `video`). Seasons also need `seriesID`.
3. If the Jellyfin app is not the active app:
   `POST /launch/{jellyfinChannelId}?contentId={ItemId}&mediaType={type}`
   If it is already active:
   `POST /input?contentId={ItemId}&mediaType={type}`
   (Both handled by the app's `onDeepLinkingEvent`, verified in source.)
4. Wait ~3s, then confirm with `/query/active-app` and `/query/media-player`. If not playing after ~10s, return `ok:false` with what we saw.
5. Optionally, cross check with Jellyfin `/Sessions` that the Roku session reports the item.

`jellyfinChannelId` is discovered from `/query/apps` by name ("Jellyfin") and cached in `ctx.state`.

## Tools (model facing)

| Tool | Input | Output |
|---|---|---|
| `tv_discover` | none | `[{name, ip, jellyfin_installed}]` |
| `tv_status` | `room?` | `{app, state, position_s?, duration_s?}` |
| `tv_control` | `action`, `room?` | confirmed status |
| `tv_play` | `item_id` or `title`, `room?` | `{ok, title, method, playing}` |
| `tv_youtube` | `video_id` | `{ok}` (P1) |
| `library_status` | none | server name, version, counts |
| `library_find` | `query?`, `genres?`, `max_minutes?`, `type?`, `unwatched?` | 3 to 5 `{item_id, title, year, minutes, type}` |
| `library_pick` | `mood?`, `max_minutes?`, `type?` | 3 `{item_id, title, year, minutes, why}` |
| `library_continue` | none | resume items + Next Up |

## Slash command

`/watch [mood or minutes]` → `library_pick` → `ctx.ask_choice` (buttons on Telegram/Discord) → `tv_play`. No model turn. Falls back to a text list when nothing can ask.

## Automation blueprint (P1)

`ctx.register_automation_blueprint("movie-night", ...)` with slots `time`, `weekdays`, `deliver`, `max_minutes`. The prompt asks Hermes to post 3 picks via `library_pick` and play the winner. Users enable it with `/blueprint movie-night`.

## Picker logic (deterministic first)

Rank candidates from Jellyfin with simple, explainable rules:
1. In progress items (resume) score highest when they fit the time.
2. Next Up episodes next.
3. Explicitly unwatched Movies/Videos, longest fitting first; no genre affinity
   without a history query (D-011).
4. Pass `max_minutes` unchanged to client tick filtering (1 tick = 100ns):
   remaining time for resume/Next Up, full runtime for unwatched.
5. Each pick carries the rule that selected it → that becomes the one line reason.

No LLM call needed for ranking; Hermes's own model does the conversation.

## Config and secrets

`plugin.yaml` `config_schema`: `jellyfin_url` (str), `jellyfin_api_key` (secret), `jellyfin_user` (str), `roku_ip` (str), `default_room` (str). Read through `ctx.get_config`; secrets through Hermes's secret scope. Never read `.env`.

## State

`ctx.state`: cached Roku IP, Jellyfin channel ID, Jellyfin user ID, last played item. Small and rebuildable.

## Error model

`{"ok": false, "reason": str, "hint": str}`. Reasons: `roku_unreachable`, `roku_permission` (Network access not Permissive), `jellyfin_app_missing`, `jellyfin_unreachable`, `jellyfin_auth`, `not_found`, `too_long`, `not_playing_after_launch`.

## Disclosures (for README + PR, catalog rule 13)

- Network calls only to the user's Jellyfin server and Roku on the LAN.
- SSDP multicast on the LAN for discovery.
- No shell commands, no background processes, no third party services.
