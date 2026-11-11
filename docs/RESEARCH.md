# RESEARCH

Facts we rely on, with a status. **Do not depend on anything `UNVERIFIED` without checking it first.** When you verify something, change the status and add the date and how you checked.

Statuses: `VERIFIED` (checked against docs, source or real device), `UNVERIFIED`, `FALSE` (checked and wrong; keep for history).

## Hermes plugin API

Source: `NousResearch/hermes-agent` repo, `website/docs/developer-guide/plugins/index.md` and `catalog-submission.md`, read 2026-11-08.

| Fact | Status | Notes |
|---|---|---|
| Plugin root has `plugin.yaml` + `__init__.py` exposing `register(ctx)` | VERIFIED | Dev guide steps 1 to 5 |
| User plugins live in `~/.hermes/plugins/<name>/` | VERIFIED | Dev guide step 1 |
| Manifest fields: `name`, `version`, `description`, `provides_tools`, `provides_hooks`, `requires_env`, `capabilities`, `config_schema`, `license`, `homepage`, `tags`, `manifest_version: 2`, `requires_hermes` | VERIFIED | Manifest v2 reference |
| `provides_tools` must exactly match registered tools or `validate` fails | VERIFIED | Dev guide + catalog rule 6 |
| `ctx.register_tool(name=, toolset=, schema=, handler=)` | VERIFIED | Step 5 |
| `ctx.register_command(name, handler, description=, args_hint=)` slash commands work in CLI and gateway (Telegram, Discord) | VERIFIED | "Register slash commands" |
| `ctx.ask_choice(question, choices)` shows buttons on Telegram/Discord/Slack, picker in CLI/Desktop; returns None in hooks, cron, async handlers | VERIFIED | "Ask the user to pick an option" |
| `ctx.dispatch_tool(name, args)` calls tools through normal approvals | VERIFIED | Step 5 |
| `ctx.get_config` / `ctx.set_config` (plugin namespace) and `ctx.state` (profile scoped, 10 MiB) | VERIFIED | "Store settings and runtime state" |
| `plugin_data_dir` / `plugin_db` from `plugins.plugin_storage` for durable data | VERIFIED | "Store durable state" |
| `config_schema` renders a Desktop settings form; type `secret` exists | VERIFIED | Manifest reference |
| `ctx.register_automation_blueprint(key, title, description, schedule_template, prompt_template, slots, ...)` | VERIFIED | "Add Automation Blueprints"; no capability needed |
| Hooks available: `pre_tool_call`, `post_tool_call`, `pre_llm_call`, `post_llm_call`, session hooks, `gateway_platform_event`, etc. | VERIFIED | Hook reference |
| Desktop plugins: `desktop/plugin.js` with `@hermes/plugin-sdk`; transcript directives `::name{key="value"}`; tool media renderers | VERIFIED | `desktop-plugin-sdk.md` |
| `hermes plugins doctor . --ci` and `hermes plugins validate . --install-deps` | VERIFIED | Dev guide + catalog page |
| Compatible `requires_hermes` source floor | VERIFIED (release + tooling) | `>=0.22.0` verified against upstream `v0.22.0` (`e06df9c2eae6901f4c88f464e0ae6e753c0428b8`); installed ZimaOS v0.16.0 reported 2026-11-09; below required floor |
| Exact secret read API name (`agent.secret_scope.get_secret`) and import path | VERIFIED (source + smoke) | Confirmed in `v0.22.0` and tested with scoped secret rotation |

## Catalog rules that affect us

Source: `plugin-catalog/README.md`, read 2026-11-08. Full text is mirrored in the catalog submission doc.

- PR adds **one** file `plugin-catalog/<name>.yaml` to `NousResearch/hermes-agent`, pinned to a **full 40 char SHA**, `version` quoted.
- Entry fields seen in existing entries: `name, title, repo, sha, description, maintainer, tier: community, category, requires_hermes, docs_url, version, platforms, capabilities {provides_tools, provides_hooks, provides_middleware, requires_env}`.
- Declared capabilities must match what's registered (rule 6).
- Security scan: `dangerous` fails; `caution` is reviewed (rule 7).
- Desktop code: no `eval`, no `new Function`, no dynamic imports beyond the SDK and React, no poking core markup (rule 8).
- No patching Hermes core (rule 9).
- Secrets only through Hermes, never `.env` or raw `os.environ` (rule 11).
- Respect approvals; anything waiting on a person must time out under cron/gateway (rule 12).
- Disclose network calls, shell use, background processes in README and PR (rule 13).
- `requires_hermes` must be a SemVer floor, declared in both `plugin.yaml` and the entry (rule 14).
- README at the pinned commit renders as the plugin's catalog page.

## Catalog landscape (2026-11-08)

- About 1,200 entries: tools 483, desktop 241, models 107, memory 84, general 70, automation 69, web 56, platform 55, voice 33.
- **Zero** entries mention Jellyfin, Roku, Chromecast, Kodi or TV control. Closest: `hermes-plex-music` (Plex music player in Desktop) and `homeassistant` (generic).

