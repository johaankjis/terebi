# Terebi Games v1: rock-paper-scissors

Ask Hermes “Let's play rock-paper-scissors.” It returns a three-minute, single-use
pairing link for your phone and a read-only display link for Mac Chrome. One
ZimaOS service owns the countdown, moves and score. Camera frames and landmarks
stay on the phone. No shutter button: hold rock, an open palm, or a V for scissors
at the end of the countdown. An unclear gesture offers Retry without scoring.
Tap-to-play is an explicitly labelled fallback and recorded as a tap round.

The interface uses CSS sky gradients, translucent panels and glossy buttons.
The TV display has a large countdown, moves, result and running score. Optional
Fullscreen requires a click. A session lasts 30 minutes; service restart ends it.
Only the three moves and round IDs are submitted. Score updates are serialized
and happen once per accepted round. Hermes's salted commitment is published
before the player submits; move and nonce are revealed afterward. Retry replaces
the attempt ID while keeping the same logical round and locked Hermes move.

## Chosen TV path and first live gate

Manual Mac Chrome tab mirroring to **Den TV, Chromecast Gen 2, 192.168.0.134**.
The user has no Custom Web Receiver app ID or registered test device. Google
requires both for unpublished Custom Receiver testing; the default media receiver
cannot load an arbitrary interactive HTML page. No Custom Receiver is shipped.

**Not yet verified:** Den TV showing this game and one live shared-state update.
This is the FIRST hardware gate after deployment: open the display link on the
Mac, mirror it, then pair the phone and confirm the TV changes from Waiting to
Ready. Remaining camera/three-round acceptance stays pending until this passes.

## Hosting choice and exposure

T3's probes found Caddy on host HTTP port 80; host TLS port 443 refused connection.
There is no HTTPS proxy config in this repository. The internal Caddy/host config
has not been inspected: this T3 container has no host shell or Docker socket.
User can provide the output of `docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}'`
and `ss -lnt` in the ZimaOS terminal. Do not include environment variables/secrets.

The proposed prototype uses a Cloudflare Quick Tunnel: no account or domain,
random trusted `https://....trycloudflare.com` hostname, changes on each tunnel
restart, no uptime guarantee. It exposes only this game container's static pages,
local model/WASM assets and game API. Session creation needs the admin secret;
pairing is one-use/three-minutes and player/display tokens expire after 30 minutes.
The URL is public, not an access-control boundary. Cloudflare terminates HTTPS and
can see game requests/tokens, but camera images never leave the phone. It does not
expose Jellyfin, the ZimaOS dashboard, movie media or the Docker socket. No SSE:
clients poll with bounded timeouts. Stop the tunnel after testing.

## Run on ZimaOS (host-side commands)

T3 prepares and checks the source, camera assets and source archive. **T3 cannot
run these Docker commands on your host.** Download the source archive linked in
T3 and use ZimaOS Files to upload it as:
`/DATA/AppData/terebi-games-rps/source.tar.gz`.
Use a new dedicated directory; keep existing Terebi/movie deployments intact.

Run in the **ZimaOS web terminal** (Docker access required):

```sh
mkdir -p /DATA/AppData/terebi-games-rps/src
cd /DATA/AppData/terebi-games-rps/src
tar -xzf ../source.tar.gz
sh games/deploy/host.sh build
sh games/deploy/host.sh init
sh games/deploy/host.sh start
sh games/deploy/host.sh status
```

Build fetches the pinned npm runtime/model with checksum validation. Node/Python
base images and Cloudflare's utility image require Internet access. No account
is needed for Quick Tunnel. Config is generated with a random admin secret;
`init` preserves it on repeats, and does not print it. The service runs as UID
10001 with a read-only filesystem and no Linux capabilities. Only localhost
port 8766 is published on the host. Two containers join their own compose network.
Docker image build/run itself is **not verified from T3** (no Docker executable or
socket); direct Python/Node execution is checked here. Image tags can be pinned to
pulled digests after the host records them for the acceptance run.

Find the `https://....trycloudflare.com` hostname in tunnel status, then run:

```sh
sh games/deploy/host.sh set-url https://YOUR-HOSTNAME.trycloudflare.com
```

