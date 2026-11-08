# Hermes Screen: Hermes runs your home theater

Project brief for the Hermes Agent Plugin Hackathon (Nous Research).
Deadline: **Wed Nov 11, 2026, 5PM EST**.

---

## 1. The pitch

Ask Hermes what to watch from anywhere it runs (terminal, Telegram, Discord, Desktop). It looks through your own **Jellyfin** media library, knows what you've finished, what you're halfway through and what you've never touched, picks something that fits the moment, and starts it on your **Roku** TV. No remote, no scrolling.

It also handles the rest of movie night: pause and resume from your phone, "next episode," a Friday group vote in the family chat, and YouTube videos sent to the TV.

## 2. Why this version works

The first version tried to deep link into Netflix and other streaming apps. That breaks because those apps use private content IDs we can't get.

Jellyfin fixes that:

- The **official Jellyfin Roku app supports Roku deep links**. Send it a Jellyfin item ID plus a media type and it plays that exact item, both on launch and while already open. We verified this in the app's source (`source/MainEventHandlers.bs`, `onDeepLinkingEvent`).
- **We own the IDs.** The Jellyfin server API returns every item's ID, so we always know exactly what to send.
- **Watch history is free.** The Roku app reports playback progress to the Jellyfin server, so watched status, resume position and Next Up all come from the API. We don't have to guess what's on screen.
- **Zero competition.** The Hermes catalog has about 1,200 plugins and none for Jellyfin, Roku, or TV control (checked Nov 8, 2026).
- **Audience fit.** Self hosters run Jellyfin, and self hosters run Hermes on home servers and VPSes.

## 3. Why it's more than a prompt

Judges favor plugins that do more than a prompt or a skill could. This plugin:

1. Controls a real device on the local network (Roku ECP).
2. Queries a real library with real watch state (Jellyfin API).
3. Uses deep Hermes plugin surfaces: tools, slash commands with button pickers (`ctx.ask_choice`), an automation blueprint for movie night, durable plugin state, a Desktop settings form, and optionally Desktop poster cards in the transcript.

## 4. Core flows

1. **"We have 45 minutes, something funny."** Hermes filters the library by runtime, genre and watch history, shows 3 picks with one line reasons, and you tap one. The TV turns on and plays it.
2. **"Finish what I was watching."** Uses Jellyfin's resume data to continue where you left off.
3. **"Next episode of Severance."** Uses Next Up.
4. **"Pause the TV."** Roku ECP keypress, confirmed by reading device state.
5. **`/watch`** One tap picker in Telegram/Discord without spending a model turn.
6. **Movie night blueprint.** Every Friday at 7pm, Hermes posts 3 picks to the group chat and plays the winner.
7. **YouTube to TV.** "Put the fitted sheet folding video on the TV" deep links the YouTube Roku app.

## 5. Stack

- Python 3.11+, `httpx` with timeouts, `pytest` + `respx`, `ruff`.
- **Jellyfin server** REST API (API key or user token).
- **Roku ECP** over HTTP on port 8060, SSDP discovery.
- Hermes plugin: `plugin.yaml` + `__init__.py` with `register(ctx)`.

## 6. Demo setup

- Jellyfin server in Docker on a laptop.
- Library of legal content: Blender open movies (Big Buck Bunny, Sintel, Tears of Steel, Spring, Agent 327) and public domain films from the Internet Archive.
- Jellyfin app on the Roku, signed in.
- Roku: Settings > System > Advanced system settings > Control by mobile apps > Network access set to Permissive.

## 7. The one command that proves it

```bash
curl -d '' "http://ROKU_IP:8060/launch/JELLYFIN_CHANNEL_ID?contentId=JELLYFIN_ITEM_ID&mediaType=movie"
```

If that plays the movie, the project is viable.
