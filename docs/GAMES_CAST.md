# Direct Chromecast game receiver

This slice starts from main `19e2344ca6dd5c671855036a0c1a93b3d0b71d77`
on `feat/chromecast-game-launch`. The RPS service, on-device phone recognition,
round/scoring authority and existing movie/scene controls are reused. There is
no Custom Receiver app ID hard-coded into the plugin.

## Google Console setup (user, on Mac)

Use `https://cast.google.com/publish/` in Chrome. Google lists a non-refundable
US$5 developer registration fee. Sign in with the Google account that will own
the receiver. The fee/account setup is a user action; T3 does not handle it.

1. Devices -> Add New Device: enter Den TV's Chromecast serial number and name
   the device Den TV. The console's Cast button can display/read out the serial
   number on the TV. Keep the serial in the console; it is not needed in git.
2. Wait about 15 minutes for Ready for Testing, then physically power-cycle the
   Chromecast (disconnect/reconnect its power).
3. Applications -> Add New Application -> Custom Receiver. Name: Terebi Games.
4. URL: `https://YOUR-HOSTNAME.trycloudflare.com/receiver/` using the current
   game service's actual trusted HTTPS hostname. Do not add any token or query.
5. Leave relay casting and audio-only support unchecked. Save, copy the
   Application ID, Done. Keep the application unpublished for registered-device
   tests. Configure the eight-character ID as `games_receiver_app_id` in Hermes.

The receiver URL is served by this branch's game container, not by the old RPS
image. Deploy before launching it. Keep the tunnel running. If its hostname
changes, update both the service public URL and the Console receiver URL.
Official registration reference: `https://developers.google.com/cast/docs/registration`.
The Custom Receiver fetches Google's CAF v3 SDK from www.gstatic.com; the rest of
the UI comes from the same game origin. The phone's local MediaPipe path and its
privacy restrictions are unchanged.

## Deploy and configure

T3 provides a source archive and runs local checks. The user uploads it as
`/DATA/AppData/terebi-games-rps/cast-source.tar.gz` and runs on ZimaOS:

```sh
cd /DATA/AppData/terebi-games-rps/src
tar -xzf ../cast-source.tar.gz
sh games/deploy/host.sh build
docker compose -f games/deploy/compose.yaml up -d --no-deps games
```

This recreates only the game container; it invalidates existing sessions. The
tunnel container and private configuration remain. Check `/receiver/`,
`/receiver/receiver.js` and `/receiver/session.js` over the trusted hostname.

In the isolated Hermes profile set `games_service_url` to the service origin,
`chromecast_host` to the identified Den TV (`192.168.0.134`), and
`games_receiver_app_id` to the Console ID. Retain `TEREBI_GAMES_API_KEY` only in
Hermes's secret scope. No production bot deployment is implied. Only one
@terebitvbot poller may run. Starting a game replaces the app currently running
on the configured Chromecast, just like starting a movie.

## Handoff and success evidence

Custom namespace: `urn:x-cast:com.terebi.games`.

```json
{"type":"SHOW_SESSION","session_id":"opaque id","display_token":"read-only capability","request_id":"fresh random challenge"}
```

Only the viewer capability is sent; no player/pairing token, game admin key,
Jellyfin key, URL, image, landmark or phone camera state crosses Cast. The
receiver uses its own origin to fetch the matching session with header auth and
runs the exact same display renderer as the manual page. It keeps the credential
in memory; it does not write a Cast credential to browser storage or a URL.

After successful state fetch and DOM render, two animation-frame callbacks allow
rendering before the receiver sends:

```json
{"type":"DISPLAY_RENDERED","session_id":"same id","request_id":"same challenge","phase":"waiting_for_player","revision":1}
```

A stale challenge, different session, invalid phase/revision, changed app or launch
status alone never proves readiness. The sender requires the correct app and
matching acknowledgement. It disconnects without stopping the receiver, which
continues polling after the Mac/sender connection is gone. CAF's non-media
`disableIdleTimeout` is enabled; session expiry stops the receiver.

`tv_game_start` always retains the pairing/manual display links. On matching
acknowledgement it returns `display_path: custom_cast_receiver`,
`tv_verified: true` and `tv.evidence: receiver_rendered_session`. This is receiver
render evidence; it does not prove that a physical television is powered on or
on the correct HDMI input. `wake_verified` and `input_verified` remain false.
On missing configuration, failure or timeout it returns a usable game with
`tv_verified: false`, a small `tv` reason/hint, and the manual Chrome mirroring
fallback. No acknowledgement means unverified, not success.

Cast debug records containing this namespace/display_token are suppressed,
including exception payloads. Game service request logs remain off. No new
runtime dependency is added.

## Sequential live acceptance (manager + user)

Only Den TV Chromecast Gen 2 at 192.168.0.134 is authorized. No worker performs
hardware tests. Record the exact plugin/service source commit and Console app ID
(app ID is public configuration; no serials or credential values in evidence).

1. Mac closed, TV already on Chromecast input: Telegram asks for a game. Record
   matching receiver acknowledgement and user observation of Waiting on Den TV.
2. Pair iPhone Safari once. Record server paired event and user observation of
   Ready on TV. Complete practice and a camera round without any shutter action;
   correlate attempt/session hashes and the single server score update, and
   confirm both screens show the result. Record camera input, not tap fallback.
3. Separate wake test: put TV in standby, start a game and record whether the
   physical TV wakes. Receiver acknowledgement alone cannot establish wake.
4. Separate HDMI test: TV on a different input, start a game and record whether
   it switches. Cast active-input flags, if available, are supporting evidence;
   user observation determines the physical result. These are HDMI-CEC/device
   capabilities, not guaranteed features of the game tool.
5. Exit only this configured game app (verify current app ID before stopping),
   then use existing tv_play for the exact known Jellyfin edition. Verify movie
   identity/content URL and receiver PLAYING, then PAUSED; record user observation.
   Reuse the original temporary movie media forwarder only for this movie check.
6. Confirm a receiver launch/ack failure returns the manual link without losing
   phone pairing; no TV-ready claim on fallback.

Until the user supplies a registered app ID and deploys this receiver build,
these live gates are BLOCKED. Unit/DOM fixtures do not count as Gen 2 CAF tests,
Mac-closed operation, TV power/input checks or post-game movie playback.