This restarts only the new game container. It invalidates any old sessions. Give
T3 that public hostname and the non-secret status output. Do not send game admin
keys in chat. If the tunnel restarts with a different hostname, repeat `set-url`.

## Hermes / Telegram configuration (T3 isolated test runtime)

Use official Hermes >=0.22.0. Configure `games_service_url` to the HTTPS origin
(or its reachable private service origin), and `TEREBI_GAMES_API_KEY` via Hermes's
secret scope to the generated `admin_token` in the private game config. Supply
any key to T3 only using the private secret card when requested. Keep the existing
production movie bot untouched; acceptance uses the isolated @terebitvbot gateway
and a final-SHA-pinned plugin copy. Do not run competing Telegram pollers.

The new `tv_game_start` tool takes no arguments and is scoped to the host-injected
Hermes conversation/session ID. Repeated calls reuse that active game. It returns
links; it does not claim automatic TV launch or verified TV state.

## Pair and mirror (after the manager confirms the bot is ready)

1. On Telegram say **“Let's play rock-paper-scissors.”**
2. On the Mac, open the display link in **Chrome**. Chrome menu → **Cast, save,
   and share → Cast…** → Sources **Cast tab** → **Den TV**. The Mac and Chromecast
   must be on the same LAN. Click the page's **Fullscreen** button (or use Chrome
   fullscreen if unavailable). Keep that tab active for the TV display.
3. On iPhone open the pairing link in **Safari** within three minutes. Confirm the
   TV changes **Waiting → Ready**. This establishes the first TV/state-update gate.
4. Read the camera explanation and tap **Start camera**. Allow **Camera** access.
   Microphone is never requested. Keep one hand fully in the preview and use good
   lighting. If denied, change Safari's **aA → Website Settings → Camera → Allow**,
   then explicitly press Start camera again. No camera permission is re-requested
   silently. Backgrounding Safari or leaving the page stops its camera.
5. Tap **Start round**. Reveal your chosen gesture on **Shoot**, then hold it
   steady briefly. After a 150 ms settling period, the phone looks for three
   consecutive confident predictions spanning at least 120 ms, until +900 ms.
   Countdown and initial movement do not vote against the revealed pose. Use **Next round**
   to continue. If unclear/no hand, follow the prompt and press **Retry**; the
   shared countdown restarts with unchanged score and Hermes move.
6. For a temporary camera problem, use the clearly labelled **Tap-to-play** panel;
   evidence must call these tap rounds, not camera rounds.

Pairing once lasts across rounds/reloads in the same Safari tab. Expired sessions
require a new Telegram game. Display tokens cannot play moves. Stop/retry/next are
controlled only by the paired device.

## TV background music

