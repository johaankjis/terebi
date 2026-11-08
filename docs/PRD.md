# PRD: Hermes Screen

**Status:** Draft v2 (Jellyfin on Roku) · **Owner:** Johaan · **Deadline:** Wed Nov 11, 2026, 5PM EST

## Problem

Jellyfin users have a library they curated but still scroll it for ages, lose track of what they were halfway through, and need the remote and several menus to start anything. Hermes knows the user and lives in their chats, but can't reach the TV.

## Goal

From one message (or one tap) to Hermes, the right thing from your own library starts playing on the TV.

## Users

- **Primary:** a self hoster running Jellyfin and Hermes, with a Roku TV.
- **Secondary:** a household choosing together in a Telegram or Discord group.
- **Judges:** need to see it work end to end in under 90 seconds, and need it to install and validate cleanly.

## Requirements

### P0 (must ship)

| ID | Requirement | Acceptance |
|---|---|---|
| P0.1 | Connect to Jellyfin | Settings take URL + API key (secret) + optional user; `library_status` confirms server name and item counts, or explains the failure |
| P0.2 | Find the Roku | `tv_discover` returns name + IP within 3s via SSDP; manual IP setting as fallback; reports whether the Jellyfin app is installed |
| P0.3 | Search and filter the library | `library_find` by text, genre, max runtime, type (movie/series), unwatched only; returns 3 to 5 compact results with item IDs |
| P0.4 | Grounded picks with reasons | `library_pick` returns 3 picks with a one line reason drawn from watch state (in progress, unwatched favorite genre, Next Up, recently finished similar) |
| P0.5 | Play on the TV | `tv_play` deep links the Jellyfin Roku app to an item (movie, episode, series, season) and verifies via Roku active app / media player |
| P0.6 | Resume and next episode | `library_continue` returns resume items and Next Up; playing them works through `tv_play` |
| P0.7 | Control playback | `tv_control` play/pause, back, home, volume up/down/mute, power on/off; returns confirmed state |
| P0.8 | Know what's on | `tv_status` returns active app and play state/position |
| P0.9 | `/watch` slash command | One tap picker (`ctx.ask_choice`) of 3 picks, plays the chosen one without a model turn |
| P0.10 | Reliable errors | Every failure returns `{ok:false, reason, hint}` with a human fix |
| P0.11 | Passes catalog validation | `hermes plugins doctor --ci` and `hermes plugins validate --install-deps` green |

### P1 (should ship)

| ID | Requirement |
|---|---|
| P1.1 | Movie night automation blueprint: schedule + chat target; posts 3 picks for a vote and plays the winner |
| P1.2 | `tv_youtube` deep links the Roku YouTube app to a video ID |
| P1.3 | Settings form in Desktop via `config_schema` |
| P1.4 | README with GIF, install, config, troubleshooting, disclosures |

### P2 (stretch)

| ID | Requirement |
|---|---|
| P2.1 | Desktop transcript directive `::poster{id="..."}` showing poster cards for picks |
| P2.2 | Multiple Rokus by room name |
| P2.3 | Mood based picks using the session model via `ctx.llm` (only if cheap and reliable) |

## Non goals

- Netflix, Hulu, Max etc. deep links (no access to their content IDs).
- Chromecast and Google TV for the hackathon.
- Any content sourcing (downloads, `.strm` from pirate or debrid sources).
- A standalone web app outside Hermes.

## Success metrics

- Demo flow works 5 times in a row on real hardware.
- Fresh install to first play in under 5 minutes following the README.
- Catalog PR passes CI; no `dangerous` scan findings.
- Video under 90 seconds that clearly shows the TV starting by itself.

## Risks

| Risk | Mitigation |
|---|---|
| Deep link fails on our Roku/app version | Day one curl test; fallback: launch app, then `/input` deep link while running |
| Roku Network access not Permissive | Detect 403 style failures; README step; clear hint |
| SSDP blocked on the network | Manual IP setting |
| Jellyfin API differences across versions | Pin to the version we test on; note in README; use stable endpoints |
| No hardware for demo | Buy a Roku stick today |
| Catalog validation surprises | Run `doctor` and `validate` from Milestone 1, not at the end |
