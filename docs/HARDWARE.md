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
  - On 2026-11-09 the user confirmed `/System/Info/Public` returns HTTP 200 from inside `hermes` (`hermes_default`) and reported installed Hermes v0.16.0. This T3 container still has no Docker socket or SSH credentials for ZimaOS. Public reachability does not verify authenticated endpoints.
  - The Roku Jellyfin app currently reports `"Server not found"` when connecting to ZimaOS Jellyfin. The user is finishing a Roku packet capture separately; **manual playback on the Roku is the next Roku milestone**, kept separate from the third-party ECP shipping restriction.

Record signed-in Jellyfin user, installed Roku channel ID and one legal library
item's ID/type/title once the Roku app connects. Do not reuse the old YouTube
video ID as a Jellyfin item ID.

From the actual Hermes container, test cold app launch, running-app input, episode,
resume and pause. Each attempt records bounded request parameters, response,
Roku active app/media report, matching Jellyfin session item/user/device and
position when available, plus separate human screen confirmation. A playing state
without item identity is unknown-title playback; active app alone is app-opened.
Record failures as failures. Launch intent and last-played cache are not evidence.

Roku 3 is an external player: TV wake depends on the actual TV/CEC configuration,
which remains unknown. Test standby separately without assuming Roku TV power
keys apply. Record exact title, wake and pause separately. No launch, wake, pause,
or resume has been demonstrated yet. Use 3s Roku and 8s Jellyfin request timeouts
for new implementation (earlier diagnostics used 5s).

## Latest user confirmation — 2026-11-09

Roku sign-in and manual playback are still pending. Previous “Server not found”
report is historical; no newer successful connection/playback evidence supplied.
The separate Hermes v0.22.0 smoke runtime is in the development environment, not
an upgrade to ZimaOS's v0.16.0 container. Its HTTP tool tests use mocks; they do not
prove a Roku Jellyfin session or an exact item match.
