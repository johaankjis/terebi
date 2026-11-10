# Hardware evidence carried forward

Reviewed against base `4fd89d1b0cad82284f960be146bab444cfc9ff13` on 2026-11-08.
Source: user-reported command output in the manager thread, also retained
in `stash@{0}^3:docs/HARDWARE.md`. This is evidence, not a claim of working playback.

## Confirmed target and runtime

- Authorized device: Roku 3, model 4200X, `192.168.0.104`.
- Advertised OS: 15.3.4. Device serial omitted as unnecessary.
- `192.168.0.209` is the router, not an authorized TV target.
- Hermes host: ZimaOS `192.168.0.126`, Docker container `hermes`.
- User ran `docker inspect hermes --format 'status={{.State.Status}} network={{.HostConfig.NetworkMode}}'`:
  `status=running network=hermes_default`. Network driver not established.

## Completed read-only probes

1. Inside `hermes`, TCP connect to Roku port 8060 succeeded within a 5s timeout.
   No ECP request was sent. DIAL SSDP (MX 2, TTL 2, 5s window) received no Roku reply.
2. Same DIAL discovery from a temporary container using the local Hermes image and
   host networking returned HTTP 200, `ST: urn:dial-multiscreen-org:service:dial:1`,
   `Server: Roku/15.3.4 UPnP/1.0 Roku/15.3.4`, and
   `LOCATION: http://192.168.0.104:8060/dial/dd.xml`.
3. Inside `hermes`, `GET /dial/dd.xml` returned HTTP 200 and
   `Application-URL: http://192.168.0.104:8060/dial`. XML identified Roku 3 / 4200X.
   `GET /dial/YouTube` returned HTTP 403, `Origin  is not allowed access.`

These results establish direct reachability and a difference in discovery outcomes
between network paths, not the precise cause. DIAL discovery is not the `roku:ecp`
SSDP query planned for the new client. YouTube DIAL rejection says nothing about
whether the Jellyfin deep-link handler works. Do not replace these findings with
blanket network-failure or playback-success claims.

## Jellyfin proof still required (manager only, sequential)

- **Jellyfin server on ZimaOS (`http://192.168.0.126:8097`):**
  - From the T3 workspace container (`172.23.0.2`), `GET http://192.168.0.126:8097/System/Info/Public` returned HTTP 200 (`Server: Kestrel`):
    `{"LocalAddress":"http://[::1]:8096","ServerName":"terebi","Version":"12.2.0","ProductName":"Jellyfin Server","OperatingSystem":"","Id":"fb875353973d4c3fac1bc17ebfb7a3b1","StartupWizardCompleted":true}`.
  - On 2026-11-09 the user confirmed `/System/Info/Public` returns HTTP 200 from inside `hermes` (`hermes_default`) and reported installed Hermes v0.16.0. This T3 container still has no Docker socket or SSH credentials for ZimaOS.
  - On 2026-11-09 authenticated `library_status` and `library_pick(max_minutes=20)` were verified against live `http://192.168.0.126:8097` from the isolated Hermes `v0.22.0` runtime using `agent.secret_scope.get_secret("JELLYFIN_API_KEY")` (secret read into memory only, never persisted to disk):
    - Resolved single enabled user `homelab-hp` (`id: "682764864adc45bbb6b981837f790812"`).
    - `library_status({})` returned `{"ok": true, "server": {"name": "terebi", "version": "12.2.0"}, "user": {"id": "682764864adc45bbb6b981837f790812", "name": "homelab-hp"}, "counts": {"movies": 1, "series": 0, "episodes": 0}}`.
    - `library_pick({"max_minutes": 20})` returned `BigBuckBunny_320x180` (`item_id: "e5d6c471a8a4ea26e00a3694f91bf8d1"`, `type: "Movie"`, `year: 2008`, `minutes: 10`, `source: "unwatched"`, `why: "Not watched yet in Jellyfin: BigBuckBunny_320x180, about 10 min, within your 20 min."`, `complete: true`, `truncated: false`, `errors: []`).