The TV display (Custom Receiver and the manual display page) starts a looping
background track — `games/display/hydrate.mp3` (user-supplied "hydrate! • a
frutiger aero playlist") — as soon as the TV version opens, before the session
handshake completes. Implementation details:

- One shared `<audio>` player per page (`startMusic` in
  `games/display/display.js`): `loop`, volume `0.5`, served same-origin at
  `/display/hydrate.mp3` under the receiver's `default-src 'self'` CSP.
- The receiver starts music at page open; the manual display page starts it via
  `startDisplay`. Autoplay-blocked starts silently retry on the next call.
- Music pauses when the session ends (`stop()`), the page hides, or the receiver
  is stopped by Hermes; a session restart resumes it.
- The iPhone camera player page never loads the audio — the phone keeps silent so
  its microphone pipeline is unaffected.
- The service whitelist gained `.mp3` for the `/display/` prefix only; traversal
  and extension bounds stay covered by `tests/test_rps_http.py`.

## Acceptance evidence to capture

- Exact source SHA, Docker image IDs and public HTTPS origin; isolated gateway
  registration and Telegram response; actual iPhone model/iOS/Safari version.
- Den TV mirror shows Waiting → Ready from the SAME session's phone pairing.
- Three completed **camera** rounds with no shutter press. Correlate TV and phone
  states; exactly one `round_scored` event per round and total rounds 1, 2, 3.
- Remove the hand for a countdown: retry prompt, no score increment. Retry keeps
  Hermes commitment and logical round, changes attempt ID; then score only once.
- Tap **Stop camera**: preview stops, all tracks end and iPhone camera indicator
  turns off. No further automatic move can be sent. Re-start is explicit.
- Keep denied permission/missing camera/leave-page mock coverage distinct from
  any real device observation. Tap fallback must be labelled separately.

On the host, sanitized game events are available with:

```sh
sh games/deploy/host.sh evidence
```

Events contain session/attempt hashes, phases, round numbers, accepted moves and
scores; no bearer token, images or landmarks. Docker log rotation bounds storage.
Before sharing other outputs, omit game links/tokens and the private config.
After testing, release the camera and stop the tunnel/service:

```sh
sh games/deploy/host.sh stop
```

Private config remains for a repeat; active sessions are memory-only and expire
on shutdown. This prototype adds no trivia, voice, charades, Roku or multiplayer.


## Current verification checkpoint

Exact tested source: **`aee89f97acdcf8b7cd23efb1f1d32895c4a7767c`**.

- **852 Python tests passed**, including the complete existing movie/scene suite,
  RPS scoring combinations, concurrent submissions, retry invariants, expiry,
  capability roles, HTTP privacy/input boundaries and native Hermes game links.
- **59 JS tests passed**, mocked camera/recognizer/timers. Camera assets build with
  checksum verification; no real camera, iPhone accuracy or release observation
  is claimed from these tests. A three-round API simulation is also a unit test.
- Ruff lint/format, diff check, shell syntax, display JS syntax, compose YAML and
  local-only host port assertions pass. Docker build/run remains host-side pending.
- Official isolated Hermes v0.22.0 doctor passed (8 tools, 0 hooks); validation and
  real-loader/ToolRegistry dispatcher smoke passed. Cautions remain visible for
  configurable LAN bind, tunnel service, and generated MediaPipe WASM loader
  `/proc` helpers discovered in built/vendor dependencies. No scan suppression.
- The initial smoke command exposed an accidental extra positional argument in
  the test harness; it was fixed and the smoke rerun passed. An initial dependency
  preparation retry message cleared on the stable-source validation rerun.
- Logs: `/tmp/terebi-rps-final-f6wz5fx5/` (validation/smoke),
  `/tmp/terebi-rps-checks-cumx0bpr/doctor.log`.

The selected TV path is manual Mac Chrome mirroring, not yet verified on Den TV.
ZimaOS deployment, Telegram game start, trusted-HTTPS iPhone Safari capture,
three real camera rounds, missed-hand retry, and physical Stop-camera indicator
acceptance remain pending. No game-state update on the TV is claimed yet.
A temporary T3 LAN display-only spike can use the existing host port 8765 forwarder
for the first Waiting → Ready proof; camera acceptance requires the HTTPS host.

The pinned model binary is downloaded at build time; no model binary is committed.
The model card text was extracted, but contained no explicit license grant; its
manifest retains that provenance limitation for redistribution review.


Draft PR: https://github.com/johaankjis/terebi/pull/6 (leave unmerged).
The existing host:8765 → T3 forwarder returned HTTP 200 for the temporary game
`/health` probe on 2026-11-11. This proves LAN reachability only. The display-only
proof has a 20-minute lifetime and requires user mirroring/TV confirmation; it
cannot establish trusted-HTTPS camera acceptance or ZimaOS deployment.


## Temporary iPhone recognition practice (PR #6)

User reports that Safari camera preview works, but no rock/paper/scissors was
recognized. This is an unresolved live defect; mocked recognizer tests do not
establish device success. The existing MediaPipe 0.10.35 CPU path, model hash,
confidence threshold are unchanged. The initial diagnostic build retained the
old 400ms-before/450ms-after window; the post-Shoot update below replaces it.

After turning on the camera, practice runs before a round. Green connections and
white landmarks follow the hand over a mirrored, aspect-preserving preview.
The page shows the detected category and confidence, or distinct no-hand,
low-confidence, stalled-prediction or model-error status. Initialization reports
JavaScript, WASM and model stages. Hold each of rock/paper/scissors steady until
its local practice check appears, then press **Practice complete — use camera in
rounds**. Practice never sends moves, and its frame window is cleared on exit.
Only the latest landmark set is retained in device memory; it is cleared on Stop
or leaving the page. No frame, landmark, confidence or practice status is sent.

First test all three gestures on the actual iPhone Safari. If practice works,
start a countdown and hold the shape through Shoot. The local status reports the
last Shoot window's prediction count, confident count and span. Unclear rounds
still send nothing and require Retry. Report the displayed status and which
shapes worked; device acceptance remains open until observed. Tap rounds remain
separate evidence.

To update the existing ZimaOS deployment, upload the new source archive, extract
it over the source directory (the archive contains no private configuration),
then build and recreate only the game service:

```sh
cd /DATA/AppData/terebi-games-rps/src
tar -xzf ../practice-source.tar.gz
sh games/deploy/host.sh build
docker compose -f games/deploy/compose.yaml up -d --no-deps games
```

Keep the tunnel container running to retain its hostname. The service restart
expires old sessions; ask the isolated Telegram bot for a new game and reload
both pages. Confirm the page contains the practice button before testing.


Display footer: a fresh unpaired session shows **Waiting for you** with
**Live · Waiting for a phone to pair**. Only after successful pairing does it
show **Live · Your paired phone controls the game**. Before the first live
snapshot it says Connecting; expiration says Session ended. Verified using the
actual display script in a DOM harness against a fresh local HTTP session,
then pairing that same session. Browser preview was unavailable due to missing
host libraries; physical Den TV verification remains separate.


### Post-Shoot timing update

User reports practice recognizes gestures, but a round says the hand changed at
the last moment. Inspection found the old whole-window majority included 400 ms
before Shoot and could penalize moving into the final shape. Round recognition
now uses only predictions from +150 ms through +900 ms after the shared Shoot
deadline. Accept the latest consecutive run of at least three predictions with
confidence >=0.6 spanning >=120 ms. A missing hand, weak prediction, different
move or >250 ms prediction gap breaks the run. The last prediction must be at
most 250 ms old. Accept at the first stable run, submit once, or offer Retry at
the deadline without changing the score. Practice's local feedback is unchanged.

The local Last Shoot window line includes post-Shoot bounds, total/confident
predictions, stable run length/span, latest prediction's offset from Shoot and
waiting/recognized/retry status. Nothing new is sent to the server. Test a reveal
on Shoot for each of rock, paper and scissors on the real iPhone Safari, then
an uncertain gesture and Retry. Unit tests model transitions, flicker, low
confidence, missing/stale/sparse frames, deadline, server clock offset and a
single submission. Actual iPhone timing acceptance remains pending deployment.


## Frutiger Aero TV scene (2026-11-11)

The TV shows a sky, drifting clouds, hills and a lake behind two glass spheres,
separate You and Hermes score panels and a wide banner. The Cast receiver and the
manual display page load the same renderer from `/display/`.

| Server state | TV |
| --- | --- |
| `waiting_for_player` | “Waiting for you — Open the pairing link on your phone.” Empty floating spheres, pulsing phone icon. Music starts when the page opens. |
| paired (seen live) | Lake ripple, phone turns into a checkmark, spheres and score panels glide in, “Phone connected”, then “Ready — Start the round on your phone.” Once per pairing; a reload of a paired session shows Ready at once. |
| `countdown` | 3, 2, 1, then Shoot! in the center, one glass pulse per beat. Spheres stay empty. |
| `countdown`, 2 s after Shoot | “Try again — Tap Retry on your phone.” |
| `reveal`, `score` | Both 3D hands turn in on the same frame; move names, “You win! / Hermes wins! / It’s a tie!”, the reason, the score, a Winner tag and a hop for the winner. |
| `next_round` | Hands stay; “Tap Next round on your phone.” Ambient motion returns. |

The footer shows the real connection (`Connecting`, `Live`, `Reconnecting`,
`Session ended`), the round and ties, and `3D` or `Static`. Static means the still
scene: reduced motion is requested, the device measured under 20 fps, or the
manual display link ended in `&motion=still`. `&motion=full` pins the animated
scene. Without WebGL the hands are drawn flat with the same poses.

Deploy exactly as for earlier builds (upload the archive, `host.sh build`, recreate
only the `games` container); the tunnel hostname and Cast registration are unchanged.
First check on Den TV: open a game, watch the Waiting screen for ten seconds and
read the footer mode.
