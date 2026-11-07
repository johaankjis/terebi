# PRD: Hermes Screen

**Status:** Draft v1 · **Owner:** Johaan · **Deadline:** Nov 11, 2026, 5PM EST

## Problem

Choosing what to watch takes too long, recommendations are siloed inside each streaming app, and getting from "let's watch X" to X actually playing takes a remote, a search box, and patience. Hermes Agent knows the user and lives in their chats, but can't touch the TV.

## Goal

From one message to Hermes, the right thing starts playing on the TV, and the picks get better the more you use it.

## Users

- **Primary:** a Hermes user with a Roku (or Chromecast) at home who watches several streaming services.
- **Secondary:** a household or friend group choosing together in a shared Telegram or Discord chat.
- **Judges:** need to see it work end to end in under 90 seconds, and need it to install cleanly.

## Requirements

### P0 (must ship)

| ID | Requirement | Acceptance |
|---|---|---|
| P0.1 | Discover Roku devices on the LAN | `tv_discover` returns name + IP within 5s, or a clear error; manual IP fallback in config |
| P0.2 | Control the TV | `tv_control` handles play, pause, home, back, volume, power; returns confirmed state |
| P0.3 | Know what's on now | `tv_status` returns active app and play state/position |
| P0.4 | Find watchable titles | `find_titles` filters by the user's services, region, runtime, genre, mood keywords; returns 3 to 5 compact results |
| P0.5 | Where to watch | `where_to_watch` says which of the user's services has a title, or where else it is |
| P0.6 | Play a title on the TV | `tv_play` opens the right app at the title (deep link, else Roku search); verifies with `tv_status` |
| P0.7 | Remember what was watched | Watcher records started/finished/abandoned/binged; `taste_get` returns a short profile |
| P0.8 | Picks use history | Recommendations cite a reason drawn from history or stated likes |
| P0.9 | One time setup | User sets services + region once; TMDB key from config/env |
| P0.10 | Reliable errors | Every failure path returns a human message with a hint |

### P1 (should ship)

| ID | Requirement |
|---|---|
| P1.1 | Chromecast: discover, cast YouTube by video ID (with timestamp), cast a URL via DashCast |
| P1.2 | `tv_cast_youtube` works on Roku too (YouTube channel deep link) |
| P1.3 | "Next episode" for a series the user is mid way through |
| P1.4 | README with GIF, install, config, troubleshooting |

### P2 (stretch)

| ID | Requirement |
|---|---|
| P2.1 | Group vote in Telegram/Discord: post options, collect votes, play winner |
| P2.2 | Scheduled casting (e.g. a morning briefing page) via Hermes cron |
| P2.3 | Hermes Desktop "now playing" card, if the plugin API supports Desktop UI |
| P2.4 | Multiple TVs by room name ("bedroom TV") |

## Non goals

- Playing DRM content on Chromecast from third party code.
- Scraping streaming sites or logging in to them.
- Smart TVs other than Roku and Chromecast/Google TV during the hackathon.
- A standalone app or web UI outside Hermes.

## Success metrics (for the hackathon)

- Demo flow (message → TV playing) works 5 times in a row on real hardware.
- Fresh install to first successful play in under 5 minutes following the README.
- Catalog PR passes maintainer checks.
- Video under 90 seconds that clearly shows the TV turning on by itself.

## Risks

| Risk | Mitigation |
|---|---|
| Netflix and others don't honor Roku deep links | Test day one; fall back to ECP search, then app launch plus keypress search |
| SSDP blocked on some networks | Manual IP in config |
| Roku "Control by mobile apps" set to Default blocks commands | README setup step; detect and explain the error |
| Hermes plugin API differs from our assumptions | Read the dev guide before writing the package; record in RESEARCH.md |
| No hardware for the demo | Buy a cheap Roku stick this weekend |