- **Roku 3 (`192.168.0.104`) Quick Connect sign-in, manual playback, and live `/Sessions` verification (2026-11-09):**
  - User signed in on the Roku 3 (`192.168.0.104`) via Quick Connect and started playing `BigBuckBunny_320x180` with the Roku remote.
  - Live `GET http://192.168.0.126:8097/Sessions` confirmed two Roku sessions for `RemoteEndPoint: "192.168.0.104"`:
    1. Active playback session `Id: "452bc61a34030e5b3dd86d07521d91f4"`:
       - `Client: "Jellyfin Roku"`, `ApplicationVersion: "3.2.4"`, `DeviceName: "Roku 3 (4200X)"`, `DeviceId: "3ed2ceba-4c54-56fe-a896-e40e3d810aachomelab-hp"`, `UserId: "682764864adc45bbb6b981837f790812"`, `UserName: "homelab-hp"`, `IsActive: true`.
       - `SupportsMediaControl: false`, `SupportsRemoteControl: false`.
       - `NowPlayingItem`: `{"Id": "e5d6c471a8a4ea26e00a3694f91bf8d1", "Name": "BigBuckBunny_320x180", "Type": "Movie", "RunTimeTicks": 5964583330}`.
       - `PlayState`: `{"PositionTicks": 840000000, "CanSeek": false, "IsPaused": false, "IsMuted": false, "PlayMethod": "DirectPlay"}`.
    2. Initial pre-playback session `Id: "a3e03070203e28b7c4b11b2556384362"` (`DeviceId: "3ed2ceba-4c54-56fe-a896-e40e3d810aac"`, `NowPlayingItem: null`, `LastPlaybackCheckIn: "0001-01-01T00:00:00.0000000Z"`).
  - Live `JellyfinClient.verify_playback("e5d6c471a8a4ea26e00a3694f91bf8d1", ...)` passed for both `device_name="Roku 3 (4200X)"` and `device_id="3ed2ceba-4c54-56fe-a896-e40e3d810aachomelab-hp"`, automatically filtering out the stale epoch-checkin session and returning:
    `{"ok": true, "verified": true, "reason": null, "item_id": "e5d6c471a8a4ea26e00a3694f91bf8d1", "now_playing": {"item_id": "e5d6c471a8a4ea26e00a3694f91bf8d1", "title": "BigBuckBunny_320x180"}, "paused": false, "playing": true, "position_s": 84, "session": {"device_name": "Roku 3 (4200X)", "client": "Jellyfin Roku", "user_name": "homelab-hp", "check_in_age_s": 4}, "matched_sessions": 1}`.

## Roku 3 control path evaluation and Chromecast assessment (2026-11-09)

1. **Jellyfin Server-Side Remote Control (`/Sessions/{id}/Playing`):**
   - **Blocked by client capabilities:** Live `/Sessions` on `Jellyfin Roku` `3.2.4` reports `SupportsMediaControl: false`, `SupportsRemoteControl: false`, and `SupportedCommands: []` (matching `source/utils/deviceCapabilities.bs` in `jellyfin/jellyfin-roku`). The official Roku channel does not listen for Jellyfin WebSocket remote-control commands, so server-side `/Sessions/{id}/Playing` cannot launch or pause playback on the Roku 3.
2. **Roku DIAL (`http://192.168.0.104:8060/dial`):**
   - **Unsupported for Jellyfin launch and pause:** The official `jellyfin/jellyfin-roku` channel is not a registered DIAL receiver, and the DIAL protocol does not standardize post-launch pause/transport controls (plus earlier `GET /dial/YouTube` returned HTTP 403 `Origin is not allowed access`).
3. **Roku External Control Protocol (ECP, port `8060`):**
   - **Technically implemented in receiver source:** `jellyfin/jellyfin-roku` (`v3.2.4`) handles ECP deep links at startup (`POST /launch/<channelId>?contentId=<itemId>&mediaType=<type>` via `Main(args)` -> `onDeepLinkingEvent(args)`) and while running (`POST /input?contentId=<itemId>&mediaType=<type>` via `roInputEvent`), as well as `roInput` transport events (`POST /input/<channelId>?type=transport&command=pause&id=1` via `VoiceInputTask` added in `v3.2.1`) and remote keypresses (`POST /keypress/Play` when `Settings > System > Advanced system settings > Control by mobile apps` is set to `Permissive` / `Enabled`).
   - **Blocked by Roku's third-party platform policy:** Official [Roku ECP documentation](https://developer.roku.com/dev/docs/external-control-api) states: *"In addition, ECP commands may not be sent from 3rd-party platforms (for example, mobile applications)."* Because no documented exception establishes that a third-party agent plugin may ship unauthenticated ECP control commands, no ECP launch or pause requests were sent to `192.168.0.104:8060`.
