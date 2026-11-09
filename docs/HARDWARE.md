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