## Jellyfin Roku app

Source: `jellyfin/jellyfin-roku` main branch, cloned 2026-11-08.

| Fact | Status | Notes |
|---|---|---|
| App handles deep links at launch (`args.contentId`, `args.mediaType`) | VERIFIED (source) | `source/Main.bs` line ~103, `onDeepLinkingEvent(args)` |
| App handles deep links while running via `roInputEvent` (ECP `/input`) | VERIFIED (source) | `source/Main.bs` ~line 200 |
| Supported `mediaType` values (lowercased): episode, recording, movie, video, audio, audiobook, musicalbum, musicartist, series, season (season needs `seriesID`) | VERIFIED (source) | `source/MainEventHandlers.bs` `onDeepLinkingEvent` |
| `contentId` is the Jellyfin item ID | VERIFIED (source) | passed as `id` to quickplay |
| App reports `SupportsMediaControl: false` to the server | VERIFIED (source + live `/Sessions`, 2026-11-09) | `source/utils/deviceCapabilities.bs` + live Roku 3 session (`SupportsMediaControl: false`, `SupportsRemoteControl: false`) → server side remote control won't work; use ECP |
| App reports playback progress to the server | VERIFIED (source + live `/Sessions`, 2026-11-09) | `PlaystateTask` + live Roku 3 session reporting `NowPlayingItem.Id: "e5d6c471a8a4ea26e00a3694f91bf8d1"`, `PositionTicks: 840000000`, `IsPaused: false` |
| Deep link actually plays on our Roku + app version | UNVERIFIED | Day one curl test |
| Jellyfin channel ID on Roku | UNVERIFIED | Read from `/query/apps` |

## Roku ECP

| Fact | Status | Notes |
|---|---|---|
| HTTP on port 8060, no auth | UNVERIFIED (high confidence) | |
| `POST /launch/{appId}?contentId=..&mediaType=..` | VERIFIED (secondhand) | Roku deep linking sample repo `rokudev/deep-Linking-samples` |
| `POST /input?contentId=..&mediaType=..` deep links while app runs | VERIFIED (secondhand) | Same sample repo |
| SSDP discovery `ST: roku:ecp` on 239.255.255.250:1900 | UNVERIFIED (high confidence) | |
| `/query/apps`, `/query/active-app`, `/query/media-player`, `/query/device-info` | UNVERIFIED (high confidence) | |
| `POST /keypress/{Key}` (Home, Play, Back, Select, VolumeUp, VolumeDown, VolumeMute, PowerOn, PowerOff) | UNVERIFIED (high confidence) | Power keys only on Roku TVs |
| Control by mobile apps > Network access must be Permissive | UNVERIFIED | Confirm which commands fail on Default |
| YouTube channel ID 837, `contentId` = video ID | VERIFIED (secondhand) | `roku-api` npm docs example |

## Jellyfin server API

| Fact | Status | Notes |
|---|---|---|
| Auth via API key (Dashboard > API Keys) in `Authorization: MediaBrowser Token="..."` header (or `X-Emby-Token`) | VERIFIED (source + live Jellyfin 12.2.0, 2026-11-09) | Verified against `http://192.168.0.126:8097` via `library_status`, `library_pick`, and `/Sessions` |
| Items query with filters (`IncludeItemTypes`, `Genres`, `IsPlayed`, `SearchTerm`, `Recursive`, `Fields`) | VERIFIED (OpenAPI + live Jellyfin 12.2.0, 2026-11-09) | Verified `/Items` and `/Items/Counts` for user `homelab-hp` (`682764864adc45bbb6b981837f790812`) |
| Resume items and `/Shows/NextUp` | VERIFIED (OpenAPI + live Jellyfin 12.2.0, 2026-11-09) | Verified `/UserItems/Resume` and `/Shows/NextUp` during live `library_pick(max_minutes=20)` |
| `RunTimeTicks` in 100ns ticks | VERIFIED (OpenAPI + live Jellyfin 12.2.0, 2026-11-09) | Live `BigBuckBunny_320x180` reports `RunTimeTicks: 5964583330` (~9.94 min, rounded to 10 min) |
| `/Sessions` lists active clients and now playing | VERIFIED (OpenAPI + live Roku 3 playback, 2026-11-09) | Live Roku 3 (`192.168.0.104`) session reported `Client: "Jellyfin Roku"`, `ApplicationVersion: "3.2.4"`, `DeviceName: "Roku 3 (4200X)"`, `NowPlayingItem.Id: "e5d6c471a8a4ea26e00a3694f91bf8d1"`, `PositionTicks: 840000000` |
| `/System/Info/Public` for server name/version | VERIFIED (T3 response; user-confirmed HTTP 200 inside `hermes`, 2026-11-09) | `http://192.168.0.126:8097/System/Info/Public` returned HTTP 200: `{"LocalAddress":"http://[::1]:8096","ServerName":"terebi","Version":"12.2.0","ProductName":"Jellyfin Server","OperatingSystem":"","Id":"fb875353973d4c3fac1bc17ebfb7a3b1","StartupWizardCompleted":true}` |
| `.strm` files let library items point to URLs | VERIFIED (secondhand) | Works but playback may proxy through server; not used for demo |