4. **Chromecast assessment as the next playback target:**
   - **Jellyfin server-side remote control (`/Sessions/{id}/Playing`):** Only works *after* a Chromecast or Android TV / Google TV session is already active and connected to Jellyfin (`SupportsMediaControl: true`); the Jellyfin server cannot wake an idle Chromecast or launch the Cast receiver from scratch without an active Cast sender. Furthermore, Jellyfin's official Google Cast Web Receiver typically requires HTTPS with a valid certificate and reachable DNS (whereas the live ZimaOS server is plain LAN HTTP at `http://192.168.0.126:8097`).
   - **Direct Google Cast (`pychromecast` Default Media Receiver + Jellyfin stream URL):** A local Cast sender on the LAN can connect to the Chromecast over TCP `8009` (`cast.wait()`), launch the Default Media Receiver (`CC1AD845`) from idle without requiring HTTPS on the Jellyfin server, start playback via `media_controller.play_media(stream_url, content_type, title=...)`, and pause via `media_controller.pause()`.
   - **Tradeoffs and requirements for Chromecast:**
     - **Session reporting caveat:** Playing a raw `/Videos/{itemId}/stream` URL on the Default Media Receiver does not run a full Jellyfin client session by default (so Jellyfin `/Sessions` may not automatically track `NowPlayingItem.Id` or `PlayState.IsPaused` unless playback comes from a Cast-enabled Jellyfin app/receiver or progress is reported separately, whereas `media_controller.status` on the Chromecast itself reports `content_id`, `player_state` `PLAYING`/`PAUSED`, and `current_time`).
     - **Network & dependency gate:** Cast TLS control on port `8009` works across Docker bridge NAT if the Chromecast's LAN IP is configured directly (mDNS discovery on `224.0.0.251:5353` will not cross `hermes_default` bridge networking without host networking). Using `pychromecast` adds a production dependency (`protobuf`/`zeroconf`/`casttube`) that must be recorded in `DECISIONS.md` and validated under `hermes plugins validate --install-deps`.
     - **Identification needed before hardware probe:** To test the Chromecast sequentially, record the authorized Chromecast's LAN IP, model/type (classic Chromecast vs. Chromecast with Google TV running the Jellyfin Android TV app), and whether a direct `pychromecast` probe on port `8009` is authorized.

From the actual Hermes container (once the target device and control gate are authorized), test cold app launch, running-app input, episode,
resume and pause. Each attempt records bounded request parameters, response,
device active app/media report, matching Jellyfin session item/user/device and
position when available, plus separate human screen confirmation. A playing state
without item identity is unknown-title playback; active app alone is app-opened.
Record failures as failures. Launch intent and last-played cache are not evidence.

Roku 3 is an external player: TV wake depends on the actual TV/CEC configuration,
which remains unknown. Test standby separately without assuming Roku TV power
keys apply. Record exact title, wake and pause separately. Use 3s Roku and 8s Jellyfin request timeouts
for new implementation (earlier diagnostics used 5s).

## Chromecast Gen 2 direct Cast attempt — 2026-11-10

**Result: PASS — from idle, exact-file PLAYING then PAUSED on the same media session.**
Recorded before building integration. User explicitly authorized this device and
credential-free temporary MP4 test; only this Chromecast received control commands.

- Repository base: `6b11f9711e1213c3a650c6ecb0095da4945b379b`, clean `main` at start.
- Execution: T3 Docker container `172.23.0.2`, gateway `172.23.0.1`, on ZimaOS
  `192.168.0.126`. This is **not** the installed `hermes` container. No Docker socket
  or host shell access; linked-environment tool unavailable. Host forwarding became
  reachable during the test; user specified the final LAN URL below.
- Target: user-identified Chromecast Gen 2 `192.168.0.134`, live name `Den TV`,
  firmware `1.56.467165`, build `467165`. TCP 8009/8008 reachable; configured IP
  used directly. mDNS discovery was not tested.
- Runner: Python 3.14.10, `pychromecast` 14.1.1, in `/tmp/cast-test-venv` only.
  No changes to project dependencies or integration code.
- Source: copied the existing legal Big Buck Bunny item from Jellyfin's static MP4
  endpoint into a temporary file. This particular GET succeeded without credentials;
  no Jellyfin setting was changed. Item `e5d6c471a8a4ea26e00a3694f91bf8d1`.
  Size **64,657,027 bytes**, SHA256
  `f78f39603e6774907f2faafabf26a667f4a6fc31769ec304a8a8f7c62d280508`.
- Server: temporary `ThreadingHTTPServer` bound to **`0.0.0.0:8765`**, exact path
  **`/BigBuckBunny_320x180.mp4`** only, GET/HEAD and byte ranges, `video/mp4`,
  no authentication, directory listing, credentials or other files. Handler rejects
  other paths. The copy and HTTP endpoint were removed in `finally` after each test.
- Cast media URL: **`http://192.168.0.126:8765/BigBuckBunny_320x180.mp4`**.
  `play_media` used MIME `video/mp4`, stream type `BUFFERED`, then explicit `pause`.

### Final exact-URL test (UTC, 2026-11-10)

| Time | Evidence |
|---|---|
| 00:31:16.359 | Host LAN HEAD reached temporary server; 200, expected file length |
| 00:31:16.440 | Fresh status: idle Backdrop `E8C28D3C`, `is_stand_by: true`, `is_active_input: null`; LOAD sent |
| 00:31:19.019 | Media GET `Range: bytes=0-`, HTTP 206; later tail and continuation ranges also 206 |
| 00:31:20.171 | `content_id` exactly matched test URL, `player_state: PLAYING`, media session `1`, duration `596.459` seconds |
| 00:31:21.093 | After brief buffering, another `PLAYING` report at position `0.2115` seconds |
| 00:31:23.171 | Explicit pause sent after observing playback |
| 00:31:23.217 | Exact same URL and media session `1`, `player_state: PAUSED`, position `2.451218` seconds |
| 00:31:23.218 | Receiver app `CC1AD845`, `Default Media Receiver`; active-input unknown, standby still true |
| 00:31:23.362 | Quit test receiver and disconnect Cast client |
| 00:31:23.489 | HTTP listener closed; temporary MP4 deleted |

HTTP requests arrived through peer `172.23.0.3` (forwarding path). Exact receiver
`content_id` plus fresh state transitions identify the file; the sender-provided
title label alone is not used as proof. TV power/CEC wake and human screen
confirmation remain **unknown**. Receiver standby is not evidence of physical TV
power; it remained true during verified playback.

### Earlier attempts and cleanup

An initial harness attempt at 00:28:24 failed to serialize the CastStatus dataclass
before sending LOAD; it cleaned up. The corrected attempt at 00:28:36 used the
container URL `http://172.23.0.2:8765/BigBuckBunny.mp4`: receiver reported exact-URL
`IDLE` but no HTTP fetch or `PLAYING` within 40 seconds. Pause was not sent; server
and copy were removed, and receiver returned to Backdrop. Host port 8765 was not
usable then. This failure motivated the published LAN endpoint.

After host forwarding became reachable, a retry at 00:30:51 using the shorter
`/BigBuckBunny.mp4` filename passed PLAYING then PAUSED and cleaned up. That retry
had started just before the user's exact-filename instruction arrived. The final
attempt above repeated from idle using the requested filename and observed position
advance before pause. Both copies had the same SHA256.

The disposable runner and event logs remain locally under
`/tmp/terebi-cast-proof-20261110/`: `probe.py`, final `result.json`, and earlier
`attempt-1.json` through `attempt-3.json`. No MP4 remains. After cleanup the local
listener is closed; the host forwarder may accept TCP but serves no media response.
The user-managed forwarding configuration itself was not changed by the runner.

Network timeouts: HTTP 3s (source copy 8s), Cast socket 3s, connect wait 8s, play
verification 40s, pause wait 12s, overall guard 100s. No background server remains.
A successful direct Cast spike does not establish Hermes integration, compatibility
inside the actual `hermes` container, Jellyfin session/history reporting, or TV wake.

Checks on the unchanged plugin: **385 pytest tests passed**, Ruff lint/format
passed (27 files), isolated official Hermes v0.22.0 doctor passed (2 tools, 0 hooks),
and `hermes plugins validate --install-deps` passed with security scan **safe**.
Validation logs: `/tmp/terebi-cast-proof-hermes-gt64kwx3/`.

### Repeat with the user watching — 2026-11-10

At the user's request, repeated the same exact-URL test from idle Backdrop, with
15 seconds allowed after the first PLAYING report and a further 15 seconds holding
the paused frame before cleanup. Same device, file hash, one-file endpoint and
bound `0.0.0.0:8765` address; no integration changes.

- **00:35:31.262 UTC:** exact-URL `PLAYING`, media session `1`.
- **Human observation:** user replied **“yes i see it”** after the playing update.
  This confirms visible playback. The user did not separately confirm the frozen
  frame or whether the TV was initially on; physical wake remains unverified.
- **00:35:46.298:** exact-URL `PAUSED`, same session `1`, position **14.462817s**.
- **00:36:01.717:** receiver quit, HTTP server closed and temporary MP4 deleted.