## Open questions

1. Does `/input` deep link work while a video is already playing, or only on app screens?
2. Does Roku `/query/media-player` show position for the Jellyfin app?
3. Exact secret read API for plugins. (Resolved: `agent.secret_scope.get_secret`)
4. Can `ctx.ask_choice` be used from the blueprint flow, or does movie night need the model to collect votes?

## Carry-forward verification from pre-pivot work (2026-11-08)

The Jellyfin pivot changes the catalog and ID mapping, not the observed hardware
or upstream protocol constraints. See HARDWARE.md for user-reported probes.

- **VERIFIED (device output):** Roku 3 / 4200X at `192.168.0.104`, advertised OS
  15.3.4. Actual Hermes container on ZimaOS can reach TCP 8060 and read DIAL device
  description. DIAL discovery succeeded on host networking but timed out inside
  `hermes_default`; ECP SSDP discovery has not been tested.
- **VERIFIED (device output):** YouTube DIAL app-status GET returned 403, origin
  denied. This does not establish Jellyfin launch behavior or ECP permissions.
- **VERIFIED (docs, earlier inspection):** official
  [Roku ECP docs](https://developer.roku.com/dev/docs/external-control-api) say
  “ECP commands may not be sent from 3rd-party platforms (for example, mobile
  applications).” Retrieved via Jina text proxy after direct HTTP 403 responses.
  They also say Search was removed in OS 12.0 and describe “Enabled” mobile-control
  settings for OS 14.1 commands. **UNRESOLVED:** shipping applicability/exception
  for this proposed plugin. Receiver source support does not resolve this.
- **VERIFIED (Hermes docs):** at upstream SHA
  `edd08bb415530db46956e881e4084b0e0a43c6a2`, plugin guide documents JSON-string
  handlers accepting `(args, **kwargs)`, injected stable `conversation_id` versus
  rotating `session_id`, and profile-owned state. Use trusted requester/profile
  context for choices and expire text fallbacks. Installed-version compatibility
  and precise secret import still require code/runtime checks as listed above.

Preserve the current Jellyfin scope; the old Chromecast fallback and local watcher
are not carried forward. Exact-title claims require title evidence, not just a
successful request or generic playing state. `/Sessions` corroboration becomes
necessary for a machine-verified item when Roku telemetry cannot identify it.

## Integration source verification (2026-11-08)

Fetched `https://api.jellyfin.org/openapi/jellyfin-openapi-stable.json`:
`info.version=12.4.0`, SHA256
`02a6064916b7e08f1f1d8d7ffc1fb1c7623df0e378729fcd7fd353766868036e`.
Verified GET paths and query parameters for `/System/Info/Public`, `/Users`,
`/Users/{userId}`, `/Items`, `/Items/{itemId}`, `/Items/Counts`,
`/UserItems/Resume`, `/Shows/NextUp`, and `/Sessions`. Note that the ZimaOS
server (`http://192.168.0.126:8097`) reports Jellyfin `12.2.0`; authenticated
endpoints were verified against that live server on 2026-11-09 (see below).

Fetched Jellyfin `AuthorizationContext.cs` at
`83d0d0e7f76e23e2e085c8ff67d28b772d35967d`: Authorization/MediaBrowser Token
parsing confirmed. Fetched Roku `source/api/baserequest.bs` at
`a7b786d0595f741849aab7eb5c558f674274abc7`: client `Jellyfin Roku`, device
`<name> (<model>)` and token header confirmed.

Official Hermes `v0.22.0` `hermes_cli/plugins_loader.py` loads directory plugins as
`hermes_plugins.<slug>` packages with explicit submodule search locations.
Relative imports passed that actual loader from outside the repository, for both
source and installed wheel. `get_config` reads plugin settings in the active
profile; secrets use `agent.secret_scope.get_secret`. Full evidence and commands
are in [INTEGRATION.md](INTEGRATION.md).

## Separate-runtime confirmation — 2026-11-09

User confirmed public Jellyfin reachability from the actual `hermes` container and
installed Hermes v0.16.0. Reused a separate official v0.22.0 checkout/venv with a
fresh isolated HERMES_HOME; doctor, validate and mocked loader invocation pass for
plugin `9320c3638d9f7d8579326e1a622a205523b395d1`. Validation includes one
non-blocking `context_exfil` caution on documentation (`HARDWARE.md:4`). No product
code changed and the existing ZimaOS installation was not modified. See INTEGRATION.md.

## Picker integration evidence — 2026-11-09

VERIFIED (source + mocked real client): `pick_titles(client, max_minutes, limit=3)`
uses the existing JellyfinClient; resume precedes Next Up, then explicitly
unwatched Movies/Videos, with deterministic ties and at most three results.
The runtime float reaches raw-tick filtering unchanged. Next Up uses remaining
runtime, not full runtime; one tick beyond the limit is rejected. Unknown runtime
cannot fit; missing Played does not imply unwatched. Reasons cite returned fields,
not genre affinity or invented history. Errors and scan truncation stay visible.
All new API checks use respx, not live hardware. See D-011 and INTEGRATION.md.

The historical documentation caution came from the upstream `skills_guard.py`
`context_exfil` pattern. The snapshot's one-word provenance clarification retains
evidence and uses “thread”; no scanner configuration was changed or suppressed.
The integrated-tree validation result is recorded separately in INTEGRATION.md.

## Live Jellyfin 12.2.0 and Roku 3 `/Sessions` verification — 2026-11-09

- **VERIFIED (live Jellyfin 12.2.0 + Hermes v0.22.0 loader):** At SHA
  `22d28304f787c339b20e137975193d91e88d8e89`, `library_status` and
  `library_pick(max_minutes=20)` were invoked through the official Hermes `v0.22.0`
  loader against `http://192.168.0.126:8097` using `agent.secret_scope.get_secret`.
  Resolved user `homelab-hp` (`682764864adc45bbb6b981837f790812`) and returned
  `BigBuckBunny_320x180` (`e5d6c471a8a4ea26e00a3694f91bf8d1`, 10 min Movie,
  `source: "unwatched"`).
- **VERIFIED (live Roku 3 playback + `/Sessions`):** When signed in via Quick Connect
  and playing `BigBuckBunny_320x180` on Roku 3 (`192.168.0.104`), `Jellyfin Roku`
  `3.2.4` creates two sessions in `/Sessions`: an initial idle session with
  `DeviceId: "3ed2ceba-4c54-56fe-a896-e40e3d810aac"` (`LastPlaybackCheckIn: "0001-01-01T00:00:00.0000000Z"`, `NowPlayingItem: null`)
  and an active playback session with `DeviceId: "3ed2ceba-4c54-56fe-a896-e40e3d810aachomelab-hp"`
  (appending the username to the UUID), `DeviceName: "Roku 3 (4200X)"`,
  `SupportsMediaControl: false`, `SupportsRemoteControl: false`, and
  `NowPlayingItem.Id: "e5d6c471a8a4ea26e00a3694f91bf8d1"`.
  `JellyfinClient.verify_playback` filters out the epoch-checkin session and
  uniquely verifies the active playing session (`verified: true`, `playing: true`,
  `paused: false`, `matched_sessions: 1`).

## Roku 3 control path evaluation and Chromecast assessment — 2026-11-09

- **VERIFIED (source + live `/Sessions` + Roku docs):** There is no documented,
  policy-clear path for a third-party platform/plugin to start and pause Jellyfin on
  the Roku 3 without relying on Roku ECP:
  1. **Jellyfin `/Sessions/{id}/Playing` remote control:** Unsupported by `Jellyfin Roku`
     `3.2.4` (`SupportsMediaControl: false`, `SupportsRemoteControl: false`,
     `SupportedCommands: []` in both `source/utils/deviceCapabilities.bs` and live
     `/Sessions`).
  2. **Roku DIAL (`:8060/dial`):** Not supported by the official `jellyfin-roku`
     channel, and DIAL does not provide post-launch transport/pause control.
  3. **Roku ECP (`:8060/launch`, `:8060/input`, `:8060/keypress`):** `jellyfin-roku`
     `3.2.4` implements startup deep links (`onDeepLinkingEvent`), running-app
     deep links (`roInputEvent`), and voice transport commands (`VoiceInputTask`
     with `enableTransportEvents()` handling `type=transport&command=pause|play`
     in `v3.2.1+`). However, official [Roku ECP docs](https://developer.roku.com/dev/docs/external-control-api)
     explicitly state: *"In addition, ECP commands may not be sent from 3rd-party
     platforms (for example, mobile applications)."* Therefore, the Roku 3 control
     path remains blocked by Roku's third-party platform restriction, and no ECP
     launch or pause commands were sent to `192.168.0.104`.
- **Chromecast next-target assessment:**
  - **Chromecast with Google TV (running the Jellyfin Android TV app):** When the
    Jellyfin app is open and connected, its Jellyfin session reports
    `SupportsMediaControl: true`, enabling server-side `/Sessions/{id}/Playing` and
    `/Sessions/{id}/Playing/Pause` with native `/Sessions` item ID and `IsPaused`
    verification; however, Jellyfin server API alone cannot wake or launch the app
    from an idle screen without Cast or ADB/CEC.
  - **Direct Google Cast (`pychromecast` over TCP `8009`):** Can wake/launch the
    Default Media Receiver (`CC1AD845`) from idle over plain LAN HTTP (unlike the
    official Jellyfin Cast Web Receiver, which requires HTTPS/DNS) and play/pause a
    Jellyfin stream URL (`media_controller.play_media` / `media_controller.pause`).
    Requires: (a) user identification of the Chromecast LAN IP and model (since mDNS
    multicast does not cross the `hermes_default` Docker bridge), (b) dependency
    approval for `pychromecast` in `DECISIONS.md` and `hermes plugins validate`, and
    (c) handling the distinction between Cast `media_controller.status` telemetry
    and Jellyfin `/Sessions` state if the Default Media Receiver is used instead of
    a full Jellyfin client session.

## Chromecast Gen 2 direct Cast evidence — 2026-11-10

- **VERIFIED (user + live device):** Authorized Gen 2 `192.168.0.134`, name `Den TV`,
  Cast firmware `1.56.467165`, build `467165`; direct TCP 8009 and 8008 reachable
  from T3 container `172.23.0.2`. Initial receiver was Backdrop (`E8C28D3C`),
  `is_stand_by: true`, `is_active_input: null`. No multicast discovery was used.
- **VERIFIED (failed first attempt):** A temporary MP4 at container IP `172.23.0.2`
  yielded exact-URL `IDLE` but no `PLAYING` within 40s and no receiver HTTP fetch.
  Outbound Cast connectivity alone did not establish inbound media reachability.
- **VERIFIED (live retry after host forwarding):** Serving only the temporary MP4
  on `0.0.0.0:8765`, with the user's exact LAN URL
  `http://192.168.0.126:8765/BigBuckBunny_320x180.mp4`, yielded fresh `PLAYING`
  at 00:31:20.171 UTC, then `PAUSED` at 00:31:23.217, position 2.451218 seconds.
  Both reports matched the exact URL and media session `1`. Receiver app:
  Default Media Receiver `CC1AD845`. HTTP range GETs returned 206; observed peer
  `172.23.0.3` is the forwarding path, not the Chromecast's own IP.
- **UNVERIFIED:** TV/CEC wake, human confirmation of pause, mDNS discovery, execution
  inside actual `hermes`, and Jellyfin history/session reporting through this receiver.
  `is_stand_by` remained true during playback and cannot prove TV power state.
- **VERIFIED (cleanup):** Test receiver quit; HTTP server stopped and local TCP 8765
  refused connections; temporary MP4 deleted. Host forwarding may still accept TCP,
  but its HTTP endpoint no longer serves the media. No library credentials or
  directory listings were exposed. The plugin and its dependencies are unchanged.

Full method, artifact hash, timestamps and limits are in [HARDWARE.md](HARDWARE.md#chromecast-gen-2-direct-cast-attempt--2026-11-10).

- **VERIFIED (repeat + human observation, 2026-11-10):** Same exact-URL test repeated
  from idle at 00:35 UTC. User replied “yes i see it” during playback. Receiver
  subsequently confirmed `PAUSED` at 14.462817s in the same media session; paused
  frame held for 15s before cleanup. Human-visible playback is confirmed; physical
  wake and human confirmation of pause remain unverified. Endpoint/copy removed.

## Jellyfin cast-source and authenticated byte-range stream verification — 2026-11-10

- **VERIFIED (live Jellyfin 12.2.0 + isolated Hermes v0.22.0 runtime):**
  - `GET /Items/e5d6c471a8a4ea26e00a3694f91bf8d1?userId=682764864adc45bbb6b981837f790812`
    returns `MediaSources[0]` with `Id: "e5d6c471a8a4ea26e00a3694f91bf8d1"`,
    `Container: "mp4"`, `Protocol: "File"`, `IsRemote: false`, `Size: 64657027`,
    `RunTimeTicks: 5964583330`, stream 0 `Video` (`Codec: "h264"`, `320x180`), and
    stream 1 `Audio` (`Codec: "aac"`, 2ch, `48000` Hz).
    `JellyfinClient.get_cast_source("e5d6c471a8a4ea26e00a3694f91bf8d1")` validates
    and normalizes this record without exposing filesystem paths.
  - `GET /Videos/e5d6c471a8a4ea26e00a3694f91bf8d1/stream?static=true&mediaSourceId=e5d6c471a8a4ea26e00a3694f91bf8d1`
    with `Authorization: MediaBrowser ...` supports both `HEAD` (`200 OK`,
    `content-type: video/mp4`, `accept-ranges: bytes`, `content-length: 64657027`)
    and `Range: bytes=0-1023` (`206 Partial Content`,
    `content-range: bytes 0-1023/64657027`, `content-length: 1024`, MP4 box signature
    `ftypisom`).
  - Official `hermes plugins validate --install-deps` on the 4-tool tree (`library_status`,
    `library_pick`, `tv_play`, `tv_pause`) passes with `security scan — caution` for
    `bind_all_interfaces` (`playback.py:77`, `plugin.yaml:50`, `relay.py:158`,
    `relay.py:166`) because containerized deployments may bind `0.0.0.0:8765`.
  - **VERIFIED (live Chromecast Gen 2 `192.168.0.134`, firmware `1.56.467165`, `2026-11-10`):**
    1. **Sender disconnect vs receiver app lifetime (`CC1AD845`):** `pychromecast`'s
       `SocketClient._cleanup()` sends `{"type": "CLOSE"}` on
       `urn:x-cast:com.google.cast.tp.connection` for every channel in
       `self._open_channels` (including `CC1AD845`'s `transport_id`). When `CC1AD845`
       on Chromecast Gen 2 receives an explicit `CLOSE` message from its last connected
       sender, it immediately exits (`app_id` becomes `None`). Clearing
       `socket_client._open_channels` before `cast.disconnect(timeout=2.0)` closes the
       TCP control socket cleanly without sending `CLOSE` to `transport_id`, keeping
       `CC1AD845` playing across separate tool calls (`tv_play` -> `tv_pause`).
    2. **Outgoing session `IDLE`/`INTERRUPTED` on `LOAD`:** When `LOAD` replaces an
       existing media session on `CC1AD845`, the receiver first emits a `MEDIA_STATUS`
       for the outgoing `mediaSessionId` with `playerState: "IDLE"`,
       `idleReason: "INTERRUPTED"`, and `extendedStatus.media.contentId` already set to
       the newly loaded capability URL, followed milliseconds later by `BUFFERING` and
       `PLAYING` on the new `mediaSessionId`. Ignoring `IDLE`/`INTERRUPTED` before
       `BUFFERING` or `PLAYING` is observed prevents false failure reports on `LOAD`.
    3. **End-to-end Hermes `v0.22.0` live acceptance (`01:43:22Z–01:43:32Z` UTC):**
       `library_status` -> `library_pick(max_minutes=20)` (`BigBuckBunny_320x180`,
       `e5d6c471a8a4ea26e00a3694f91bf8d1`) -> `tv_play` (`verified: true`,
       `state: "playing"`, `action: "started"`, `position_s: 0.0`,
       `duration_s: 596.5`, `relay_expires_in_minutes: 25`) -> `tv_pause` after 5.0s
       (`verified: true`, `state: "paused"`, `already_paused: false`,
       `position_s: 4.7`) -> idempotent repeat `tv_pause` (`already_paused: true`,
       `position_s: 4.7`) -> `on_unload` cleanup (`relay_port_8765_closed: true`).

## Scene subtitle source verification — 2026-11-10

- **VERIFIED (OpenAPI 12.4.0 + source v12.4):** text subtitle route is
  `GET /Videos/{itemId}/{mediaSourceId}/Subtitles/{index}/Stream.{srt|vtt}`.
  Stream index is looked up in the specified source. Default start position is
  zero, preserving original cue timestamps. Item metadata lists source-specific
  subtitle streams. Sources were checked at
  `83d0d0e7f76e23e2e085c8ff67d28b772d35967d` by the Claude resolver worker.
  Its downloaded stable OpenAPI hash matches the existing `02a60649…6036e` snapshot.
- **VERIFIED (mocked fixtures):** SRT/WebVTT parsing, timestamped dialogue across
  neighboring cues, repeated lines, exact source/track selection, local cache
  refresh and structured errors. Full track text stays local; compact matching
  excerpts can appear in chat and therefore reach the user's model provider.
- **UNVERIFIED (live):** Jellyfin 12.2 subtitle extraction/conversion and ETag
  behavior. Big Buck Bunny has no dialogue; its acceptance uses a manual marker.
- No real embedding model is approved or enabled. Fake-embedder tests establish
  only the injectable interface, not semantic paraphrase quality.


## Scene timestamp playback verification — 2026-11-10

- **VERIFIED (source + mocked receiver):** pychromecast 14.1.1 LOAD supports
  `current_time`; Cast SEEK uses `currentTime` and `resumeState: PLAYBACK_START`.
  Explicit offsets on an owned running/paused edition seek and start playback;
  no-offset ordinary play/pause behavior remains covered by regression tests.
- **VERIFIED (mocked receiver):** exact URL/state alone does not verify a scene.
  Fresh measured receiver position must be in [target − 3s, target + elapsed + 3s].
  Missing, nonfinite or incorrect positions remain unverified. Explicit source
  selection cannot silently fall back to another file. Multi-edition sources
  without a source runtime cannot use another edition's item-level runtime.
- **VERIFIED (live feature branch):** Telegram manual-marker fresh LOAD at 60.0s,
  receiver-confirmed PLAYING then PAUSED at 73.071335s, same exact content/session,
  runtime SHA `ff27aaf111f12c5a02e4b821d0b88276bc168367`. Existing-session SEEK
  remains mocked-test verified only; live subtitle extraction remains unverified.
- **VERIFIED (v0.22.0 source + live kwargs audit + dispatcher regression):** this
  release injects `session_id`, not `conversation_id`, into registry handlers.
  Final code prefers conversation ID when available, otherwise trusted session ID,
  rejects missing host context, and invalidates choices across session changes.
  This adapter correction was made after the recorded live hardware run.

- **VERIFIED (live exact final code, 2026-11-10 18:20–18:21 UTC):** runtime
  `37582aea9f2a3bfba66c1ac116b78eb03f138be7`, real Hermes v0.22.0 Telegram
  `library_scene_find` → `tv_scene_play` → `tv_pause`, trusted session scope.
  Existing manual marker for the exact Big Buck Bunny source loaded at 60.0s;
  receiver PLAYING 60.0s then PAUSED 74.652622s, same media session/content hash.
  Relay served HTTP 206 and was released after verified pause; TCP 8765 closed.
  This closes the final adapter's prior live-code gap. Evidence:
  [scene-marker-37582ae-20261110.json](evidence/scene-marker-37582ae-20261110.json).


## Saved-description demo (2026-11-10)

- **VERIFIED (worker fixtures):** pure local description lookup scopes records to
  exact item, media source and fingerprint, preserves inputs, and distinguishes
  supported paraphrases, ambiguous descriptions, and no match. This is lexical
  normalization with a fixed vocabulary and aliases, not semantic-model quality.
- **BLOCKED (live scene data):** manager's new Jellyfin metadata request for
  `BigBuckBunny_320x180` returned HTTP 401. No action-start timestamps were viewed
  or inferred. The user was asked for three verified times for this exact copy.
- **UNVERIFIED (live Telegram):** paraphrase to described marker to exact-edition
  receiver PLAYING, and ambiguous/unmatched agent requests causing no playback.
  Previous marker acceptance on PR #4 is not evidence for this new demo flow.


## Terebi Games hosting/displays — 2026-11-11

- Google registration docs verified: Custom Web Receiver requires an app ID;
  unpublished testing requires registered Cast device. Development receiver URL
  may use LAN HTTP; published receiver requires HTTPS. No such app/device setup
  exists for this user. Manual Mac Chrome mirroring selected, not yet proven.
  https://developers.google.com/cast/docs/registration
- Camera getUserMedia requires a secure context and explicit permission; LAN
  plain HTTP does not qualify. Request video only and release every track.
  https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia
- Host probe: `http://192.168.0.126/` responds 200 with Server: Caddy;
  `https://192.168.0.126/` refuses connection. Repo has no proxy deployment config.
  Internal host configuration has not been inspected from this T3 container.
- Cloudflare Quick Tunnel docs verified: temporary trycloudflare.com hostname,
  no account/domain needed, URL changes each start, no uptime guarantee, up to
  200 in-flight requests and no SSE. Use bounded short polling for the game.
  https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/


### RPS iPhone live debug — 2026-11-11

- **VERIFIED (manager HTTPS requests):** deployed service health and admin session
  creation return HTTP 200; returned links use the configured public origin.
  Player, display, local model, JS and WASM return HTTP 200 with usable MIME types.
- **VERIFIED (gateway log):** isolated @terebitvbot connected at 02:20:37 UTC on
  `0e17940`, with the game tool preflight successful and plugin origins checked.
- **USER OBSERVED:** iPhone Safari shows the camera preview, but recognized no
  rock/paper/scissors. This does not isolate model initialization, inference,
  confidence or sampling as the cause.
- **UNVERIFIED:** each real iPhone gesture, round sampling, physical Den TV state,
  three camera rounds, missed-hand retry and Stop indicator. Temporary local
  practice diagnostics added to investigate; no model substitution made.


- **USER OBSERVED (RPS follow-up):** practice recognizes gestures, but a live round
  reports a last-moment hand change. Successful camera-round acceptance remains
  unverified. **VERIFIED (source):** old round selection included pre-Shoot
  predictions and a whole-window majority. New post-Shoot suffix logic has fixture
  tests; actual iPhone timing and all-three-gesture rounds remain UNVERIFIED.


### Custom game receiver — 2026-11-11

- VERIFIED (official Google registration guide, fetched 2026-11-11): unpublished
  Custom Receiver testing requires device registration. Add New Device by serial,
  wait roughly 15 minutes for Ready for Testing and restart the Chromecast.
  Add New Application -> Custom Receiver -> URL -> Save gives the app ID.
  Developer account fee is non-refundable US$5. Source:
  `https://developers.google.com/cast/docs/registration`.
- VERIFIED (official CAF API reference): customNamespaces must be declared before
  start; addCustomMessageListener/sendCustomMessage support sender-specific JSON
  messages. disableIdleTimeout is documented for non-media apps. skipPlayersLoad
  avoids media player loading. Sources:
  `https://developers.google.com/cast/docs/reference/web_receiver/cast.framework.CastReceiverOptions`
  and `https://developers.google.com/cast/docs/reference/web_receiver/cast.framework.CastReceiverContext`.
- VERIFIED (installed pychromecast 14.1.1 source): BaseController supports the
  namespace and no_add_request_id; Chromecast.start_app accepts a timeout.
  Existing direct connection uses explicit cast type; existing close clears
  virtual channels before disconnect to avoid stopping the receiver.
- UNVERIFIED (Den TV hardware): Custom Receiver registration, CAF runtime and
  SDK CSP/hosting on Gen 2, matching render acknowledgement, persistence after
  sender disconnect/Mac closed, game round, TV wake/input and subsequent movie
  playback. User must complete registration and deploy the receiver build first.


## YouTube Cast spike — 2026-11-11

- VERIFIED installed source: PyChromecast **14.1.1**, `controllers/youtube.py`:
  `YouTubeController.play_video` uses `TimeoutYouTubeSession`; media controller
  provides playback state/pause. Upstream source checked at
  https://github.com/home-assistant-libs/pychromecast/blob/14.1.1/pychromecast/controllers/youtube.py .
- VERIFIED source: casttube's play path exchanges MDX/lounge control requests;
  queue HTML parsing is a separate unused helper. No media URL extraction required.
- VERIFIED hardware/API: Den TV Gen 2 `192.168.0.134`, public video `aqz-KE-bpKQ`.
  YouTube app `233637DE`; exact content ID BUFFERING then PLAYING at 17.661 seconds
  after connection, official Blender title, position 1.114 seconds. A subsequent
  direct pause confirmed PAUSED at 27.368 seconds, same session `1712781726`.
  Evidence in `docs/evidence/youtube-direct-spike-20261111.json`.
- UNVERIFIED physical: user observation of this video, Mac-mirroring state, Telegram
  link test, title search with a real key, post-YouTube Jellyfin/movie and game launch.
- VERIFIED current official docs fetched: search.list supports `part=snippet`,
  `type=video`, `maxResults`, `q`, `safeSearch` and returns video IDs/title/channel.
  https://developers.google.com/youtube/v3/docs/search/list . Search is optional;
  video availability/age/region restrictions remain a receiver/live observation.

## RPS Frutiger Aero renderer — 2026-11-11

- VERIFIED (headless Chrome 156, SwiftShader, 1280×720, real local game service):
  Waiting, Phone connected, Ready, 3-2-1, Shoot, Try again, Reveal and Next round
  render from live API state; no CSP violations under the receiver's
  `style-src 'self'` policy model (no inline styles); WebGL hands report `3D`;
  `#motion=still` reports `Static` with the same text, moves and scores.
  Screenshots and a recording: `docs/evidence/rps-aero/`.
- VERIFIED (same harness): the restyled phone page pairs, starts the camera with a
  fake device, loads the on-device recognizer and shows practice status.
- **UNVERIFIED (Den TV Chromecast Gen 2):** frame rate of the ambient loops, WebGL 1
  availability and antialiasing, whether the 20 fps probe trips to the still scene,
  font rendering, and audio continuity alongside the animation. The receiver has
  not been loaded on the device with this build.
- **UNVERIFIED (real iPhone Safari):** the restyled controller's look and tap
  targets on the device; camera behaviour is unchanged code but not re-observed.

## RPS polish pass — 2026-11-11

- VERIFIED (user, Den TV, commit `7cf12ac`): the redesign runs on the Chromecast
  Gen 2 receiver; animations and 3D hands looked rough. Which render mode the TV
  showed was not recorded for that run.
- VERIFIED (deployed tunnel origin, 2026-11-11 ~16:10Z): every display, receiver
  and phone file served matched `7cf12ac` byte for byte.
- VERIFIED (T3 → LAN, 2026-11-11 16:10Z–16:55Z): `192.168.0.134` ports 8008, 8009
  and 9222 closed and no other host answered on 8009, while `192.168.0.126` was
  reachable. The Chromecast was off, so nothing in this pass was profiled on it.
- VERIFIED (headless Chrome 156, software GL, traced): reveal-start stall is a GPU
  task (`GLContextEGL::MakeCurrent`) of 0.6–3 s on the first WebGL frame after
  idling; with a 400 ms keep-alive frame and pre-reveal priming the first real turn
  measured 34 frames, mean 37 ms, worst 112 ms. Ambient, pairing and countdown
  windows held 17 ms frames. Software GL timings do not predict the Chromecast.
- VERIFIED (same, frame-stepped capture of the real page against the real service
  with a controlled clock): Waiting → Phone connected → Ready → 3-2-1-Shoot →
  Reveal renders in the intended order at every frame. Clips in
  `docs/evidence/rps-aero/`.
- **UNVERIFIED (Den TV Chromecast Gen 2):** everything about this pass on the
  device: frame timing per phase, which level and turn style it settles on, whether
  the cold-start stall exists there, hand antialiasing, and a real camera round.
  Read it from the footer and from `display_profile` rows after a round.