Local evidence: `observed-repeat-result.json` and `human-observation.json` under
`/tmp/terebi-cast-proof-20261110/`. The automatic runner's human-confirmation field
is not chat-aware; the separate annotation records the actual user response.
The earlier exact-URL log is preserved as `first-exact-url-result.json`.

## Live Jellyfin cast-source preflight and Chromecast readiness check — 2026-11-10

Executed in the isolated Hermes `v0.22.0` runtime (`/tmp/hermes-screen-hermes-venv/bin/python`) against live Jellyfin `12.2.0` (`http://192.168.0.126:8097`) on the integrated `feat/jellyfin-chromecast-playback` code (`de5bf8d5ab33faec4fbf1b43bafaa9e269ae0493` / cherry-picked `da54f74`). `JELLYFIN_API_KEY` was requested via T3's one-time file secret card, read into memory, and immediately `unlink()`ed before any network call (`secret_file_unlinked: True`).

1. **Live Jellyfin item metadata and `get_cast_source` verification (`e5d6c471a8a4ea26e00a3694f91bf8d1`):**
   - `JellyfinClient.status()` returned `{"ok": true, "server": {"name": "terebi", "version": "12.2.0"}, "user": {"id": "682764864adc45bbb6b981837f790812", "name": "homelab-hp"}, "counts": {"movies": 1, "series": 0, "episodes": 0}}`.
   - Raw `GET /Items/e5d6c471a8a4ea26e00a3694f91bf8d1?userId=682764864adc45bbb6b981837f790812` `MediaSources[0]` reported:
     - `Id: "e5d6c471a8a4ea26e00a3694f91bf8d1"`, `Container: "mp4"`, `Protocol: "File"`, `IsRemote: false`, `Size: 64657027`, `Bitrate: 867212`, `RunTimeTicks: 5964583330`, `SupportsDirectPlay: true`, `SupportsDirectStream: true`, `DefaultAudioStreamIndex: 1`.
     - Stream 0 (`Video`): `Codec: "h264"`, `Profile: "Constrained Baseline"`, `Width: 320`, `Height: 180`.
     - Stream 1 (`Audio`): `Codec: "aac"`, `Profile: "LC"`, `Channels: 2`, `SampleRate: 48000`.
   - `JellyfinClient.get_cast_source("e5d6c471a8a4ea26e00a3694f91bf8d1")` returned:
     `{"duration_s": 596.458333, "item_id": "e5d6c471a8a4ea26e00a3694f91bf8d1", "media_source_id": "e5d6c471a8a4ea26e00a3694f91bf8d1", "minutes": 10, "title": "BigBuckBunny_320x180", "type": "Movie"}`.
2. **Live authenticated upstream `HEAD` and byte-range `GET` (`cast_stream_target`):**
   - Upstream URL: `http://192.168.0.126:8097/Videos/e5d6c471a8a4ea26e00a3694f91bf8d1/stream?static=true&mediaSourceId=e5d6c471a8a4ea26e00a3694f91bf8d1` with `Authorization: MediaBrowser ...` header.
   - Authenticated `HEAD` returned HTTP `200` (`content-type: video/mp4`, `accept-ranges: bytes`, `content-length: 64657027`).
   - Authenticated `GET` with `Range: bytes=0-1023` returned HTTP `206` (`content-type: video/mp4`, `accept-ranges: bytes`, `content-range: bytes 0-1023/64657027`, `content-length: 1024`, `bytes_read: 1024`, MP4 box signature `ftypisom`).
3. **Live Chromecast (`192.168.0.134`) and ZimaOS host forwarder (`192.168.0.126:8765`) readiness check (`2026-11-10T01:19:26Z`):**
   - TCP connect to `192.168.0.134:8009` failed with `TimeoutError: timed out` / `OSError: [Errno 113] No route to host` (the Chromecast Gen 2 is currently powered off or asleep with the TV; TV wake is out of scope for this slice).
   - HTTP probe to `http://192.168.0.126:8765/probe` while listening on container `0.0.0.0:8765` failed with `URLError: <urlopen error [Errno 111] Connection refused>` (the temporary ZimaOS port forwarder `192.168.0.126:8765` -> `172.23.0.2:8765` is currently stopped).
   - Because `192.168.0.134:8009` was unreachable and the host forwarder on `192.168.0.126:8765` was stopped, live `tv_play` / `tv_pause` against the physical Chromecast could not be executed in this pass and remains gated on powering on the Chromecast and starting the temporary host port forwarder.
